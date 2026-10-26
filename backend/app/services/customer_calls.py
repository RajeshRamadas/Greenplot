"""WhatsApp audio and video calls from the office to a customer.

The customer is the ticket's customer (also for a job raised from a ticket); for any
other job it is the plot's owner. Calls go to the customer's WhatsApp number, which is
their calling number unless they gave a separate one.

Customers' numbers are shown to layout admins only (app.services.access.sees_customer_contact),
so only they can call (permission ``customers.call``), on any ticket or job that is not
closed or cancelled. Staff and supervisors would see the number in their own WhatsApp, so
they get calling once calls go out from GreenPlot's business number (WhatsApp Business
Calling API, which needs the provider keys).

WhatsApp has no public link that starts a call. ``wa.me/<number>`` opens the chat with
the customer, prefilled with a short message saying who is calling and why; the caller
taps the phone (audio) or camera (video) icon in the chat header. Every link handed out
is audited.
"""

import uuid
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import MaintenanceTask, Property, Resident, Ticket, User
from app.models.enums import TaskStatus
from app.services import audit
from app.services.whatsapp import normalize_phone

MODES = ("audio", "video")
CLOSED_TICKET = {"closed", "cancelled", "rejected"}

Contact = tuple[str, str | None]  # normalised WhatsApp number, name to greet


def _first(*candidates: tuple[str | None, str | None]) -> Contact | None:
    """The first candidate whose number normalises to a usable one."""
    for phone, name in candidates:
        if norm := normalize_phone(phone):
            return norm, name
    return None


def ticket_contact(db: Session, t: Ticket) -> Contact | None:
    customer = db.get(User, t.customer_id)
    if customer is not None and customer.tenant_id != t.tenant_id:
        customer = None
    name = customer.full_name if customer else None
    if t.contact_phone:  # the number given on the ticket wins over the account's
        return _first((t.contact_whatsapp, name), (t.contact_phone, name))
    return _first((customer.whatsapp_phone, name), (customer.phone, name)) if customer else None


def _owner_contact(db: Session, prop: Property) -> Contact | None:
    owner = db.get(User, prop.owner_user_id) if prop.owner_user_id else None
    if owner is not None and owner.tenant_id != prop.tenant_id:
        owner = None
    residents = db.execute(
        select(Resident.whatsapp_phone, Resident.phone, Resident.name)
        .where(
            Resident.tenant_id == prop.tenant_id,
            Resident.property_id == prop.id,
            Resident.relation == "owner",
            Resident.phone.is_not(None),
            Resident.deleted_at.is_(None),
        )
        .order_by(Resident.is_primary.desc(), Resident.created_at)
    ).all()
    candidates: list[tuple[str | None, str | None]] = []
    if owner:
        candidates += [(owner.whatsapp_phone, owner.full_name), (owner.phone, owner.full_name)]
    candidates += [(prop.owner_whatsapp, prop.owner_name), (prop.owner_phone, prop.owner_name)]
    for whatsapp, phone, name in residents:
        candidates += [(whatsapp, name), (phone, name)]
    return _first(*candidates)


def task_contact(db: Session, task: MaintenanceTask) -> Contact | None:
    """A job raised from a ticket calls that ticket's customer; any other job calls the plot's owner."""
    if task.ticket_id:
        t = db.get(Ticket, task.ticket_id)
        return ticket_contact(db, t) if t and t.tenant_id == task.tenant_id else None
    prop = db.get(Property, task.property_id) if task.property_id else None
    return _owner_contact(db, prop) if prop and prop.tenant_id == task.tenant_id else None


def may_call_ticket(actor: Actor, t: Ticket) -> bool:
    return actor.can("customers.call") and t.tenant_id == actor.tenant_id and t.status not in CLOSED_TICKET


def may_call_task(actor: Actor, task: MaintenanceTask) -> bool:
    return (
        actor.can("customers.call") and task.tenant_id == actor.tenant_id and task.status not in (TaskStatus.CLOSED, TaskStatus.CANCELLED)
    )


def can_call_ticket(db: Session, actor: Actor, t: Ticket) -> bool:
    return may_call_ticket(actor, t) and ticket_contact(db, t) is not None


def can_call_task(db: Session, actor: Actor, task: MaintenanceTask) -> bool:
    return may_call_task(actor, task) and task_contact(db, task) is not None


def call_link(phone: str, mode: str, caller: str, customer: str | None, ref: str, subject: str) -> str:
    first = (customer or "").split()
    hello = f"Hi {first[0]}" if first else "Hi"
    plan = "I'll video call you on WhatsApp now so I can show you the work." if mode == "video" else "I'll call you on WhatsApp now."
    text = f"{hello}, this is {caller} from GreenPlot about {ref} ({subject}). {plan}"
    return f"https://wa.me/{phone}?text={quote(text)}"


def record(db: Session, actor: Actor, entity_type: str, entity_id: uuid.UUID, mode: str) -> None:
    audit.record(db, actor, "customer.whatsapp_call", entity_type, entity_id, new={"mode": mode})
