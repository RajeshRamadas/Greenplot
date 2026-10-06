"""SMS through MSG91: DLT template payloads, fallbacks, delivery reports and admin endpoints."""

import pytest

from app.core.config import get_settings
from app.models import NotificationDelivery, User
from app.services import notifications
from app.services import sms as sms_svc


@pytest.fixture()
def msg91(monkeypatch):
    """Pretend to be MSG91 and record every Flow API call."""
    s = get_settings()
    monkeypatch.setattr(s, "msg91_otp_template_id", "tpl-otp")
    monkeypatch.setattr(s, "msg91_notify_template_id", "tpl-notify")
    monkeypatch.setattr(s, "msg91_link_template_id", "tpl-link")
    monkeypatch.setattr(s, "msg91_sender", "GRNPLT")
    calls: list[tuple[str, dict]] = []

    def transport(path, payload):
        calls.append((path, payload))
        return {"type": "success", "message": f"req-{len(calls)}"}

    sms_svc.set_transport(transport)
    yield calls
    sms_svc.set_transport(None)


def test_flow_payloads_use_dlt_templates(msg91):
    assert sms_svc.send_otp("98450 12345", "123456") == ("sent", "req-1")
    path, p = msg91[0]
    assert path == "flow" and p["template_id"] == "tpl-otp" and p["sender"] == "GRNPLT"
    assert p["recipients"] == [{"mobiles": "919845012345", "otp": "123456"}]

    sms_svc.send_notification("9845012345", "GP-TKT-2026-000001 resolved — please confirm", "Line one\nline two is quite long indeed")
    r = msg91[1][1]["recipients"][0]
    assert msg91[1][1]["template_id"] == "tpl-notify"
    assert len(r["title"]) <= 30 and len(r["body"]) <= 30 and "\n" not in r["body"]  # DLT variable limit

    link = "https://app.greenplot.in/accept-invite?token=" + "x" * 43
    sms_svc.send_link("9845012345", "Your GreenPlot invitation", link)
    assert msg91[2][1]["template_id"] == "tpl-link" and msg91[2][1]["recipients"][0]["link"] == link  # links never trimmed


def test_errors_and_missing_config(msg91, monkeypatch):
    assert sms_svc.send_otp("123", "1") == ("skipped:no_phone", None)
    monkeypatch.setattr(get_settings(), "msg91_link_template_id", None)
    assert sms_svc.send_link("9845012345", "t", "https://x")[0] == "skipped:no_template"

    sms_svc.set_transport(lambda path, p: {"type": "error", "message": "Invalid template"})
    assert sms_svc.send_otp("9845012345", "111111") == ("failed:Invalid template", None)

    def boom(path, p):
        raise sms_svc.SmsError("HTTP 401: unauthorised")

    sms_svc.set_transport(boom)
    assert sms_svc.send_notification("9845012345", "t", "b")[0] == "failed:HTTP 401: unauthorised"


def test_notification_sms_is_logged_and_tracked_by_delivery_report(client, world, db, msg91):
    notifications.notify(db, world.ta.id, [world.staff.id], "payment_due", "Dues reminder", "₹2,000 due", channels=["in_app", "sms"])
    db.commit()
    row = db.query(NotificationDelivery).filter_by(channel="sms").one()
    assert row.status == "sent" and row.provider_message_id == "req-1"

    # MSG91 posts delivery reports; the token in the URL is required once configured.
    get_settings().msg91_webhook_token = "dlr-secret"
    try:
        report = [{"requestId": "req-1", "report": [{"number": "919000000001", "status": "1", "desc": "DELIVERED"}]}]
        assert client.post("/api/v1/webhooks/msg91", json=report).status_code == 401
        assert client.post("/api/v1/webhooks/msg91?token=wrong", json=report).status_code == 401
        assert client.post("/api/v1/webhooks/msg91?token=dlr-secret", json=report).json() == {"updated": 1}
        db.expire_all()
        row = db.query(NotificationDelivery).filter_by(channel="sms").one()
        assert row.status == "delivered" and row.delivered_at is not None

        failed = {"data": [{"request_id": "req-1", "report": [{"desc": "NDNC Rejected"}]}]}
        client.post("/api/v1/webhooks/msg91?token=dlr-secret", json=failed)
        db.expire_all()
        row = db.query(NotificationDelivery).filter_by(channel="sms").one()
        assert row.status == "failed" and row.failure_reason == "NDNC Rejected"
    finally:
        get_settings().msg91_webhook_token = None


def test_codes_fall_back_to_sms_when_whatsapp_is_off(client, world, msg91):
    r = client.post("/api/v1/auth/password/forgot", json={"identifier": "9000000001"}).json()
    assert r["channels"] == ["sms"]
    assert msg91[-1][1]["template_id"] == "tpl-otp" and msg91[-1][1]["recipients"][0]["otp"] == r["dev_code"]


def test_invites_use_the_link_template(as_, world, msg91):
    out = as_(world.admin).ok(
        "post", "/users", {"email": "sms.staff@gv.in", "full_name": "Sms Staff", "role": "staff", "phone": "9845066666"}
    )
    assert "sms" in out["sent_via"]
    path, p = msg91[-1]
    assert p["template_id"] == "tpl-link" and p["recipients"][0]["link"] == out["invite_url"]


def test_admin_status_and_test_send(as_, world, db, msg91):
    admin = as_(world.admin)
    st = admin.ok("get", "/sms/status")
    assert st["live"] is True and st["templates"] == {"otp": True, "notify": True, "link": True}
    assert as_(world.resident).get("/sms/status").status_code == 403
    assert admin.post("/sms/test", json={}).status_code == 422  # admin has no phone yet
    assert admin.ok("post", "/sms/test", {"phone": "9845077777"}) == {"result": "sent", "request_id": f"req-{len(msg91)}"}
    db.get(User, world.admin.id).phone = "9845077777"
    db.commit()
    assert admin.ok("post", "/sms/test", {})["result"] == "sent"
