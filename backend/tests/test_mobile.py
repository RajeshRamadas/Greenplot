"""Speed and mobile-app readiness: query counts that stay flat as data grows, conditional GETs,
compression, one error shape, push to phones, photo previews and the app start-up config."""

import io
from contextlib import contextmanager

import pytest
from PIL import Image
from sqlalchemy import event

from app.core import db as dbmod
from app.main import create_app
from app.models import DeviceToken, Notification, NotificationDelivery, PatrolCheckpoint, PatrolRoute, TicketCategory
from app.services import notifications, push


@contextmanager
def count_queries():
    seen = []

    def on_execute(conn, cursor, statement, *args):
        seen.append(statement)

    event.listen(dbmod.engine, "before_cursor_execute", on_execute)
    try:
        yield seen
    finally:
        event.remove(dbmod.engine, "before_cursor_execute", on_execute)


# --------------------------------------------------------------------------- query counts


def test_lists_do_not_query_once_per_row(as_, world, db):
    admin = as_(world.admin)
    admin.ok("get", "/tickets/categories")  # creates the default categories
    for i in range(30):
        db.add(TicketCategory(tenant_id=world.ta.id, code=f"extra-{i}", name=f"Extra {i}", position=100 + i))
        route = PatrolRoute(tenant_id=world.ta.id, name=f"Route {i}")
        db.add(route)
        db.flush()
        db.add(PatrolCheckpoint(tenant_id=world.ta.id, route_id=route.id, name="Gate", qr_code=f"CP-{i}"))
    db.commit()

    for path, most in (("/tickets/categories", 8), ("/patrol/routes", 6), ("/incidents", 8), ("/inspections", 10)):
        with count_queries() as seen:
            r = admin.get(path)
        assert r.status_code == 200, r.text
        assert len(seen) <= most, f"{path} ran {len(seen)} queries"
    assert len(admin.ok("get", "/tickets/categories")) >= 30


def test_sign_in_checks_take_one_query(as_, world):
    admin = as_(world.admin)
    with count_queries() as seen:
        admin.ok("get", "/auth/me")
    assert len(seen) <= 2, seen  # the caller, layout and session together; /me itself reads nothing else much


# --------------------------------------------------------------------------- HTTP


def test_unchanged_lists_answer_304(as_, world):
    admin = as_(world.admin)
    first = admin.get("/meta")
    etag = first.headers["etag"]
    assert etag.startswith('W/"') and "private" in first.headers["cache-control"]
    again = admin.get("/meta", headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b"" and again.headers["etag"] == etag
    assert admin.get("/meta", headers={"If-None-Match": 'W/"other"'}).status_code == 200


def test_large_responses_are_gzipped(as_, world):
    admin = as_(world.admin)
    r = admin.get("/tickets/categories", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip" and r.json()  # the client unpacks it
    assert "accept-encoding" in r.headers.get("vary", "").lower()


def test_errors_share_one_shape(client, as_, world):
    admin = as_(world.admin)
    missing = admin.get("/tickets/00000000-0000-0000-0000-000000000000").json()
    assert missing["code"] == "not_found" and missing["detail"] == missing["message"]
    assert client.get("/api/v1/auth/me").json()["code"] == "unauthorized"
    bad = admin.post("/tickets", {"title": ""}).json()
    assert bad["code"] == "validation_error" and isinstance(bad["detail"], list) and bad["message"]
    forbidden = as_(world.resident).get("/audit").json()
    assert forbidden["code"] == "forbidden" and "Missing permission" in forbidden["message"]


def test_operation_ids_are_short_and_unique():
    spec = create_app().openapi()
    ids = [op["operationId"] for item in spec["paths"].values() for op in item.values() if isinstance(op, dict) and "operationId" in op]
    assert len(ids) == len(set(ids))
    assert "tickets_list_tickets" in ids and "app_register_device" in ids


def test_app_config_needs_no_sign_in(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "app_min_version_android", "1.2.0")
    cfg = client.get("/api/v1/app/config").json()
    assert cfg["api_version"] == "v1" and cfg["min_version"] == {"android": "1.2.0", "ios": None}
    assert cfg["push_enabled"] is False


# --------------------------------------------------------------------------- notifications and push


@pytest.fixture()
def fcm():
    sent = []

    def transport(token, message):
        if token.startswith("gone"):
            raise push.PushError("HTTP 404: NOT_FOUND/UNREGISTERED", gone=True)
        sent.append(message)
        return {"name": f"projects/greenplot/messages/{len(sent)}"}

    push.set_transport(transport)
    yield sent
    push.set_transport(None)


def test_phone_gets_pushes_until_it_signs_out(client, world, db, fcm):
    from tests.conftest import Api

    phone = Api(client, world.resident.email)
    d = phone.ok("post", "/devices", {"token": "fcm-token-" + "x" * 30, "platform": "android", "app_version": "1.0.0"})
    assert d["platform"] == "android" and len(phone.ok("get", "/devices")) == 1

    notifications.notify(db, world.ta.id, [world.resident.id], "ticket_update", "Ticket resolved", "Tap to rate", "ticket", world.p117.id)
    db.commit()
    [msg] = fcm
    assert msg["notification"]["title"] == "Ticket resolved"
    assert msg["data"]["entity_type"] == "ticket" and msg["data"]["entity_id"] == str(world.p117.id)
    row = db.query(NotificationDelivery).filter_by(channel="push").one()
    assert row.status == "sent" and row.provider_message_id == "projects/greenplot/messages/1"

    phone.ok("post", "/auth/logout", {"refresh_token": phone.refresh})
    notifications.notify(db, world.ta.id, [world.resident.id], "ticket_update", "Another update")
    db.commit()
    assert len(fcm) == 1, "a signed-out phone gets nothing"
    db.expire_all()
    rows = db.query(NotificationDelivery).filter_by(channel="push").order_by(NotificationDelivery.created_at).all()
    assert rows[-1].status == "skipped" and rows[-1].failure_reason == "no_device"


def test_uninstalled_app_token_is_switched_off(client, world, db, fcm):
    from tests.conftest import Api

    phone = Api(client, world.resident.email)
    phone.ok("post", "/devices", {"token": "gone-token-" + "y" * 30, "platform": "ios"})
    notifications.notify(db, world.ta.id, [world.resident.id], "ticket_update", "Hello")
    db.commit()
    db.expire_all()
    d = db.query(DeviceToken).one()
    assert d.disabled_at is not None and "UNREGISTERED" in d.disabled_reason
    assert db.query(NotificationDelivery).filter_by(channel="push").one().status == "failed"
    assert phone.ok("get", "/devices") == []


def test_a_device_token_moves_to_whoever_signs_in(client, world, db):
    from tests.conftest import Api

    token = "shared-phone-" + "z" * 30
    Api(client, world.resident.email).ok("post", "/devices", {"token": token, "platform": "android"})
    Api(client, world.resident2.email).ok("post", "/devices", {"token": token, "platform": "android"})
    [d] = db.query(DeviceToken).all()
    assert d.user_id == world.resident2.id


def test_notifications_wait_for_the_save(world, db, monkeypatch):
    sent = []
    monkeypatch.setattr(notifications.ADAPTERS["email"], "send", lambda user, title, body, data=None: sent.append(title) or "sent")

    notifications.notify(db, world.ta.id, [world.resident.id], "ticket_update", "Rolled back", channels=["in_app", "email"])
    db.rollback()
    assert sent == [] and db.query(Notification).count() == 0

    notifications.notify(db, world.ta.id, [world.resident.id], "ticket_update", "Saved", channels=["in_app", "email"])
    assert sent == []
    db.commit()
    assert sent == ["Saved"]
    db.expire_all()
    note = db.query(Notification).one()
    assert note.delivery == {"in_app": "stored", "email": "sent"}


def test_worker_sends_what_was_left_queued(world, db, monkeypatch):
    from datetime import timedelta

    from app.models.base import utcnow

    sent = []
    monkeypatch.setattr(notifications.ADAPTERS["email"], "send", lambda user, title, body, data=None: sent.append(title) or "sent")
    notifications.notify(db, world.ta.id, [world.resident.id], "ticket_update", "Stranded", channels=["in_app", "email"])
    db.info.pop("queued_deliveries")  # as if the process stopped before sending
    db.commit()
    assert sent == []
    row = db.query(NotificationDelivery).filter_by(channel="email").one()
    assert row.status == "queued"
    row.created_at = utcnow() - timedelta(minutes=5)
    db.commit()
    assert notifications.retry_failed_deliveries(db) == 1
    db.commit()
    assert sent == ["Stranded"] and row.status == "sent" and row.attempts == 1


# --------------------------------------------------------------------------- photos


def _photo(size) -> bytes:
    buf = io.BytesIO()
    Image.effect_noise(size, 60).convert("RGB").save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_large_photos_get_a_screen_sized_preview(as_, world):
    admin = as_(world.admin)
    big = admin.upload("property", world.p117.id, _photo((3000, 2000)), "image/jpeg").json()
    assert big["thumbnail_url"] and big["preview_url"]
    preview = admin.c.get(big["preview_url"].replace("http://testserver", ""))
    assert preview.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(preview.content)) as im:
        assert max(im.size) == 1600

    small = admin.upload("property", world.p117.id, _photo((800, 600)), "image/jpeg").json()
    assert small["thumbnail_url"] and small["preview_url"] is None, "small photos are already screen-sized"


def test_signed_links_stay_the_same_within_a_minute(as_, world):
    admin = as_(world.admin)
    m = admin.upload("property", world.p117.id, _photo((200, 100)), "image/jpeg").json()
    again = admin.ok("get", f"/media/{m['id']}")
    # Phones cache pictures by URL; a new link on every request would download them again.
    expiries = [int(x["url"].split("token=")[1].split(".")[0]) for x in (m, again)]
    assert all(e % 60 == 0 for e in expiries) and expiries[1] - expiries[0] <= 60
