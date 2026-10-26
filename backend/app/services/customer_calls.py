"""WhatsApp audio and video calls from the team to a customer.

The customer is the ticket's customer (also for a job raised from a ticket); for any
other job it is the plot's owner.

Only the people responsible for that customer may call (permission ``customers.call``):
  * a supervisor or layout admin, while the ticket or job is not closed or cancelled;
  * the staff member or vendor the job is currently assigned to, while the job is open.
    Vendors are outside companies, so they also need the layout's
    ``ticket_share_customer_contact`` setting: the call link carries the customer's number.

WhatsApp has no public link that starts a call. ``wa.me/<number>`` opens the chat with
the customer, prefilled with a short message saying who is calling and why; the caller
taps the phone (audio) or camera (video) icon in the chat header. Ringing the customer
directly needs the WhatsApp Business Calling API and the provider keys. Every link
handed out is audited.
"""

import uuid
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import MaintenanceTask, Property, Resident, Ticket, User
from app.models.enums import Role, TaskStatus
from app.services import audit
from app.services import tickets as tsvc
from app.services.access import is_task_worker, is_ticket_assignee
from app.services.whatsapp import normalize_phone

MODES = ("audio", "video")
CLOSED_TICKET = {"closed", "cancelled", "rejected"}


def _vendor_allowed(db: Session, actor: Actor) -> bool:
    return actor.role != Role.VENDOR or bool(tsvc.setting(db, actor.tenant_id, "ticket_share_customer_contact"))


Contact = tuple[str, str | None]  # normalised phone, name to greet


def _first(*candidates: tuple[str | None, str | None]) -> Contact | None:
    """The first candidate whose phone normalises to a usable number."""
    for phone, name in candidates:
        if norm := normalize_phone(phone):
            return norm, name
    return None


def ticket_contact(db: Session, t: Ticket) -> Contact | None:
    customer = db.get(User, t.customer_id)
    if customer is not None and customer.tenant_id != t.tenant_id:
        customer = None
    name = customer.full_name if customer else None
    return _first((t.contact_phone, name), (customer.phone if customer else None, name))


def _owner_contact(db: Session, prop: Property) -> Contact | None:
    owner = db.get(User, prop.owner_user_id) if prop.owner_user_id else None
    if owner is not None and owner.tenant_id != prop.tenant_id:
        owner = None
    residents = db.execute(
        select(Resident.phone, Resident.name)
        .where(
            Resident.tenant_id == prop.tenant_id,
            Resident.property_id == prop.id,
            Resident.relation == "owner",
            Resident.phone.is_not(None),
            Resident.deleted_at.is_(None),
        )
        .order_by(Resident.is_primary.desc(), Resident.created_at)
    ).all()
    return _first(
        (owner.phone if owner else None, owner.full_name if owner else prop.owner_name),
        (prop.owner_phone, prop.owner_name),
        *((phone, name) for phone, name in residents),
    )


def task_contact(db: Session, task: MaintenanceTask) -> Contact | None:
    """A job raised from a ticket calls that ticket's customer; any other job calls the plot's owner."""
    if task.ticket_id:
        t = db.get(Ticket, task.ticket_id)
        return ticket_contact(db, t) if t and t.tenant_id == task.tenant_id else None
    prop = db.get(Property, task.property_id) if task.property_id else None
    return _owner_contact(db, prop) if prop and prop.tenant_id == task.tenant_id else None


def may_call_ticket(db: Session, actor: Actor, t: Ticket) -> bool:
    if not actor.can("customers.call") or t.status in CLOSED_TICKET:
        return False
    if actor.is_manager():
        return True
    return is_ticket_assignee(actor, t) and t.status in tsvc.ACTIVE and _vendor_allowed(db, actor)


def may_call_task(db: Session, actor: Actor, task: MaintenanceTask) -> bool:
    if not actor.can("customers.call") or task.status in (TaskStatus.CLOSED, TaskStatus.CANCELLED):
        return False
    if actor.is_manager():
        return True
    return is_task_worker(actor, task) and task.status not in tsvc.TASK_DONE and _vendor_allowed(db, actor)


def can_call_ticket(db: Session, actor: Actor, t: Ticket) -> bool:
    return may_call_ticket(db, actor, t) and ticket_contact(db, t) is not None


def can_call_task(db: Session, actor: Actor, task: MaintenanceTask) -> bool:
    return may_call_task(db, actor, task) and task_contact(db, task) is not None


def call_link(phone: str, mode: str, caller: str, customer: str | None, ref: str, subject: str) -> str:
    first = (customer or "").split()
    hello = f"Hi {first[0]}" if first else "Hi"
    plan = "I'll video call you on WhatsApp now so I can show you the work." if mode == "video" else "I'll call you on WhatsApp now."
    text = f"{hello}, this is {caller} from GreenPlot about {ref} ({subject}). {plan}"
    return f"https://wa.me/{phone}?text={quote(text)}"


def record(db: Session, actor: Actor, entity_type: str, entity_id: uuid.UUID, mode: str) -> None:
    audit.record(db, actor, "customer.whatsapp_call", entity_type, entity_id, new={"mode": mode})
