"""Messages to plot owners: who to reach, signed public links and pay links.

Owners with an account get a normal notification (in-app plus the tenant's channels
for that kind: WhatsApp, email, SMS, push), so consent, the WhatsApp 24-hour window,
delivery receipts and retries all apply. Owners recorded only by phone/email on the
property get email and SMS; WhatsApp needs an opted-in account.
"""

import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import sign_value, verify_signed_value
from app.models import Invoice, Property, Resident
from app.services import notifications

# --------------------------------------------------------------------------- recipients


def owner_user_ids(db: Session, prop: Property) -> list[uuid.UUID]:
    ids = [prop.owner_user_id] if prop.owner_user_id else []
    ids += db.scalars(
        select(Resident.user_id).where(
            Resident.property_id == prop.id,
            Resident.relation == "owner",
            Resident.user_id.is_not(None),
            Resident.deleted_at.is_(None),
        )
    )
    return list(dict.fromkeys(ids))


def has_owner_contact(db: Session, prop: Property) -> bool:
    return bool(owner_user_ids(db, prop) or prop.owner_phone or prop.owner_email)


def send(
    db: Session,
    prop: Property,
    kind: str,
    title: str,
    body: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    link: str | None = None,
) -> list[str]:
    """Reach the plot's owner(s); returns the channels that accepted the message."""
    users = owner_user_ids(db, prop)
    if users:
        sent: list[str] = []
        for n in notifications.notify(db, prop.tenant_id, users, kind, title, body, entity_type, entity_id, send_now=True):
            sent += [ch for ch, r in (n.delivery or {}).items() if r.split(":", 1)[0] in ("stored", "sent", "delivered")]
        return list(dict.fromkeys(sent))
    from app.services.messaging import send_email, send_sms

    sent = []
    if prop.owner_email and send_email(prop.owner_email, title, body).startswith("sent"):
        sent.append("email")
    if prop.owner_phone and send_sms(prop.owner_phone, title, body, link).startswith("sent"):
        sent.append("sms")
    return sent


# --------------------------------------------------------------------------- links


def link_token(kind: str, obj_id: uuid.UUID, days: int) -> str:
    """An unguessable, expiring token for a public link (no sign-in needed to open it)."""
    return f"{obj_id.hex}.{sign_value(f'{kind}:{obj_id}', days * 86400)}"


def read_link_token(kind: str, token: str) -> uuid.UUID | None:
    try:
        raw, sig = token.split(".", 1)
        obj_id = uuid.UUID(hex=raw)
    except ValueError:
        return None
    return obj_id if verify_signed_value(f"{kind}:{obj_id}", sig) else None


def app_link(path: str) -> str:
    return f"{get_settings().app_url}{path}"


_pay_link_builder: Callable[[Session, Invoice], str] | None = None


def set_pay_link_builder(fn: Callable[[Session, Invoice], str] | None) -> None:
    """Plug in the payment gateway's link (e.g. a Razorpay Payment Link) for reminders."""
    global _pay_link_builder
    _pay_link_builder = fn


def pay_link(db: Session, inv: Invoice) -> str:
    if _pay_link_builder is not None:
        return _pay_link_builder(db, inv)
    return app_link(f"/billing?invoice={inv.id}")
