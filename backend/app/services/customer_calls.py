"""WhatsApp audio and video calls from the team to a customer.

The customer is the ticket's customer, or for a work order the plot's owner.

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
from app.models.enums import Role
from app.services import audit
from app.services import tickets as tsvc
from app.services.access import is_task_worker, is_ticket_assignee
from app.services.whatsapp import normalize_phone

MODES = ("audio", "video")
CLOSED_TICKET = {"closed", "cancelled", "rejected"}


def _vendor_allowed(db: Session, actor: Actor) -> bool:
    return actor.role != Role.VENDOR or bool(tsvc.setting(db, actor.tenant_id, "ticket_share_customer_contact"))


def ticket_phone(db: Session, t: Ticket) -> str | None:
    customer = db.get(User, t.customer_id)
    return normalize_phone(t.contact_phone or (customer.phone if customer else None))


def _owner_phone(db: Session, prop: Property | None) -> str | None:
    if prop is None:
        return None
    if prop.owner_user_id:
        owner = db.get(User, prop.owner_user_id)
        if owner and owner.phone:
            return normalize_phone(owner.phone)
    if prop.owner_phone:
        return normalize_phone(prop.owner_phone)
    phone = db.scalar(
        select(Resident.phone).where(
            Resident.property_id == prop.id,
            Resident.relation == "owner",
            Resident.phone.is_not(None),
            Resident.deleted_at.is_(None),
        )
    )
    return normalize_phone(phone)


def may_call_ticket(db: Session, actor: Actor, t: Ticket) -> bool:
    if not actor.can("customers.call") or t.status in CLOSED_TICKET:
        return False
    if actor.is_manager():
        return True
    return is_ticket_assignee(actor, t) and t.status in tsvc.ACTIVE and _vendor_allowed(db, actor)


def may_call_task(db: Session, actor: Actor, task: MaintenanceTask) -> bool:
    if not actor.can("customers.call") or task.status in tsvc.TASK_DONE:
        return False
    return actor.is_manager() or (is_task_worker(actor, task) and _vendor_allowed(db, actor))


def task_phone(db: Session, task: MaintenanceTask) -> str | None:
    if task.ticket_id:
        t = db.get(Ticket, task.ticket_id)
        if t and (phone := ticket_phone(db, t)):
            return phone
    return _owner_phone(db, db.get(Property, task.property_id) if task.property_id else None)


def can_call_ticket(db: Session, actor: Actor, t: Ticket) -> bool:
    return may_call_ticket(db, actor, t) and ticket_phone(db, t) is not None


def can_call_task(db: Session, actor: Actor, task: MaintenanceTask) -> bool:
    return may_call_task(db, actor, task) and task_phone(db, task) is not None


def call_link(phone: str, mode: str, caller: str, customer: str | None, ref: str, subject: str) -> str:
    hello = f"Hi {customer.split()[0]}" if customer else "Hi"
    plan = "I'll video call you on WhatsApp now so I can show you the work." if mode == "video" else "I'll call you on WhatsApp now."
    text = f"{hello}, this is {caller} from GreenPlot about {ref} ({subject}). {plan}"
    return f"https://wa.me/{phone}?text={quote(text)}"


def record(db: Session, actor: Actor, entity_type: str, entity_id: uuid.UUID, mode: str) -> None:
    audit.record(db, actor, "customer.whatsapp_call", entity_type, entity_id, new={"mode": mode})
