"""WhatsApp Business channel: consent, templates vs session messages, receipts, two-way replies."""

import hashlib
import hmac
import json
from datetime import timedelta

import pytest

from app.core.config import get_settings
from app.models import NotificationDelivery, TicketComment, User, WhatsAppMessage
from app.models.base import utcnow
from app.services import notifications
from app.services import whatsapp as wa


@pytest.fixture()
def meta(monkeypatch):
    """Pretend to be the Meta Cloud API and record every request."""
    sent: list[dict] = []

    def transport(payload):
        sent.append(payload)
        return {"messages": [{"id": f"wamid.{len(sent)}"}]}

    wa.set_transport(transport)
    yield sent
    wa.set_transport(None)


def opt_in(db, user, phone="98450 12345"):
    u = db.get(User, user.id)
    u.phone, u.whatsapp_opt_in = phone, True
    db.commit()
    return u


def webhook(client, payload, secret=None):
    raw = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Hub-Signature-256"] = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/api/v1/webhooks/whatsapp", content=raw, headers=headers)


def inbound(wamid, text, phone="919845012345", context=None):
    msg = {"from": phone, "id": wamid, "type": "text", "text": {"body": text}}
    if context:
        msg["context"] = {"id": context}
    return {"entry": [{"changes": [{"value": {"messages": [msg]}}]}]}


def receipt(wamid, status, errors=None):
    st = {"id": wamid, "status": status, **({"errors": errors} if errors else {})}
    return {"entry": [{"changes": [{"value": {"statuses": [st]}}]}]}


def test_phone_normalisation():
    assert wa.normalize_phone("98450 12345") == "919845012345"
    assert wa.normalize_phone("09845012345") == "919845012345"
    assert wa.normalize_phone("+91 98450-12345") == "919845012345"
    assert wa.normalize_phone("+1 415 555 0100") == "14155550100"
    assert wa.normalize_phone("123") is None and wa.normalize_phone(None) is None


def test_consent_is_required_and_template_used_outside_session(world, db, meta):
    notifications.notify(db, world.ta.id, [world.resident.id], "ticket_update", "Hello", "Body", channels=["in_app", "whatsapp"])
    db.commit()
    assert meta == []  # not opted in
    row = db.query(NotificationDelivery).filter_by(channel="whatsapp").one()
    assert row.status == "skipped" and row.failure_reason == "not_opted_in"

    opt_in(db, world.resident)
    notifications.notify(db, world.ta.id, [world.resident.id], "ticket_update", "GP-TKT-2026-000001 resolved", "Line one\nline two")
    db.commit()
    assert len(meta) == 1
    p = meta[0]
    assert p["to"] == "919845012345" and p["type"] == "template"
    assert p["template"]["name"] == get_settings().whatsapp_template
    params = p["template"]["components"][0]["parameters"]
    assert [x["text"] for x in params] == ["GP-TKT-2026-000001 resolved", "Line one line two"]  # no newlines in params
    row = db.query(NotificationDelivery).filter_by(channel="whatsapp", status="sent").one()
    assert row.provider_message_id == "wamid.1"


def test_session_message_inside_24h_window(world, db, meta):
    u = opt_in(db, world.resident)
    u.whatsapp_last_inbound_at = utcnow() - timedelta(hours=2)
    db.commit()
    notifications.notify(db, world.ta.id, [u.id], "ticket_update", "Title", "Body", channels=["whatsapp"])
    assert meta[0]["type"] == "text" and meta[0]["text"]["body"] == "*Title*\nBody"


def test_provider_error_is_logged_and_retried(world, db):
    calls = []

    def flaky(payload):
        calls.append(payload)
        if len(calls) == 1:
            raise wa.WhatsAppError("HTTP 400: 131026 Message undeliverable")
        return {"messages": [{"id": "wamid.retry"}]}

    wa.set_transport(flaky)
    try:
        opt_in(db, world.resident)
        notifications.notify(db, world.ta.id, [world.resident.id], "ticket_closed", "Closed", "x", channels=["whatsapp"])
        db.commit()
        row = db.query(NotificationDelivery).one()
        assert row.status == "failed" and "131026" in row.failure_reason
        assert notifications.retry_failed_deliveries(db) == 1
        db.commit()
        assert row.status == "sent" and row.provider_message_id == "wamid.retry" and row.attempts == 2
    finally:
        wa.set_transport(None)


def test_webhook_verification_handshake(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_verify_token", "s3cret")
    ok = client.get("/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "s3cret", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    bad = client.get("/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"})
    assert bad.status_code == 403


def test_webhook_signature_is_enforced(client, world, monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", "appsecret")
    assert webhook(client, receipt("wamid.x", "delivered")).status_code == 401
    assert webhook(client, receipt("wamid.x", "delivered"), secret="wrong").status_code == 401
    assert webhook(client, receipt("wamid.x", "delivered"), secret="appsecret").status_code == 200


def test_delivery_receipts_update_the_log(client, world, db, meta):
    opt_in(db, world.resident)
    notifications.notify(db, world.ta.id, [world.resident.id], "ticket_closed", "Closed", "x", channels=["whatsapp"])
    db.commit()
    webhook(client, receipt("wamid.1", "read"))
    webhook(client, receipt("wamid.1", "delivered"))  # late receipt must not step backwards
    db.expire_all()
    row = db.query(NotificationDelivery).filter_by(provider_message_id="wamid.1").one()
    assert row.status == "read" and row.delivered_at is not None
    webhook(client, receipt("wamid.1", "failed", [{"code": 131047, "title": "Re-engagement message"}]))
    db.expire_all()
    row = db.query(NotificationDelivery).filter_by(provider_message_id="wamid.1").one()
    assert row.status == "failed" and row.failure_reason == "Re-engagement message"


def test_customer_reply_on_whatsapp_becomes_a_ticket_comment(client, as_, world, db, meta):
    opt_in(db, world.resident)
    resident, admin = as_(world.resident), as_(world.admin)
    t = resident.ok(
        "post",
        "/tickets",
        {"category": "plumbing", "title": "Leak", "description": "Leak at the meter", "property_id": str(world.p117.id)},
    )
    assert any(p["type"] == "template" for p in meta)  # "Ticket created" went out on WhatsApp
    wamid = db.query(NotificationDelivery).filter(NotificationDelivery.provider_message_id.is_not(None)).first().provider_message_id

    # Reply to the update message → comment on that ticket, threaded acknowledgement.
    assert webhook(client, inbound("wamid.in1", "It is getting worse", context=wamid)).status_code == 200
    detail = admin.ok("get", f"/tickets/{t['id']}")
    c = [x for x in detail["comments"] if "getting worse" in x["message"]]
    assert c and c[0]["author_name"] == "Priya Owner" and c[0]["visibility"] == "customer"
    ack = meta[-1]
    assert ack["type"] == "text" and t["number"] in ack["text"]["body"] and ack["context"]["message_id"] == "wamid.in1"

    # Replays of the same webhook are ignored.
    webhook(client, inbound("wamid.in1", "It is getting worse", context=wamid))
    db.expire_all()
    assert db.query(TicketComment).filter(TicketComment.message.like("%getting worse%")).count() == 1

    # A message quoting the ticket number works without replying; STATUS returns the status.
    webhook(client, inbound("wamid.in2", f"{t['number']} the plumber did not come"))
    assert any("plumber did not come" in x["message"] for x in admin.ok("get", f"/tickets/{t['id']}")["comments"])
    webhook(client, inbound("wamid.in3", "status"))
    assert meta[-1]["text"]["body"].startswith(f"{t['number']}: open")

    # The 24-hour window is now open, so the next update is a plain text message.
    db.expire_all()
    assert db.get(User, world.resident.id).whatsapp_last_inbound_at is not None


def test_stop_start_and_unknown_numbers(client, world, db, meta):
    opt_in(db, world.resident)
    webhook(client, inbound("wamid.s1", "STOP"))
    db.expire_all()
    assert db.get(User, world.resident.id).whatsapp_opt_in is False
    assert "no longer receive" in meta[-1]["text"]["body"]
    webhook(client, inbound("wamid.s2", "start"))
    db.expire_all()
    assert db.get(User, world.resident.id).whatsapp_opt_in is True

    n = len(meta)
    webhook(client, inbound("wamid.u1", "hello", phone="919999999999"))
    db.expire_all()
    assert len(meta) == n  # strangers get no reply
    assert db.query(WhatsAppMessage).filter_by(wamid="wamid.u1").one().status == "ignored"


def test_message_with_no_matching_ticket_gets_help(client, world, db, meta):
    opt_in(db, world.resident)
    webhook(client, inbound("wamid.h1", "hi"))
    assert "ticket number" in meta[-1]["text"]["body"]


def test_cannot_comment_on_someone_elses_ticket(client, as_, world, db, meta):
    """Quoting another customer's ticket number must not post to it."""
    t = as_(world.resident2).ok("post", "/tickets", {"category": "plumbing", "title": "Leak", "description": "Leak"})
    opt_in(db, world.resident)
    webhook(client, inbound("wamid.x1", f"{t['number']} hello"))
    db.expire_all()
    assert db.query(TicketComment).filter(TicketComment.message.like("%hello%")).count() == 0


def test_consent_endpoint_and_admin_status(as_, world, db, meta):
    resident, admin = as_(world.resident), as_(world.admin)
    r = resident.put("/whatsapp/consent", json={"whatsapp_opt_in": True})
    assert r.status_code == 422  # no phone on file
    out = resident.ok("put", "/whatsapp/consent", {"whatsapp_opt_in": True, "phone": "98450 12345"})
    assert out == {"whatsapp_opt_in": True, "phone": "98450 12345"}
    assert resident.ok("get", "/auth/me")["whatsapp_opt_in"] is True
    assert resident.get("/whatsapp/status").status_code == 403

    st = admin.ok("get", "/whatsapp/status")
    assert st["opted_in_users"] == 1 and st["live"] is True and st["webhook_path"] == "/api/v1/webhooks/whatsapp"
    admin.ok("put", "/whatsapp/consent", {"whatsapp_opt_in": True, "phone": "9000000099"})
    assert admin.ok("post", "/whatsapp/test", {})["result"] == "sent"
    assert meta[-1]["to"] == "919000000099"
