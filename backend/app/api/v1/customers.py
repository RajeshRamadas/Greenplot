"""Customer records: one page per customer with their plots, history, conversations and photos.

Layout admins only, since the record shows customers' numbers and the office's internal notes.
"""

import json
import uuid
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, or_, select

from app.api.v1._util import Limit, Offset, apply, paginate, user_names
from app.api.v1.media import present
from app.core.deps import DB, Actor, Perm
from app.models import CustomerInteraction, Property, Resident, Ticket, User
from app.models.base import utcnow
from app.models.enums import Role
from app.schemas.common import Page
from app.schemas.customers import (
    CustomerEvent,
    CustomerMediaOut,
    CustomerOut,
    CustomerSummary,
    InteractionIn,
    InteractionOut,
    InteractionUpdate,
)
from app.services import audit
from app.services import customers as svc
from app.services.access import get_scoped

router = APIRouter(tags=["customers"])


def _interaction_out(db, rows: list[CustomerInteraction]) -> list[InteractionOut]:
    names = user_names(db, (r.author_id for r in rows))
    out = []
    for r in rows:
        o = InteractionOut.model_validate(r)
        o.author_name = names.get(r.author_id)
        out.append(o)
    return out


def _customer_out(db, u: User) -> CustomerOut:
    return CustomerOut(
        id=u.id,
        full_name=u.full_name,
        email=u.email,
        phone=u.phone,
        whatsapp_phone=u.whatsapp_phone,
        is_active=u.is_active,
        whatsapp_opt_in=u.whatsapp_opt_in,
        phone_verified=u.phone_verified_at is not None,
        joined_at=u.created_at,
        last_login_at=u.last_login_at,
        plots=svc.plots(db, u.tenant_id, u.id),
        stats=svc.stats(db, u),
    )


@router.get("/customers", response_model=Page[CustomerSummary])
def list_customers(db: DB, actor: Perm("customers.read"), q: str | None = None, limit: int = Limit, offset: int = Offset):
    stmt = select(User).where(User.tenant_id == actor.tenant_id, User.role == Role.RESIDENT).order_by(User.full_name)
    if q:
        like = f"%{q.lower()}%"
        plot_owners = select(Property.owner_user_id).where(
            Property.tenant_id == actor.tenant_id, or_(Property.plot_number.ilike(like), Property.code.ilike(like))
        )
        plot_residents = (
            select(Resident.user_id)
            .join(Property, Property.id == Resident.property_id)
            .where(Resident.tenant_id == actor.tenant_id, or_(Property.plot_number.ilike(like), Property.code.ilike(like)))
        )
        stmt = stmt.where(
            or_(
                User.full_name.ilike(like),
                User.email.ilike(like),
                User.phone.ilike(like),
                User.whatsapp_phone.ilike(like),
                User.id.in_(plot_owners),
                User.id.in_(plot_residents),
            )
        )
    users, total = paginate(db, stmt, limit, offset)
    ids = [u.id for u in users]
    contact = svc.last_contact(db, users)
    open_tickets = (
        dict(
            db.execute(
                select(Ticket.customer_id, func.count())
                .where(
                    Ticket.tenant_id == actor.tenant_id,
                    Ticket.customer_id.in_(ids),
                    Ticket.deleted_at.is_(None),
                    Ticket.status.not_in(svc.OPEN_TICKET_EXCLUDED),
                )
                .group_by(Ticket.customer_id)
            ).all()
        )
        if ids
        else {}
    )
    items = [
        CustomerSummary(
            id=u.id,
            full_name=u.full_name,
            email=u.email,
            phone=u.phone,
            whatsapp_phone=u.whatsapp_phone,
            is_active=u.is_active,
            plots=[f"Plot {p.plot_number}" for p in svc.plots(db, actor.tenant_id, u.id)],
            open_tickets=open_tickets.get(u.id, 0),
            last_contact_at=contact.get(u.id),
        )
        for u in users
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/customers/{user_id}", response_model=CustomerOut)
def get_customer(user_id: uuid.UUID, db: DB, actor: Perm("customers.read")):
    return _customer_out(db, svc.get_customer(db, actor, user_id))


@router.get("/customers/{user_id}/history", response_model=list[CustomerEvent])
def customer_history(
    user_id: uuid.UUID, db: DB, actor: Perm("customers.read"), kind: str | None = None, limit: int = Limit, offset: int = Offset
):
    """Newest first; page back with offset."""
    events = svc.timeline(db, svc.get_customer(db, actor, user_id))
    if kind:
        events = [e for e in events if e.kind == kind]
    return events[offset : offset + limit]


@router.get("/customers/{user_id}/media", response_model=list[CustomerMediaOut])
def customer_media(user_id: uuid.UUID, db: DB, actor: Perm("customers.read"), limit: int | None = Query(None, ge=1), offset: int = Offset):
    """Photos, videos and documents from the customer's tickets, jobs, plots, inspections and own file (all of them by default)."""
    u = svc.get_customer(db, actor, user_id)
    return [CustomerMediaOut(**present(db, m).model_dump(), source=source) for m, source in svc.media(db, u, limit, offset)]


@router.get("/customers/{user_id}/export")
def export_customer(user_id: uuid.UUID, db: DB, actor: Perm("customers.read")):
    """Everything on the customer's record as one JSON file (photo links expire after a few minutes)."""
    u = svc.get_customer(db, actor, user_id)
    pids = set(svc.plot_links(db, u.tenant_id, u.id))
    data = {
        "exported_at": utcnow().isoformat(),
        "customer": _customer_out(db, u).model_dump(mode="json"),
        "conversations": [i.model_dump(mode="json") for i in _interaction_out(db, svc.interactions(db, u.tenant_id, u.id, pids))],
        "history": [e.model_dump(mode="json") for e in svc.timeline(db, u)],
        "files": [{**present(db, m).model_dump(mode="json"), "source": source} for m, source in svc.media(db, u)],
    }
    audit.record(db, actor, "customer.exported", "user", u.id)
    db.commit()
    # ASCII fallback plus the full name in filename* (RFC 6266), so names in Kannada or Hindi still download.
    ascii_slug = "-".join("".join(c if c.isascii() and c.isalnum() else " " for c in u.full_name.lower()).split()) or "customer"
    full = quote(f"greenplot-{'-'.join(u.full_name.lower().split())}.json")
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=\"greenplot-{ascii_slug}.json\"; filename*=UTF-8''{full}"},
    )


# ------------------------------------------------------------------ conversations & notes


@router.get("/customers/{user_id}/interactions", response_model=list[InteractionOut])
def customer_interactions(user_id: uuid.UUID, db: DB, actor: Perm("customers.read")):
    u = svc.get_customer(db, actor, user_id)
    return _interaction_out(db, svc.interactions(db, u.tenant_id, u.id, set(svc.plot_links(db, u.tenant_id, u.id))))


def _create(db, actor: Actor, body: InteractionIn, customer_id: uuid.UUID | None, property_id: uuid.UUID | None) -> CustomerInteraction:
    ticket_id = None
    if body.ticket_id:
        t = get_scoped(db, Ticket, body.ticket_id, actor, "Ticket")
        if (customer_id and t.customer_id != customer_id) or (property_id and t.property_id not in (None, property_id)):
            raise HTTPException(422, "That ticket belongs to another customer or plot")
        ticket_id = t.id
        property_id = property_id or t.property_id
    i = CustomerInteraction(
        tenant_id=actor.tenant_id,
        customer_id=customer_id,
        property_id=property_id,
        ticket_id=ticket_id,
        kind=body.kind,
        direction=body.direction,
        occurred_at=body.occurred_at or utcnow(),
        summary=body.summary.strip(),
        outcome=body.outcome,
        author_id=actor.id,
    )
    db.add(i)
    db.flush()
    audit.record(
        db,
        actor,
        "customer.interaction_logged",
        "customer_interaction",
        i.id,
        new={"kind": i.kind, "customer_id": customer_id, "property_id": property_id},
    )
    db.commit()
    return i


@router.post("/customers/{user_id}/interactions", response_model=InteractionOut, status_code=201)
def log_interaction(user_id: uuid.UUID, body: InteractionIn, db: DB, actor: Perm("customers.notes")):
    u = svc.get_customer(db, actor, user_id)
    if body.property_id and body.property_id not in svc.plot_links(db, u.tenant_id, u.id):
        raise HTTPException(422, "That plot is not linked to this customer")
    return _interaction_out(db, [_create(db, actor, body, u.id, body.property_id)])[0]


@router.get("/properties/{property_id}/interactions", response_model=list[InteractionOut])
def property_interactions(property_id: uuid.UUID, db: DB, actor: Perm("customers.read")):
    """Conversations about a plot, including ones with an owner who has no login."""
    p = get_scoped(db, Property, property_id, actor, "Property")
    clauses = [CustomerInteraction.property_id == p.id]
    if p.owner_user_id:  # plus the owner's general notes that aren't about a particular plot
        clauses.append((CustomerInteraction.customer_id == p.owner_user_id) & CustomerInteraction.property_id.is_(None))
    rows = db.scalars(
        select(CustomerInteraction)
        .where(CustomerInteraction.tenant_id == actor.tenant_id, CustomerInteraction.deleted_at.is_(None), or_(*clauses))
        .order_by(CustomerInteraction.occurred_at.desc())
    )
    return _interaction_out(db, list(rows))


@router.post("/properties/{property_id}/interactions", response_model=InteractionOut, status_code=201)
def log_property_interaction(property_id: uuid.UUID, body: InteractionIn, db: DB, actor: Perm("customers.notes")):
    p = get_scoped(db, Property, property_id, actor, "Property")
    return _interaction_out(db, [_create(db, actor, body, p.owner_user_id, p.id)])[0]


@router.patch("/customer-interactions/{interaction_id}", response_model=InteractionOut)
def update_interaction(interaction_id: uuid.UUID, body: InteractionUpdate, db: DB, actor: Perm("customers.notes")):
    i = get_scoped(db, CustomerInteraction, interaction_id, actor, "Conversation")
    before = audit.snapshot(i)
    apply(i, {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k in ("direction", "outcome")})
    old, new = audit.diff(before, audit.snapshot(i))
    if new:
        audit.record(db, actor, "customer.interaction_updated", "customer_interaction", i.id, old=old, new=new)
    db.commit()
    return _interaction_out(db, [i])[0]


@router.delete("/customer-interactions/{interaction_id}", status_code=204)
def delete_interaction(interaction_id: uuid.UUID, db: DB, actor: Perm("customers.notes")):
    i = get_scoped(db, CustomerInteraction, interaction_id, actor, "Conversation")
    i.deleted_at = utcnow()
    audit.record(db, actor, "customer.interaction_deleted", "customer_interaction", i.id, old={"kind": i.kind, "summary": i.summary})
    db.commit()
