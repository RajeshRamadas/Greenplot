"""One place for everything about a customer: plots, tickets, jobs, conversations, payments and photos.

A customer is a resident account. Most of the history already lives in its own tables
(tickets, ticket comments, WhatsApp messages, notifications, jobs, invoices, media); this
module gathers it, and adds CustomerInteraction for what the office does outside the app:
phone and WhatsApp calls, visits, meetings and notes.

The customer record carries their phone numbers and the office's internal notes, so it is
for layout admins only (``customers.read``), in line with app.services.access.sees_customer_contact.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import (
    Complaint,
    ComplaintComment,
    CustomerInteraction,
    Inspection,
    Invoice,
    MaintenanceTask,
    Media,
    Notification,
    Payment,
    PlotReport,
    Property,
    Resident,
    Subscription,
    Ticket,
    TicketComment,
    User,
    WhatsAppMessage,
)
from app.models.base import utcnow
from app.models.enums import InvoiceStatus, MediaStatus, PaymentStatus, Role, SubscriptionStatus
from app.schemas.customers import CustomerEvent, CustomerPlot, CustomerStats
from app.services.access import not_found

KIND_LABELS = {
    "note": "Note",
    "phone_call": "Phone call",
    "whatsapp_call": "WhatsApp call",
    "whatsapp_chat": "WhatsApp chat",
    "sms": "SMS",
    "email": "Email",
    "site_visit": "Site visit",
    "meeting": "Meeting",
}
DONE_TASK = ("completed", "approved", "closed")
OPEN_TICKET_EXCLUDED = ("resolved", "closed", "cancelled", "rejected")


def get_customer(db: Session, actor: Actor, user_id: uuid.UUID) -> User:
    u = db.get(User, user_id)
    if u is None or u.tenant_id != actor.tenant_id or u.role != Role.RESIDENT:
        raise not_found("Customer")
    return u


def plot_links(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """The customer's plots and how they are linked to each: owner, tenant or family."""
    links: dict[uuid.UUID, str] = {
        pid: "owner"
        for pid in db.scalars(
            select(Property.id).where(Property.tenant_id == tenant_id, Property.owner_user_id == user_id, Property.deleted_at.is_(None))
        )
    }
    for pid, relation in db.execute(
        select(Resident.property_id, Resident.relation).where(
            Resident.tenant_id == tenant_id, Resident.user_id == user_id, Resident.deleted_at.is_(None)
        )
    ):
        links.setdefault(pid, relation)
    return links


def plots(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[CustomerPlot]:
    links = plot_links(db, tenant_id, user_id)
    if not links:
        return []
    props = db.scalars(select(Property).where(Property.id.in_(links), Property.deleted_at.is_(None)).order_by(Property.code))
    return [
        CustomerPlot(
            id=p.id,
            code=p.code,
            plot_number=p.plot_number,
            layout_name=p.layout.name if p.layout else None,
            relation=links[p.id],
            area_sqft=p.area_sqft,
            status=p.status,
        )
        for p in props
    ]


def _interactions_filter(user_id: uuid.UUID, property_ids: set[uuid.UUID]):
    clauses = [CustomerInteraction.customer_id == user_id]
    if property_ids:
        clauses.append(CustomerInteraction.property_id.in_(property_ids))
    return or_(*clauses)


def interactions(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, property_ids: set[uuid.UUID]) -> list[CustomerInteraction]:
    return list(
        db.scalars(
            select(CustomerInteraction)
            .where(
                CustomerInteraction.tenant_id == tenant_id,
                CustomerInteraction.deleted_at.is_(None),
                _interactions_filter(user_id, property_ids),
            )
            .order_by(CustomerInteraction.occurred_at.desc())
        )
    )


def _task_ids(db: Session, tenant_id: uuid.UUID, property_ids: set[uuid.UUID], ticket_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    clauses = []
    if property_ids:
        clauses.append(MaintenanceTask.property_id.in_(property_ids))
    if ticket_ids:
        clauses.append(MaintenanceTask.ticket_id.in_(ticket_ids))
    if not clauses:
        return set()
    return set(
        db.scalars(
            select(MaintenanceTask.id).where(MaintenanceTask.tenant_id == tenant_id, MaintenanceTask.deleted_at.is_(None), or_(*clauses))
        )
    )


def _media_sources(db: Session, u: User) -> dict[tuple[str, uuid.UUID], str]:
    """Every live record whose photos and files belong on this customer's record, with a label for each."""
    tid = u.tenant_id
    pids = set(plot_links(db, tid, u.id))
    sources: dict[tuple[str, uuid.UUID], str] = {("customer", u.id): "Customer file"}
    if pids:
        for p in db.execute(select(Property.id, Property.plot_number).where(Property.id.in_(pids))):
            sources[("property", p.id)] = f"Plot {p.plot_number}"
        for i in db.execute(
            select(Inspection.id, Inspection.number).where(
                Inspection.tenant_id == tid, Inspection.property_id.in_(pids), Inspection.deleted_at.is_(None)
            )
        ):
            sources[("inspection", i.id)] = f"Inspection {i.number}"
    tickets = dict(
        db.execute(
            select(Ticket.id, Ticket.number).where(Ticket.tenant_id == tid, Ticket.customer_id == u.id, Ticket.deleted_at.is_(None))
        ).all()
    )
    for tid_, number in tickets.items():
        sources[("ticket", tid_)] = f"Ticket {number}"
    task_ids = _task_ids(db, tid, pids, set(tickets))
    if task_ids:
        for t in db.execute(select(MaintenanceTask.id, MaintenanceTask.number).where(MaintenanceTask.id.in_(task_ids))):
            sources[("maintenance_task", t.id)] = f"Job {t.number}"
    for c in db.execute(
        select(Complaint.id, Complaint.number).where(
            Complaint.tenant_id == tid, Complaint.raised_by == u.id, Complaint.deleted_at.is_(None)
        )
    ):
        sources[("complaint", c.id)] = f"Complaint {c.number}"
    return sources


def _media_query(u: User, sources: dict[tuple[str, uuid.UUID], str]):
    by_type: dict[str, set[uuid.UUID]] = {}
    for etype, eid in sources:
        by_type.setdefault(etype, set()).add(eid)
    clause = or_(*[(Media.entity_type == etype) & Media.entity_id.in_(ids) for etype, ids in by_type.items()])
    return select(Media).where(Media.tenant_id == u.tenant_id, Media.status == MediaStatus.READY, clause)


def media(db: Session, u: User, limit: int | None = None, offset: int = 0) -> list[tuple[Media, str]]:
    """Ready photos, videos and documents from the customer's tickets, jobs, plots and own file, newest first."""
    sources = _media_sources(db, u)
    stmt = _media_query(u, sources).order_by(func.coalesce(Media.captured_at, Media.uploaded_at, Media.created_at).desc()).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return [(m, sources[(m.entity_type, m.entity_id)]) for m in db.scalars(stmt)]


def media_count(db: Session, u: User) -> int:
    stmt = _media_query(u, _media_sources(db, u))
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


def _standalone_ratings(db: Session, tenant_id: uuid.UUID, task_ids: set[uuid.UUID]) -> list[MaintenanceTask]:
    """Jobs without a ticket that the customer rated (ticket jobs are rated on the ticket)."""
    if not task_ids:
        return []
    return list(
        db.scalars(
            select(MaintenanceTask).where(
                MaintenanceTask.id.in_(task_ids), MaintenanceTask.ticket_id.is_(None), MaintenanceTask.rated_at.is_not(None)
            )
        )
    )


def _last_contact(db: Session, u: User, pids: set[uuid.UUID]) -> datetime | None:
    """Latest conversation: a logged interaction, a WhatsApp message that went through, or a ticket message."""
    tid = u.tenant_id
    last = [
        db.scalar(
            select(func.max(CustomerInteraction.occurred_at)).where(
                CustomerInteraction.tenant_id == tid, CustomerInteraction.deleted_at.is_(None), _interactions_filter(u.id, pids)
            )
        ),
        db.scalar(
            select(func.max(WhatsAppMessage.created_at)).where(
                WhatsAppMessage.user_id == u.id, WhatsAppMessage.tenant_id == tid, WhatsAppMessage.status != "failed"
            )
        ),
        db.scalar(
            select(func.max(TicketComment.created_at))
            .join(Ticket, Ticket.id == TicketComment.ticket_id)
            .where(Ticket.tenant_id == tid, Ticket.customer_id == u.id, TicketComment.comment_type != "system")
        ),
    ]
    last = [x for x in last if x]
    return max(last) if last else None


def stats(db: Session, u: User) -> CustomerStats:
    tid = u.tenant_id
    pids = set(plot_links(db, tid, u.id))
    s = CustomerStats()
    tickets = list(
        db.execute(
            select(Ticket.id, Ticket.status, Ticket.rating).where(
                Ticket.tenant_id == tid, Ticket.customer_id == u.id, Ticket.deleted_at.is_(None)
            )
        )
    )
    s.tickets = len(tickets)
    s.open_tickets = sum(1 for t in tickets if t.status not in OPEN_TICKET_EXCLUDED)
    task_ids = _task_ids(db, tid, pids, {t.id for t in tickets})
    ratings = [t.rating for t in tickets if t.rating] + [t.rating for t in _standalone_ratings(db, tid, task_ids) if t.rating]
    s.avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
    if task_ids:
        s.jobs_done = db.scalar(select(func.count()).where(MaintenanceTask.id.in_(task_ids), MaintenanceTask.status.in_(DONE_TASK))) or 0
    s.photos = media_count(db, u)
    if pids:
        billed, paid = db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0), func.coalesce(func.sum(Invoice.amount_paid), 0)).where(
                Invoice.tenant_id == tid,
                Invoice.property_id.in_(pids),
                Invoice.deleted_at.is_(None),
                Invoice.status != InvoiceStatus.WAIVED,
            )
        ).one()
        s.billed, s.paid = float(billed), float(paid)
        s.outstanding = round(s.billed - s.paid, 2)
        s.active_subscriptions = (
            db.scalar(
                select(func.count()).where(
                    Subscription.tenant_id == tid, Subscription.property_id.in_(pids), Subscription.status == SubscriptionStatus.ACTIVE
                )
            )
            or 0
        )
    s.conversations = len(interactions(db, tid, u.id, pids))
    s.last_contact_at = _last_contact(db, u, pids)
    return s


def last_contact(db: Session, users: list[User]) -> dict[uuid.UUID, datetime | None]:
    """Latest conversation per customer for the list page (a page is at most a few dozen customers)."""
    return {u.id: _last_contact(db, u, set(plot_links(db, u.tenant_id, u.id))) for u in users}


# --------------------------------------------------------------------------- history


def timeline(db: Session, u: User) -> list[CustomerEvent]:
    """Everything that happened with this customer, newest first."""
    tid = u.tenant_id
    pids = set(plot_links(db, tid, u.id))
    labels = dict(db.execute(select(Property.id, Property.plot_number).where(Property.id.in_(pids))).all()) if pids else {}
    names: dict[uuid.UUID, str] = {}

    def name(user_id: uuid.UUID | None) -> str | None:
        if not user_id:
            return None
        if user_id not in names:
            names[user_id] = db.scalar(select(User.full_name).where(User.id == user_id)) or "Someone"
        return names[user_id]

    ev: list[CustomerEvent] = [CustomerEvent(at=u.created_at, kind="account", title="Customer account created")]

    for i in interactions(db, tid, u.id, pids):
        plot = f" · Plot {labels[i.property_id]}" if i.property_id in labels else ""
        body = i.summary + (f"\nOutcome: {i.outcome}" if i.outcome else "")
        ev.append(
            CustomerEvent(
                at=i.occurred_at,
                kind=i.kind,
                title=f"{KIND_LABELS.get(i.kind, i.kind)}{plot}",
                body=body,
                by=name(i.author_id),
                direction=i.direction,
                internal=True,
                entity_type="customer_interaction",
                entity_id=i.id,
            )
        )

    tickets = list(db.scalars(select(Ticket).where(Ticket.tenant_id == tid, Ticket.customer_id == u.id, Ticket.deleted_at.is_(None))))
    by_ticket = {t.id: t for t in tickets}
    for t in tickets:
        common = {"number": t.number, "entity_type": "ticket", "entity_id": t.id}
        ev.append(
            CustomerEvent(at=t.created_at, kind="ticket", title=f"Ticket raised · {t.title}", body=t.description, status=t.status, **common)
        )
        if t.closed_at or t.resolved_at:
            ev.append(
                CustomerEvent(
                    at=t.closed_at or t.resolved_at,
                    kind="ticket",
                    title=f"Ticket {'closed' if t.closed_at else 'resolved'} · {t.title}",
                    body=t.resolution,
                    status=t.status,
                    **common,
                )
            )
        if t.rating and t.feedback_at:
            ev.append(CustomerEvent(at=t.feedback_at, kind="feedback", title=f"Rated the work {t.rating}/5", body=t.feedback, **common))
    if by_ticket:
        for c in db.scalars(
            select(TicketComment)
            .where(TicketComment.ticket_id.in_(by_ticket), TicketComment.comment_type != "system")
            .order_by(TicketComment.created_at)
        ):
            t = by_ticket[c.ticket_id]
            ev.append(
                CustomerEvent(
                    at=c.created_at,
                    kind="ticket_message",
                    title=f"Message on {t.number}",
                    body=c.message,
                    by=name(c.author_id),
                    direction="in" if c.author_id == u.id else "out",
                    internal=c.visibility != "customer",
                    number=t.number,
                    entity_type="ticket",
                    entity_id=t.id,
                )
            )

    for m in db.scalars(select(WhatsAppMessage).where(WhatsAppMessage.tenant_id == tid, WhatsAppMessage.user_id == u.id)):
        t = by_ticket.get(m.ticket_id) if m.ticket_id else None
        ev.append(
            CustomerEvent(
                at=m.created_at,
                kind="whatsapp",
                title="WhatsApp from customer" if m.direction == "in" else "WhatsApp to customer",
                body=m.body,
                status=m.status,
                direction=m.direction,
                number=t.number if t else None,
                entity_type="ticket" if t else None,
                entity_id=t.id if t else None,
            )
        )

    for n in db.scalars(select(Notification).where(Notification.tenant_id == tid, Notification.user_id == u.id)):
        sent = [ch for ch, r in (n.delivery or {}).items() if str(r).split(":", 1)[0] in ("stored", "sent", "delivered", "read")]
        ev.append(
            CustomerEvent(
                at=n.created_at,
                kind="update_sent",
                title=n.title,
                body=n.body,
                status=", ".join(sent) or None,
                direction="out",
                entity_type=n.entity_type,
                entity_id=n.entity_id,
            )
        )

    task_ids = _task_ids(db, tid, pids, set(by_ticket))
    if task_ids:
        for t in db.scalars(select(MaintenanceTask).where(MaintenanceTask.id.in_(task_ids))):
            done_at = t.closed_at or t.completed_at
            ev.append(
                CustomerEvent(
                    at=done_at or t.created_at,
                    kind="job",
                    title=f"{'Job done' if done_at else 'Job booked'} · {t.title}",
                    status=t.status,
                    number=t.number,
                    entity_type="maintenance_task",
                    entity_id=t.id,
                )
            )
            if t.rated_at and t.rating and t.ticket_id is None:
                ev.append(
                    CustomerEvent(
                        at=t.rated_at,
                        kind="feedback",
                        title=f"Rated the work {t.rating}/5",
                        body=t.rating_comment,
                        number=t.number,
                        entity_type="maintenance_task",
                        entity_id=t.id,
                    )
                )

    complaints = {
        c.id: c
        for c in db.scalars(
            select(Complaint).where(Complaint.tenant_id == tid, Complaint.raised_by == u.id, Complaint.deleted_at.is_(None))
        )
    }
    for c in complaints.values():
        ev.append(
            CustomerEvent(
                at=c.created_at,
                kind="complaint",
                title=f"Complaint · {c.title}",
                body=c.description,
                status=c.status,
                number=c.number,
                entity_type="complaint",
                entity_id=c.id,
            )
        )
    if complaints:
        for cc in db.scalars(select(ComplaintComment).where(ComplaintComment.complaint_id.in_(complaints))):
            c = complaints[cc.complaint_id]
            ev.append(
                CustomerEvent(
                    at=cc.created_at,
                    kind="complaint_message",
                    title=f"Message on {c.number}",
                    body=cc.body,
                    by=name(cc.author_id),
                    direction="in" if cc.author_id == u.id else "out",
                    internal=cc.internal,
                    number=c.number,
                    entity_type="complaint",
                    entity_id=c.id,
                )
            )

    if pids:
        for i in db.scalars(
            select(Inspection).where(Inspection.tenant_id == tid, Inspection.property_id.in_(pids), Inspection.deleted_at.is_(None))
        ):
            ev.append(
                CustomerEvent(
                    at=i.completed_at or i.scheduled_for or i.created_at,
                    kind="inspection",
                    title=f"Plot {labels.get(i.property_id, '')} inspection · {i.overall_condition or i.status}",
                    body=i.findings,
                    status=i.status,
                    number=i.number,
                    entity_type="inspection",
                    entity_id=i.id,
                )
            )
        for inv in db.scalars(select(Invoice).where(Invoice.tenant_id == tid, Invoice.property_id.in_(pids), Invoice.deleted_at.is_(None))):
            ev.append(
                CustomerEvent(
                    at=inv.created_at,
                    kind="invoice",
                    title=f"Invoice · {inv.description} · ₹{float(inv.amount):,.0f}",
                    status=inv.status,
                    number=inv.number,
                    entity_type="invoice",
                    entity_id=inv.id,
                )
            )
        for p in db.scalars(
            select(Payment).where(Payment.tenant_id == tid, Payment.property_id.in_(pids), Payment.status == PaymentStatus.SUCCEEDED)
        ):
            ev.append(
                CustomerEvent(
                    at=p.paid_at or p.created_at,
                    kind="payment",
                    title=f"Paid ₹{float(p.amount):,.0f} by {p.method.replace('_', ' ')}",
                    number=p.receipt_number,
                    entity_type="payment",
                    entity_id=p.id,
                )
            )
        for r in db.scalars(
            select(PlotReport).where(PlotReport.tenant_id == tid, PlotReport.property_id.in_(pids), PlotReport.sent_at.is_not(None))
        ):
            ev.append(
                CustomerEvent(
                    at=r.sent_at,
                    kind="plot_report",
                    title=f"Monthly report for Plot {labels.get(r.property_id, '')} sent",
                    status=", ".join(r.channels or []) or None,
                    direction="out",
                    entity_type="property",
                    entity_id=r.property_id,
                )
            )

    ev.sort(key=lambda e: e.at, reverse=True)
    return ev


# --------------------------------------------------------------------------- calls from tickets and jobs


def log_whatsapp_call(db: Session, actor: Actor, entity_type: str, entity_id: uuid.UUID, mode: str) -> None:
    """Put a WhatsApp call from a ticket or job on the customer's record.

    The app only hands out a wa.me link (the call itself happens in WhatsApp), so this records
    that the call link was opened, not that the call connected.
    """
    customer_id = property_id = ticket_id = task_id = None
    ref = ""
    if entity_type == "ticket":
        t = db.get(Ticket, entity_id)
        customer_id, property_id, ticket_id, ref = t.customer_id, t.property_id, t.id, t.number
    else:
        task = db.get(MaintenanceTask, entity_id)
        task_id, property_id, ref = task.id, task.property_id, task.number
        t = db.get(Ticket, task.ticket_id) if task.ticket_id else None
        if t is not None and t.tenant_id == task.tenant_id:
            customer_id, ticket_id = t.customer_id, t.id
        elif task.property_id:
            prop = db.get(Property, task.property_id)
            customer_id = prop.owner_user_id if prop else None
    db.add(
        CustomerInteraction(
            tenant_id=actor.tenant_id,
            customer_id=customer_id,
            property_id=property_id,
            ticket_id=ticket_id,
            maintenance_task_id=task_id,
            kind="whatsapp_call",
            direction="out",
            occurred_at=utcnow(),
            summary=f"{'Video' if mode == 'video' else 'Audio'} call link opened from {ref} (the call itself happens in WhatsApp).",
            author_id=actor.id,
        )
    )
