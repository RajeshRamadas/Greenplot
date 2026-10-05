"""Notification fan-out (requirements §20, §39).

In-app notifications are stored rows. Push, SMS, WhatsApp and email go through
channel adapters; the defaults log the message so a provider (Firebase, MSG91,
WhatsApp Business API, SES...) can be plugged in without touching callers.
"""

import logging
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    "ticket_update": ["in_app", "push"],
    "ticket_assigned": ["in_app", "push", "sms"],
    "ticket_closed": ["in_app", "push", "whatsapp"],
    "ticket_sla": ["in_app", "push"],
}

MAX_DELIVERY_ATTEMPTS = 3


class ChannelAdapter:
    name = "log"

    def send(self, user: User, title: str, body: str | None) -> str:
        log.info("[%s] -> %s (%s): %s", self.name, user.email, user.phone, title)
        return "sent"


class PushAdapter(ChannelAdapter):
    name = "push"


class SmsAdapter(ChannelAdapter):
    name = "sms"

    def send(self, user: User, title: str, body: str | None) -> str:
        if not user.phone:
            return "skipped:no_phone"
        return super().send(user, title, body)


class WhatsAppAdapter(SmsAdapter):
    name = "whatsapp"


class EmailAdapter(ChannelAdapter):
    name = "email"


ADAPTERS: dict[str, ChannelAdapter] = {
    "push": PushAdapter(),
    "sms": SmsAdapter(),
    "whatsapp": WhatsAppAdapter(),
    "email": EmailAdapter(),
}


def channels_for(db: Session, tenant_id: uuid.UUID, kind: str) -> list[str]:
    tenant = db.get(Tenant, tenant_id)
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
) -> list[Notification]:
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
            result = "stored" if ch == "in_app" else _send(ch, user, title, body)
            delivery[ch] = result
            db.add(_delivery_row(n, ch, result))
        n.delivery = delivery
        db.add(n)
        created.append(n)
    return created


def _send(channel: str, user: User, title: str, body: str | None) -> str:
    adapter = ADAPTERS.get(channel)
    if adapter is None:
        return "unsupported"
    try:
        return adapter.send(user, title, body)
    except Exception as exc:  # provider failures must not break workflows
        log.warning("%s delivery to %s failed: %s", channel, user.id, exc)
        return f"failed:{exc}"


def _delivery_row(n: Notification, channel: str, result: str) -> NotificationDelivery:
    status, _, reason = result.partition(":")
    now = utcnow()
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
    )


def retry_failed_deliveries(db: Session) -> int:
    """Resend failed external-channel deliveries, up to MAX_DELIVERY_ATTEMPTS each."""
    n = 0
    rows = db.scalars(
        select(NotificationDelivery).where(NotificationDelivery.status == "failed", NotificationDelivery.attempts < MAX_DELIVERY_ATTEMPTS)
    )
    for d in rows:
        user = db.get(User, d.user_id)
        note = db.get(Notification, d.notification_id)
        if user is None or note is None or not user.is_active:
            continue
        result = _send(d.channel, user, note.title, note.body)
        status, _, reason = result.partition(":")
        d.attempts += 1
        d.status = status if status in ("sent", "delivered", "skipped") else "failed"
        d.failure_reason = (reason or status) if d.status == "failed" else None
        if d.status in ("sent", "delivered"):
            d.sent_at = utcnow()
        note.delivery = {**(note.delivery or {}), d.channel: result}
        n += 1
    return n


def users_with_roles(db: Session, tenant_id: uuid.UUID, roles: Iterable[str]) -> list[uuid.UUID]:
    return list(db.scalars(select(User.id).where(User.tenant_id == tenant_id, User.role.in_(list(roles)), User.is_active.is_(True))))


def managers(db: Session, tenant_id: uuid.UUID) -> list[uuid.UUID]:
    return users_with_roles(db, tenant_id, [Role.SUPERVISOR, Role.LAYOUT_ADMIN])


def vendor_users(db: Session, tenant_id: uuid.UUID, vendor_id: uuid.UUID | None) -> list[uuid.UUID]:
    if vendor_id is None:
        return []
    return list(db.scalars(select(User.id).where(User.tenant_id == tenant_id, User.vendor_id == vendor_id, User.is_active.is_(True))))
