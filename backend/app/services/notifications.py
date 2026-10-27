"""Notification fan-out (requirements §20, §39).

In-app notifications are stored rows. Push, SMS, WhatsApp and email go through
channel adapters; the defaults log the message so a provider (Firebase, MSG91,
WhatsApp Business API, SES...) can be plugged in without touching callers.

External channels are queued with the notification and sent once the caller's
transaction commits, on a small thread pool, so a slow provider never holds up
the request that triggered it (and a rolled-back change sends nothing). The
worker picks up anything left queued, for example after a restart.
"""

import logging
import uuid
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import event, or_, select
from sqlalchemy.orm import Session

from app.core.db import keep
from app.models import Notification, NotificationDelivery, Tenant, User
from app.models.base import utcnow
from app.models.enums import Role

log = logging.getLogger("greenplot.notify")

DEFAULT_CHANNELS: dict[str, list[str]] = {
    "task_assigned": ["in_app", "push"],
    "task_due": ["in_app", "push"],
    "task_overdue": ["in_app", "push"],
    "task_completed": ["in_app", "push"],
    "task_approved": ["in_app", "push"],
    "task_rework": ["in_app", "push"],
    "complaint_update": ["in_app", "push"],
    "payment_due": ["in_app", "sms"],
    "payment_success": ["in_app"],
    "incident": ["in_app", "push"],
    "sos": ["in_app", "push", "sms"],
    "announcement": ["in_app", "push"],
    "visitor": ["in_app", "push"],
    "ticket_update": ["in_app", "push", "whatsapp"],
    "ticket_assigned": ["in_app", "push", "whatsapp"],
    "ticket_closed": ["in_app", "push", "whatsapp"],
    "ticket_sla": ["in_app", "push"],
    "signup_request": ["in_app", "push"],
    "job_feedback": ["in_app", "push"],
    "low_rating": ["in_app", "push"],
    "job_proof": ["in_app", "push", "whatsapp", "email"],
    "plot_due": ["in_app", "push", "whatsapp", "email"],
    "plot_report": ["in_app", "whatsapp", "email"],
}

MAX_DELIVERY_ATTEMPTS = 3
LOW_RATING_THRESHOLD = 4  # ratings below this alert the layout office


class ChannelAdapter:
    name = "log"

    def send(self, user: User, title: str, body: str | None, data: dict | None = None) -> str:
        log.info("[%s] -> %s (%s): %s", self.name, user.email, user.phone, title)
        return "sent"


class PushAdapter(ChannelAdapter):
    """Phones registered at /devices, through Firebase Cloud Messaging (see app.services.push)."""

    name = "push"

    def send(self, user: User, title: str, body: str | None, data: dict | None = None) -> str:
        from app.services import push

        return push.send_to_user(user, title, body, data)


class SmsAdapter(ChannelAdapter):
    """MSG91 DLT template when GP_SMS_PROVIDER=msg91 (see app.services.sms), otherwise logs."""

    name = "sms"

    def send(self, user: User, title: str, body: str | None, data: dict | None = None) -> tuple[str, str | None]:
        from app.services import sms

        return sms.send_notification(user.phone, title, body)


class WhatsAppAdapter(ChannelAdapter):
    """WhatsApp Business Cloud API; see app.services.whatsapp (consent, 24-hour window, templates)."""

    name = "whatsapp"

    def send(self, user: User, title: str, body: str | None, data: dict | None = None) -> tuple[str, str | None]:
        from app.services import whatsapp

        return whatsapp.send_notification(user, title, body)


class EmailAdapter(ChannelAdapter):
    """SMTP when GP_SMTP_HOST is set (see app.services.messaging), otherwise logs."""

    name = "email"

    def send(self, user: User, title: str, body: str | None, data: dict | None = None) -> str:
        from app.core.config import get_settings
        from app.services.messaging import send_email

        return send_email(user.email, title, f"{body or title}\n\nOpen GreenPlot: {get_settings().app_url}")


ADAPTERS: dict[str, ChannelAdapter] = {
    "push": PushAdapter(),
    "sms": SmsAdapter(),
    "whatsapp": WhatsAppAdapter(),
    "email": EmailAdapter(),
}


def channels_for(db: Session, tenant_id: uuid.UUID, kind: str) -> list[str]:
    tenant = keep(db, db.get(Tenant, tenant_id))
    configured = ((tenant.settings or {}).get("notification_channels") or {}) if tenant else {}
    channels = configured.get(kind) or DEFAULT_CHANNELS.get(kind, ["in_app"])
    return list(dict.fromkeys(["in_app", *channels]))


def notify(
    db: Session,
    tenant_id: uuid.UUID,
    user_ids: Iterable[uuid.UUID | None],
    kind: str,
    title: str,
    body: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    channels: list[str] | None = None,
    send_now: bool = False,
) -> list[Notification]:
    """Store in-app notifications and queue the other channels.

    send_now=True sends external channels before returning, for callers that report the result
    (test messages, the owner's job photos that must follow the message in the chat).
    """
    chans = channels or channels_for(db, tenant_id, kind)
    created = []
    for uid in dict.fromkeys(u for u in user_ids if u):
        user = db.get(User, uid)
        if user is None or not user.is_active or user.tenant_id != tenant_id:
            continue
        n = Notification(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=uid,
            kind=kind,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
            channels=chans,
            delivery={},
        )
        delivery = {}
        for ch in chans:
            if ch == "in_app":
                result, provider_id = "stored", None
            elif send_now:
                result, provider_id = _send(ch, user, title, body, _push_data(n))
            else:
                result, provider_id = "queued", None
            delivery[ch] = result
            row = _delivery_row(n, ch, result, provider_id)
            db.add(row)
            if result == "queued":
                db.info.setdefault(_QUEUE_KEY, []).append(row.id)
        n.delivery = delivery
        db.add(n)
        created.append(n)
    return created


def _push_data(n: Notification) -> dict:
    """What a phone needs to open the right screen when the notification is tapped."""
    data = {"notification_id": str(n.id), "kind": n.kind}
    if n.entity_type and n.entity_id:
        data |= {"entity_type": n.entity_type, "entity_id": str(n.entity_id)}
    return data


def _send(channel: str, user: User, title: str, body: str | None, data: dict | None = None) -> tuple[str, str | None]:
    """Returns (result, provider message id). Adapters may return a plain result string."""
    adapter = ADAPTERS.get(channel)
    if adapter is None:
        return "unsupported", None
    try:
        out = adapter.send(user, title, body, data)
    except Exception as exc:  # provider failures must not break workflows
        log.warning("%s delivery to %s failed: %s", channel, user.id, exc)
        return f"failed:{exc}", None
    return out if isinstance(out, tuple) else (out, None)


def _delivery_row(n: Notification, channel: str, result: str, provider_id: str | None = None) -> NotificationDelivery:
    status, _, reason = result.partition(":")
    now = utcnow()
    if status == "queued":
        return NotificationDelivery(
            id=uuid.uuid4(),
            tenant_id=n.tenant_id,
            notification_id=n.id,
            user_id=n.user_id,
            event_type=n.kind,
            entity_type=n.entity_type,
            entity_id=n.entity_id,
            channel=channel,
            status="queued",
            attempts=0,
        )
    return NotificationDelivery(
        tenant_id=n.tenant_id,
        notification_id=n.id,
        user_id=n.user_id,
        event_type=n.kind,
        entity_type=n.entity_type,
        entity_id=n.entity_id,
        channel=channel,
        status=status if status in ("stored", "sent", "delivered", "skipped", "failed") else "failed",
        sent_at=now if status in ("stored", "sent", "delivered") else None,
        delivered_at=now if status in ("stored", "delivered") else None,
        failure_reason=reason or (None if status in ("stored", "sent", "delivered") else status),
        provider_message_id=provider_id,
    )


def _attempt(db: Session, d: NotificationDelivery) -> bool:
    """Send one queued or failed delivery and record the outcome on it and its notification."""
    user = db.get(User, d.user_id)
    note = db.get(Notification, d.notification_id)
    if user is None or note is None or not user.is_active:
        d.status, d.failure_reason = "skipped", "recipient unavailable"
        return False
    result, provider_id = _send(d.channel, user, note.title, note.body, _push_data(note))
    status, _, reason = result.partition(":")
    d.provider_message_id = provider_id or d.provider_message_id
    d.attempts += 1
    d.status = status if status in ("sent", "delivered", "skipped") else "failed"
    d.failure_reason = None if d.status in ("sent", "delivered") else (reason or status)
    if d.status in ("sent", "delivered"):
        d.sent_at = utcnow()
    note.delivery = {**(note.delivery or {}), d.channel: result}
    return True


def send_queued(db: Session, ids: Iterable[uuid.UUID]) -> int:
    """Send the given queued deliveries (rows already sent or gone are left alone)."""
    rows = list(
        db.scalars(
            select(NotificationDelivery)
            .where(NotificationDelivery.id.in_(list(ids)), NotificationDelivery.status == "queued")
            .with_for_update(skip_locked=True)
        )
    )
    for d in rows:
        _attempt(db, d)
    return len(rows)


QUEUED_GRACE = timedelta(minutes=2)  # leave fresh rows to the thread that queued them


def retry_failed_deliveries(db: Session) -> int:
    """Resend failed external-channel deliveries, up to MAX_DELIVERY_ATTEMPTS each, and send any left queued."""
    n = 0
    rows = db.scalars(
        select(NotificationDelivery)
        .where(
            or_(
                (NotificationDelivery.status == "failed") & (NotificationDelivery.attempts < MAX_DELIVERY_ATTEMPTS),
                (NotificationDelivery.status == "queued") & (NotificationDelivery.created_at < utcnow() - QUEUED_GRACE),
            )
        )
        .with_for_update(skip_locked=True)
    )
    for d in rows:
        if _attempt(db, d):
            n += 1
    return n


# --------------------------------------------------------------------------- sending after commit

_QUEUE_KEY = "queued_deliveries"
_pool: ThreadPoolExecutor | None = None


def _send_in_own_session(ids: list[uuid.UUID]) -> None:
    from app.core.db import SessionLocal

    try:
        with SessionLocal() as db:
            send_queued(db, ids)
            db.commit()
    except Exception:  # pragma: no cover - the worker retries what is left queued
        log.exception("sending %d queued notifications failed", len(ids))


@event.listens_for(Session, "after_commit")
def _dispatch_after_commit(session: Session) -> None:
    ids = session.info.pop(_QUEUE_KEY, None)
    if not ids:
        return
    from app.core.config import get_settings

    if get_settings().notify_in_background:
        global _pool
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="notify")
        _pool.submit(_send_in_own_session, ids)
    else:
        _send_in_own_session(ids)


@event.listens_for(Session, "after_rollback")
def _drop_queue(session: Session) -> None:
    session.info.pop(_QUEUE_KEY, None)


def users_with_roles(db: Session, tenant_id: uuid.UUID, roles: Iterable[str]) -> list[uuid.UUID]:
    return list(db.scalars(select(User.id).where(User.tenant_id == tenant_id, User.role.in_(list(roles)), User.is_active.is_(True))))


def managers(db: Session, tenant_id: uuid.UUID) -> list[uuid.UUID]:
    return users_with_roles(db, tenant_id, [Role.SUPERVISOR, Role.LAYOUT_ADMIN])


def vendor_users(db: Session, tenant_id: uuid.UUID, vendor_id: uuid.UUID | None) -> list[uuid.UUID]:
    if vendor_id is None:
        return []
    return list(db.scalars(select(User.id).where(User.tenant_id == tenant_id, User.vendor_id == vendor_id, User.is_active.is_(True))))


def alert_low_rating(
    db: Session, tenant_id: uuid.UUID, rating: int | None, comment: str | None, what: str, entity_type: str, entity_id: uuid.UUID
) -> list[Notification]:
    """Tell supervisors and admins about a customer rating below LOW_RATING_THRESHOLD so they can follow up."""
    if rating is None or rating >= LOW_RATING_THRESHOLD:
        return []
    body = f"Customer comment: {comment}" if comment else "The customer left no comment."
    return notify(db, tenant_id, managers(db, tenant_id), "low_rating", f"Low rating {rating}/5: {what}", body, entity_type, entity_id)
