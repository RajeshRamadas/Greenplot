"""WhatsApp channel: Meta webhook, layout status and the user's own consent."""

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.v1._util import user_names
from app.core.config import get_settings
from app.core.deps import DB, CurrentActor, Perm
from app.models import User, WhatsAppMessage
from app.services import audit, notifications
from app.services import whatsapp as wa

router = APIRouter(tags=["whatsapp"])


@router.get("/webhooks/whatsapp", response_class=PlainTextResponse)
def verify_webhook(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
):
    """Meta's subscription handshake: echo the challenge when the verify token matches."""
    expected = get_settings().whatsapp_verify_token
    if mode != "subscribe" or not expected or token != expected:
        raise HTTPException(403, "Verification failed")
    return challenge


@router.post("/webhooks/whatsapp")
async def receive_webhook(request: Request, db: DB, x_hub_signature_256: str | None = Header(None)):
    """Delivery receipts and inbound messages. Signed with the app secret; replays are ignored."""
    raw = await request.body()
    if not wa.verify_signature(raw, x_hub_signature_256):
        raise HTTPException(401, "Invalid signature")
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    return wa.handle_webhook(db, payload)


class TestIn(BaseModel):
    message: str | None = None


@router.get("/whatsapp/status")
def status(db: DB, actor: Perm("settings.manage")):
    s = get_settings()
    opted = db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == actor.tenant_id, User.whatsapp_opt_in.is_(True), User.is_active.is_(True))
    )
    rows = list(
        db.scalars(
            select(WhatsAppMessage)
            .where(WhatsAppMessage.tenant_id == actor.tenant_id)
            .order_by(WhatsAppMessage.created_at.desc())
            .limit(30)
        )
    )
    names = user_names(db, (r.user_id for r in rows))
    pid = s.whatsapp_phone_number_id or ""
    return {
        "provider": s.whatsapp_provider,
        "live": wa.enabled(),
        "configured": bool(s.whatsapp_access_token and s.whatsapp_phone_number_id),
        "webhook_secured": bool(s.whatsapp_app_secret),
        "phone_number_id": f"…{pid[-4:]}" if pid else None,
        "template": s.whatsapp_template,
        "template_language": s.whatsapp_template_language,
        "business_number": s.whatsapp_number,
        "opted_in_users": opted or 0,
        "webhook_path": f"{s.api_prefix}/webhooks/whatsapp",
        "events": {k: notifications.channels_for(db, actor.tenant_id, k) for k in notifications.DEFAULT_CHANNELS},
        "recent": [
            {
                "at": r.created_at,
                "direction": r.direction,
                "user_name": names.get(r.user_id),
                "phone": f"…{r.phone[-4:]}",
                "body": r.body,
                "status": r.status,
                "error": r.error,
                "ticket_id": r.ticket_id,
            }
            for r in rows
        ],
    }


@router.post("/whatsapp/test")
def send_test(body: TestIn, db: DB, actor: Perm("settings.manage")):
    """Send a test notification to yourself over WhatsApp (you must have opted in)."""
    sent = notifications.notify(
        db,
        actor.tenant_id,
        [actor.id],
        "announcement",
        "GreenPlot test message",
        body.message or "WhatsApp notifications are working for your layout.",
        channels=["in_app", "whatsapp"],
    )
    db.commit()
    result = sent[0].delivery.get("whatsapp") if sent else "not_sent"
    return {"result": result}


@router.get("/whatsapp/info")
def info(actor: CurrentActor):
    """What a user needs to opt in: our business number and whether WhatsApp is live."""
    s = get_settings()
    return {"business_number": s.whatsapp_number, "live": wa.enabled(), "opted_in": actor.user.whatsapp_opt_in}


class ConsentIn(BaseModel):
    whatsapp_opt_in: bool
    phone: str | None = None


@router.put("/whatsapp/consent")
def consent(body: ConsentIn, db: DB, actor: CurrentActor):
    """The user's own consent to receive WhatsApp updates."""
    u = actor.user
    if body.phone is not None and wa.normalize_phone(body.phone) != wa.normalize_phone(u.phone):
        # A self-service number change must be proven with a code (/auth/phone/request + /confirm),
        # because the number is also used for phone sign-in.
        raise HTTPException(422, "Verify your new mobile number first")
    if body.whatsapp_opt_in and not wa.normalize_phone(u.phone):
        raise HTTPException(422, "Add your mobile number to receive WhatsApp updates")
    old = u.whatsapp_opt_in
    u.whatsapp_opt_in = body.whatsapp_opt_in
    if body.whatsapp_opt_in and not old:
        from app.models.base import utcnow

        u.whatsapp_opt_in_at = utcnow()
    audit.record(db, actor, "user.whatsapp_consent", "user", u.id, old={"opt_in": old}, new={"opt_in": body.whatsapp_opt_in})
    db.commit()
    return {"whatsapp_opt_in": u.whatsapp_opt_in, "phone": u.phone}
