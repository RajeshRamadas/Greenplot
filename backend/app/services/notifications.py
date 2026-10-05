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

from app.models import Notification, Tenant, User
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
}


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
        delivery = {}
        for ch in chans:
            if ch == "in_app":
                delivery[ch] = "stored"
                continue
            adapter = ADAPTERS.get(ch)
            try:
                delivery[ch] = adapter.send(user, title, body) if adapter else "unsupported"
            except Exception as exc:  # pragma: no cover - provider failures must not break workflows
                delivery[ch] = f"failed:{exc}"
        n = Notification(
            tenant_id=tenant_id,
            user_id=uid,
            kind=kind,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
            channels=chans,
            delivery=delivery,
        )
        db.add(n)
        created.append(n)
    return created


def users_with_roles(db: Session, tenant_id: uuid.UUID, roles: Iterable[str]) -> list[uuid.UUID]:
    return list(db.scalars(select(User.id).where(User.tenant_id == tenant_id, User.role.in_(list(roles)), User.is_active.is_(True))))


def managers(db: Session, tenant_id: uuid.UUID) -> list[uuid.UUID]:
    return users_with_roles(db, tenant_id, [Role.SUPERVISOR, Role.LAYOUT_ADMIN])


def vendor_users(db: Session, tenant_id: uuid.UUID, vendor_id: uuid.UUID | None) -> list[uuid.UUID]:
    if vendor_id is None:
        return []
    return list(db.scalars(select(User.id).where(User.tenant_id == tenant_id, User.vendor_id == vendor_id, User.is_active.is_(True))))
