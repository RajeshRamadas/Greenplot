"""SMS channel (MSG91): delivery-report webhook and the layout admin's status/test."""

import hmac

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.deps import DB, Perm
from app.services import notifications
from app.services import sms as sms_svc
from app.services.whatsapp import normalize_phone

router = APIRouter(tags=["sms"])


def _token_ok(token: str | None) -> bool:
    s = get_settings()
    if not s.msg91_webhook_token:
        return s.environment != "production" and s.sms_provider != "msg91"
    return bool(token) and hmac.compare_digest(token, s.msg91_webhook_token)


@router.post("/webhooks/msg91")
async def msg91_delivery_report(request: Request, db: DB, token: str | None = Query(None)):
    """MSG91 DLR webhook. Configure it in MSG91 as …/api/v1/webhooks/msg91?token=<GP_MSG91_WEBHOOK_TOKEN>."""
    if not _token_ok(token):
        raise HTTPException(401, "Invalid token")
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    return {"updated": sms_svc.handle_dlr(db, payload)}


@router.get("/sms/status")
def status(actor: Perm("settings.manage")):
    s = get_settings()
    return {
        "provider": s.sms_provider,
        "live": sms_svc.enabled(),
        "configured": bool(s.msg91_authkey),
        "sender": s.msg91_sender,
        "templates": {
            "otp": bool(s.msg91_otp_template_id),
            "notify": bool(s.msg91_notify_template_id),
            "link": bool(s.msg91_link_template_id),
        },
        "webhook_secured": bool(s.msg91_webhook_token),
        "webhook_path": f"{s.api_prefix}/webhooks/msg91?token=…",
        "var_max": s.msg91_var_max,
    }


class SmsTestIn(BaseModel):
    phone: str | None = Field(None, max_length=30)


@router.post("/sms/test")
def send_test(body: SmsTestIn, db: DB, actor: Perm("settings.manage")):
    """Send a test SMS (notification template) to the given number or your own."""
    phone = body.phone or actor.user.phone
    if not normalize_phone(phone):
        raise HTTPException(422, "Enter a valid mobile number, or add one to your profile")
    if body.phone:
        result, rid = sms_svc.send_notification(phone, "Test message", "SMS is working for your layout")
        return {"result": result, "request_id": rid}
    sent = notifications.notify(
        db, actor.tenant_id, [actor.id], "announcement", "Test message", "SMS is working for your layout", channels=["in_app", "sms"]
    )
    db.commit()
    return {"result": sent[0].delivery.get("sms") if sent else "not_sent"}
