"""WhatsApp Business Cloud API channel (ticketing requirements §18; open decision 12).

Outbound
  Business-initiated messages go only to users who opted in. Inside WhatsApp's
  24-hour customer-service window (the user wrote to us recently) a plain text
  message is sent; outside it, the approved utility template
  ``settings.whatsapp_template`` with {{1}} = title and {{2}} = body.

Inbound (webhook)
  * delivery receipts (sent / delivered / read / failed) update the notification delivery log;
  * replies to a ticket update, or messages quoting a ticket number, are added
    to that ticket's conversation as the customer (or assignee);
  * STOP / START change consent; STATUS returns the ticket's status.

With ``GP_WHATSAPP_PROVIDER=log`` (the default) messages are only logged, so
development and tests never call Meta.
"""

import hashlib
import hmac
import json
import logging
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import NotificationDelivery, Ticket, User, WhatsAppMessage
from app.models.base import utcnow

log = logging.getLogger("greenplot.whatsapp")

SESSION_WINDOW = timedelta(hours=24)
TICKET_RE = re.compile(r"\bGP-TKT-\d{4}-\d{6}\b", re.I)
STOP_WORDS = {"STOP", "UNSUBSCRIBE", "STOP ALL"}
START_WORDS = {"START", "SUBSCRIBE", "YES"}
RECEIPT_STATUSES = {"sent", "delivered", "read", "failed"}


class WhatsAppError(Exception):
    pass


# --------------------------------------------------------------------------- transport


def _http_post(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - fixed https endpoint from settings
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        try:
            err = json.loads(detail).get("error", {})
            detail = f"{err.get('code')} {err.get('message')}".strip()
        except (ValueError, AttributeError):
            pass
        raise WhatsAppError(f"HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise WhatsAppError(str(e)) from e


_transport: Callable[[dict], dict] | None = None


def set_transport(fn: Callable[[dict], dict] | None) -> None:
    """Override the HTTP call (tests)."""
    global _transport
    _transport = fn


def _post(payload: dict) -> dict:
    if _transport is not None:
        return _transport(payload)
    s = get_settings()
    if not (s.whatsapp_access_token and s.whatsapp_phone_number_id):
        raise WhatsAppError("WhatsApp is not configured (GP_WHATSAPP_ACCESS_TOKEN / GP_WHATSAPP_PHONE_NUMBER_ID)")
    url = f"{s.whatsapp_api_url}/{s.whatsapp_api_version}/{s.whatsapp_phone_number_id}/messages"
    return _http_post(url, s.whatsapp_access_token, payload)


def enabled() -> bool:
    s = get_settings()
    return s.whatsapp_provider == "meta" or _transport is not None


# --------------------------------------------------------------------------- helpers


def normalize_phone(raw: str | None) -> str | None:
    """Digits-only international number, e.g. '98450 12345' -> '919845012345'."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    cc = get_settings().default_country_code
    if len(digits) == 10:
        return cc + digits
    if len(digits) == 11 and digits.startswith("0"):
        return cc + digits[1:]
    if 11 <= len(digits) <= 15:
        return digits
    return None


def _clean_param(text: str, limit: int) -> str:
    # Template parameters may not contain newlines, tabs or 4+ consecutive spaces.
    t = re.sub(r"\s+", " ", text or "").strip() or "-"
    return t[: limit - 1] + "…" if len(t) > limit else t


def in_session(user: User) -> bool:
    last = user.whatsapp_last_inbound_at
    return bool(last and utcnow() - last < SESSION_WINDOW)


def text_payload(phone: str, text: str, reply_to: str | None = None) -> dict:
    p = {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": text[:4096], "preview_url": False}}
    if reply_to:
        p["context"] = {"message_id": reply_to}
    return p


def template_payload(phone: str, title: str, body: str | None) -> dict:
    s = get_settings()
    return {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": s.whatsapp_template,
            "language": {"code": s.whatsapp_template_language},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": _clean_param(title, 200)},
                        {"type": "text", "text": _clean_param(body or "", 800)},
                    ],
                }
            ],
        },
    }


def _message_id(resp: dict) -> str | None:
    msgs = resp.get("messages") or []
    return msgs[0].get("id") if msgs else None


# --------------------------------------------------------------------------- outbound


def send_notification(user: User, title: str, body: str | None) -> tuple[str, str | None]:
    """Channel adapter entry point. Returns (result, provider_message_id)."""
    if not user.whatsapp_opt_in:
        return "skipped:not_opted_in", None
    phone = normalize_phone(user.phone)
    if not phone:
        return "skipped:no_phone", None
    if not enabled():
        log.info("[whatsapp:log] -> %s: %s", phone, title)
        return "sent", None
    if in_session(user):
        text = f"*{title}*" + (f"\n{body}" if body else "")
        payload = text_payload(phone, text)
    else:
        payload = template_payload(phone, title, body)
    try:
        resp = _post(payload)
    except WhatsAppError as e:
        return f"failed:{e}", None
    return "sent", _message_id(resp)


def send_text(db: Session, phone: str, text: str, user: User | None = None, ticket_id=None, reply_to: str | None = None) -> None:
    """Free-form reply inside the 24-hour window (answers to inbound messages)."""
    row = WhatsAppMessage(
        tenant_id=user.tenant_id if user else None,
        user_id=user.id if user else None,
        direction="out",
        phone=phone,
        body=text,
        ticket_id=ticket_id,
        status="sent",
    )
    if enabled():
        try:
            row.wamid = _message_id(_post(text_payload(phone, text, reply_to)))
        except WhatsAppError as e:
            row.status, row.error = "failed", str(e)
    else:
        log.info("[whatsapp:log] -> %s: %s", phone, text)
    db.add(row)


# --------------------------------------------------------------------------- webhook


def verify_signature(raw: bytes, header: str | None) -> bool:
    secret = get_settings().whatsapp_app_secret
    if not secret:
        return get_settings().environment != "production" and get_settings().whatsapp_provider != "meta"
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def handle_webhook(db: Session, payload: dict) -> dict:
    counts = {"statuses": 0, "messages": 0}
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for st in value.get("statuses") or []:
                counts["statuses"] += _apply_status(db, st)
            for msg in value.get("messages") or []:
                counts["messages"] += _handle_inbound(db, msg)
    db.commit()
    return counts


def _apply_status(db: Session, st: dict) -> int:
    wamid, status = st.get("id"), st.get("status")
    if not wamid or status not in RECEIPT_STATUSES:
        return 0
    now = utcnow()
    errors = st.get("errors") or []
    reason = None
    if errors:
        e = errors[0]
        reason = e.get("title") or e.get("message") or str(e.get("code"))
    n = 0
    for d in db.scalars(select(NotificationDelivery).where(NotificationDelivery.provider_message_id == wamid)):
        order = ["sent", "delivered", "read"]
        if status == "failed":
            d.status, d.failure_reason = "failed", reason
        elif d.status not in order or order.index(status) > order.index(d.status):
            d.status = status  # receipts can arrive out of order; never step backwards
        if status in ("delivered", "read"):
            d.delivered_at = d.delivered_at or now
        n += 1
    for m in db.scalars(select(WhatsAppMessage).where(WhatsAppMessage.wamid == wamid, WhatsAppMessage.direction == "out")):
        m.status = status
        m.error = reason
        n += 1
    return 1 if n else 0


def _inbound_text(msg: dict) -> str:
    kind = msg.get("type")
    if kind == "text":
        return (msg.get("text") or {}).get("body", "")
    if kind == "button":
        return (msg.get("button") or {}).get("text", "")
    if kind == "interactive":
        i = msg.get("interactive") or {}
        return (i.get("button_reply") or i.get("list_reply") or {}).get("title", "")
    return ""


def users_for_phone(db: Session, phone: str) -> list[User]:
    tail = phone[-10:]
    candidates = db.scalars(select(User).where(User.is_active.is_(True), User.phone.ilike(f"%{tail[-4:]}%")))
    return [u for u in candidates if normalize_phone(u.phone) == phone]


def _ticket_for(db: Session, msg: dict, text: str, users: list[User]) -> Ticket | None:
    tenants = {u.tenant_id for u in users}
    ctx = (msg.get("context") or {}).get("id")
    if ctx:
        d = db.scalar(select(NotificationDelivery).where(NotificationDelivery.provider_message_id == ctx))
        if d and d.entity_type == "ticket" and d.entity_id:
            t = db.get(Ticket, d.entity_id)
            if t and t.tenant_id in tenants:
                return t
    m = TICKET_RE.search(text)
    if m:
        return db.scalar(
            select(Ticket).where(Ticket.number == m.group(0).upper(), Ticket.tenant_id.in_(tenants), Ticket.deleted_at.is_(None))
        )
    from app.services.tickets import ACTIVE

    mine = list(
        db.scalars(
            select(Ticket).where(
                Ticket.customer_id.in_([u.id for u in users]),
                Ticket.status.in_([s.value for s in ACTIVE]),
                Ticket.deleted_at.is_(None),
            )
        )
    )
    return mine[0] if len(mine) == 1 else None


def _handle_inbound(db: Session, msg: dict) -> int:
    from app.core.deps import Actor
    from app.services import tickets as tsvc
    from app.services.access import can_view_ticket, is_ticket_assignee

    wamid = msg.get("id")
    if not wamid or db.scalar(select(WhatsAppMessage.id).where(WhatsAppMessage.wamid == wamid)):
        return 0  # webhook replay
    phone = normalize_phone(msg.get("from"))
    if not phone:
        return 0
    text = _inbound_text(msg).strip()
    users = users_for_phone(db, phone)
    row = WhatsAppMessage(direction="in", wamid=wamid, phone=phone, body=text or f"[{msg.get('type')}]", status="received")
    db.add(row)
    if not users:
        row.status = "ignored"
        log.info("whatsapp from unknown number %s", phone)
        return 1
    now = utcnow()
    for u in users:
        u.whatsapp_last_inbound_at = now
    row.user_id, row.tenant_id = users[0].id, users[0].tenant_id
    command = text.upper()

    if command in STOP_WORDS:
        for u in users:
            u.whatsapp_opt_in = False
        row.status = "handled"
        send_text(db, phone, "You will no longer receive GreenPlot updates on WhatsApp. Reply START to turn them back on.", users[0])
        return 1
    if command in START_WORDS:
        for u in users:
            u.whatsapp_opt_in, u.whatsapp_opt_in_at = True, now
        row.status = "handled"
        send_text(db, phone, "WhatsApp updates are on. Reply STOP at any time to turn them off.", users[0])
        return 1

    ticket = _ticket_for(db, msg, text, users)
    user = next((u for u in users if ticket and u.tenant_id == ticket.tenant_id), None)
    actor = Actor(user=user, ip=None, user_agent="whatsapp") if user else None
    if ticket is None or actor is None or not can_view_ticket(db, actor, ticket):
        row.status = "ignored"
        base = get_settings().public_base_url.rstrip("/")
        send_text(
            db,
            phone,
            "Hello from GreenPlot. To add to a request, reply to its update message or include the ticket number "
            f"(for example GP-TKT-2026-000123). To raise a new request, open {base}/tickets",
            users[0],
        )
        return 1
    row.ticket_id, row.tenant_id, row.user_id = ticket.id, ticket.tenant_id, user.id

    if command in ("STATUS", ticket.number.upper()) or not text:
        row.status = "handled"
        who = tsvc.assignee_name(db, ticket)
        reply = f"{ticket.number}: {ticket.status.replace('_', ' ')}" + (f", with {who}" if who else "")
        if not text:
            reply += ". Photos and files can be added in the app."
        send_text(db, phone, reply, user, ticket.id, reply_to=wamid)
        return 1

    visibility = "customer"
    if is_ticket_assignee(actor, ticket) and not tsvc.setting(db, ticket.tenant_id, "ticket_assignee_customer_chat"):
        visibility = "vendor"
    try:
        tsvc.add_comment(db, actor, ticket, f"{text}\n\n(via WhatsApp)", visibility)
    except Exception as e:  # e.g. ticket closed
        row.status, row.error = "ignored", getattr(e, "detail", str(e))
        send_text(
            db, phone, f"{ticket.number} is {ticket.status}; your message was not added. {row.error}", user, ticket.id, reply_to=wamid
        )
        return 1
    row.status = "handled"
    send_text(db, phone, f"Added to {ticket.number}. We'll update you here.", user, ticket.id, reply_to=wamid)
    return 1
