"""Records search across maintenance, tickets, complaints, inspections, incidents, assets,
properties, vendors and staff (requirements §23).

Free text is interpreted for plot numbers, record IDs, categories, statuses and
relative dates, so "Show all gate repairs for Plot 117 in the last 12 months"
becomes {type: maintenance, category: gate_fence, plot: 117, date_from: -12mo}.
"""

import re
import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import Asset, Complaint, Incident, Inspection, MaintenanceTask, Property, Ticket, TicketCategory, User, Vendor
from app.models.base import utcnow
from app.models.enums import Role
from app.schemas.operations import SearchHit
from app.services.access import resident_property_ids, scope_complaints, scope_inspections, scope_tasks, scope_tickets, tenant_select

CATEGORY_WORDS = {
    "gate": "gate_fence",
    "gates": "gate_fence",
    "fence": "gate_fence",
    "fencing": "gate_fence",
    "plumbing": "plumbing",
    "leak": "plumbing",
    "electrical": "electrical",
    "electric": "electrical",
    "streetlight": "electrical",
    "streetlights": "electrical",
    "cleaning": "cleaning",
    "clean": "cleaning",
    "compound": "compound_maintenance",
    "garden": "gardening",
    "gardening": "gardening",
    "landscaping": "landscaping",
    "painting": "painting",
    "civil": "civil",
    "drainage": "civil",
    "inspection": "inspection",
    "preventive": "preventive",
    "servicing": "asset_servicing",
}
TYPE_WORDS = {
    "repair": "maintenance",
    "repairs": "maintenance",
    "maintenance": "maintenance",
    "task": "maintenance",
    "tasks": "maintenance",
    "job": "maintenance",
    "jobs": "maintenance",
    "complaint": "complaint",
    "complaints": "complaint",
    "ticket": "ticket",
    "tickets": "ticket",
    "request": "ticket",
    "requests": "ticket",
    "inspections": "inspection",
    "visit": "inspection",
    "visits": "inspection",
    "incident": "incident",
    "incidents": "incident",
    "asset": "asset",
    "assets": "asset",
    "vendor": "vendor",
    "vendors": "vendor",
    "property": "property",
    "properties": "property",
    "staff": "staff",
}
STATUS_WORDS = {
    "open": [
        "created",
        "assigned",
        "accepted",
        "started",
        "rework_required",
        "open",
        "acknowledged",
        "investigating",
        "in_progress",
        "scheduled",
    ],
    "pending": ["completed"],
    "completed": ["completed", "approved", "closed", "resolved"],
    "approved": ["approved", "closed"],
    "closed": ["closed"],
    "rework": ["rework_required"],
}
STOP = {
    "show",
    "all",
    "me",
    "for",
    "in",
    "the",
    "of",
    "on",
    "at",
    "last",
    "past",
    "find",
    "list",
    "with",
    "and",
    "a",
    "an",
    "from",
    "any",
    "my",
}
UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}


def interpret(q: str | None) -> dict:
    out: dict = {}
    if not q:
        return out
    text = q.strip()
    m = re.search(r"\bGP-(MNT|CMP|TKT|INS|INC)-\d{4}-\d{3,}\b", text, re.I)
    if m:
        out["number"] = m.group(0).upper()
        kinds = {"MNT": "maintenance", "CMP": "complaint", "TKT": "ticket", "INS": "inspection", "INC": "incident"}
        out["type"] = kinds[m.group(1).upper()]
        return out
    m = re.search(r"\bplot\s*(?:no\.?|number|#)?\s*([A-Za-z0-9-]+)", text, re.I)
    if m:
        out["plot"] = m.group(1)
        text = text.replace(m.group(0), " ")
    m = re.search(r"\b(?:last|past)\s+(\d+)\s+(day|week|month|year)s?\b", text, re.I)
    if m:
        out["date_from"] = utcnow() - timedelta(days=int(m.group(1)) * UNIT_DAYS[m.group(2).lower()])
        text = text.replace(m.group(0), " ")
    elif re.search(r"\b(?:last|past)\s+(day|week|month|year)\b", text, re.I):
        unit = re.search(r"\b(?:last|past)\s+(day|week|month|year)\b", text, re.I)
        out["date_from"] = utcnow() - timedelta(days=UNIT_DAYS[unit.group(1).lower()])
        text = text.replace(unit.group(0), " ")
    leftovers = []
    for word in re.findall(r"[A-Za-z0-9_-]+", text.lower()):
        if word in CATEGORY_WORDS and "category" not in out:
            out["category"] = CATEGORY_WORDS[word]
            if word == "inspection":
                out.setdefault("type", "inspection")
        elif word in TYPE_WORDS:
            out.setdefault("type", TYPE_WORDS[word])
        elif word in STATUS_WORDS:
            out["status"] = STATUS_WORDS[word]
        elif word == "overdue":
            out["overdue"] = True
        elif word not in STOP:
            leftovers.append(word)
    if out.get("category") and "type" not in out:
        out["type"] = "maintenance"
    if leftovers:
        out["text"] = " ".join(leftovers)
    return out


def search(
    db: Session,
    actor: Actor,
    q: str | None,
    type_: str | None = None,
    property_id: uuid.UUID | None = None,
    plot: str | None = None,
    category: str | None = None,
    status: str | None = None,
    asset_id: uuid.UUID | None = None,
    vendor_id: uuid.UUID | None = None,
    staff_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 50,
) -> tuple[dict, list[SearchHit]]:
    f = interpret(q)
    f_type = type_ or f.get("type")
    plot = plot or f.get("plot")
    category = category or f.get("category")
    statuses = [status] if status else f.get("status")
    date_from = date_from or f.get("date_from")
    text = f.get("text") if f else q
    number = f.get("number")
    interpreted = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in f.items()}

    prop_ids: set[uuid.UUID] | None = None
    if plot:
        matches = tenant_select(Property, actor).where(or_(Property.plot_number.ilike(plot), Property.code.ilike(f"%-{plot}")))
        prop_ids = {p.id for p in db.scalars(matches)}
        if not prop_ids:
            return interpreted, []
    if property_id:
        prop_ids = {property_id} if prop_ids is None else prop_ids & {property_id}
    if actor.role == Role.RESIDENT:
        mine = resident_property_ids(db, actor)
        prop_ids = mine if prop_ids is None else prop_ids & mine

    def want(t: str) -> bool:
        return f_type in (None, t)

    hits: list[SearchHit] = []
    labels: dict[uuid.UUID, str] = {}

    words = (text or "").split()

    def text_match(*cols):
        """Every remaining word must appear in at least one of the columns."""
        return and_(*[or_(*[c.ilike(f"%{w}%") for c in cols]) for w in words])

    if want("maintenance") and actor.can("maintenance.read"):
        stmt = scope_tasks(tenant_select(MaintenanceTask, actor), db, actor)
        if number:
            stmt = stmt.where(MaintenanceTask.number == number)
        if prop_ids is not None:
            stmt = stmt.where(MaintenanceTask.property_id.in_(prop_ids))
        if category:
            stmt = stmt.where(MaintenanceTask.category == category)
        if statuses:
            stmt = stmt.where(MaintenanceTask.status.in_(statuses))
        if f.get("overdue"):
            stmt = stmt.where(
                MaintenanceTask.due_at < utcnow(),
                MaintenanceTask.status.in_(["created", "assigned", "accepted", "started", "rework_required"]),
            )
        if asset_id:
            stmt = stmt.where(MaintenanceTask.asset_id == asset_id)
        if vendor_id:
            stmt = stmt.where(MaintenanceTask.vendor_id == vendor_id)
        if staff_id:
            stmt = stmt.where(MaintenanceTask.assigned_staff_id == staff_id)
        if date_from:
            stmt = stmt.where(MaintenanceTask.created_at >= date_from)
        if date_to:
            stmt = stmt.where(MaintenanceTask.created_at <= date_to)
        if text and not number:
            stmt = stmt.where(
                text_match(MaintenanceTask.title, MaintenanceTask.description, MaintenanceTask.number, MaintenanceTask.work_notes)
            )
        for t in db.scalars(stmt.order_by(MaintenanceTask.created_at.desc()).limit(limit)):
            hits.append(
                SearchHit(
                    type="maintenance",
                    id=t.id,
                    number=t.number,
                    title=t.title,
                    status=t.status,
                    category=t.category,
                    property_id=t.property_id,
                    date=t.closed_at or t.completed_at or t.created_at,
                )
            )

    if want("complaint") and actor.can("complaints.read") and not asset_id and not staff_id:
        stmt = scope_complaints(tenant_select(Complaint, actor), db, actor)
        if number:
            stmt = stmt.where(Complaint.number == number)
        if prop_ids is not None:
            stmt = stmt.where(Complaint.property_id.in_(prop_ids))
        if statuses:
            stmt = stmt.where(Complaint.status.in_(statuses))
        if category and f_type == "complaint":
            stmt = stmt.where(Complaint.category.ilike(f"%{category.split('_')[0]}%"))
        if vendor_id:
            stmt = stmt.where(Complaint.vendor_id == vendor_id)
        if date_from:
            stmt = stmt.where(Complaint.created_at >= date_from)
        if date_to:
            stmt = stmt.where(Complaint.created_at <= date_to)
        if text and not number:
            stmt = stmt.where(text_match(Complaint.title, Complaint.description, Complaint.number))
        if not (category and f_type != "complaint"):
            for c in db.scalars(stmt.order_by(Complaint.created_at.desc()).limit(limit)):
                hits.append(
                    SearchHit(
                        type="complaint",
                        id=c.id,
                        number=c.number,
                        title=c.title,
                        status=c.status,
                        category=c.category,
                        property_id=c.property_id,
                        date=c.created_at,
                    )
                )

    if want("ticket") and actor.can("tickets.read") and not asset_id:
        stmt = scope_tickets(tenant_select(Ticket, actor), db, actor)
        if number:
            stmt = stmt.where(Ticket.number == number)
        if prop_ids is not None:
            stmt = stmt.where(Ticket.property_id.in_(prop_ids))
        if statuses:
            stmt = stmt.where(Ticket.status.in_(statuses))
        if category:
            cat_ids = select(TicketCategory.id).where(
                TicketCategory.tenant_id == actor.tenant_id,
                or_(TicketCategory.code == category, TicketCategory.task_category == category),
            )
            stmt = stmt.where(Ticket.category_id.in_(cat_ids))
        if vendor_id:
            stmt = stmt.where(Ticket.assigned_to_type == "vendor", Ticket.assigned_to_id == vendor_id)
        if staff_id:
            stmt = stmt.where(Ticket.assigned_to_type == "staff", Ticket.assigned_to_id == staff_id)
        if date_from:
            stmt = stmt.where(Ticket.created_at >= date_from)
        if date_to:
            stmt = stmt.where(Ticket.created_at <= date_to)
        if text and not number:
            stmt = stmt.where(text_match(Ticket.title, Ticket.description, Ticket.number))
        for t in db.scalars(stmt.order_by(Ticket.created_at.desc()).limit(limit)):
            hits.append(
                SearchHit(
                    type="ticket",
                    id=t.id,
                    number=t.number,
                    title=t.title,
                    status=t.status,
                    category=t.subcategory,
                    property_id=t.property_id,
                    date=t.closed_at or t.created_at,
                )
            )

    if want("inspection") and actor.can("inspections.read") and not (asset_id or vendor_id) and (category in (None, "inspection")):
        stmt = scope_inspections(tenant_select(Inspection, actor), db, actor)
        if number:
            stmt = stmt.where(Inspection.number == number)
        if prop_ids is not None:
            stmt = stmt.where(Inspection.property_id.in_(prop_ids))
        if statuses:
            stmt = stmt.where(Inspection.status.in_(statuses))
        if staff_id:
            stmt = stmt.where(Inspection.inspector_id == staff_id)
        if date_from:
            stmt = stmt.where(Inspection.created_at >= date_from)
        if text and not number:
            stmt = stmt.where(text_match(Inspection.findings, Inspection.number))
        for i in db.scalars(stmt.order_by(Inspection.created_at.desc()).limit(limit)):
            hits.append(
                SearchHit(
                    type="inspection",
                    id=i.id,
                    number=i.number,
                    title=f"Inspection · {i.overall_condition or i.status}",
                    status=i.status,
                    property_id=i.property_id,
                    date=i.completed_at or i.created_at,
                )
            )

    if want("incident") and actor.can("incidents.read") and actor.role not in (Role.RESIDENT,) and not (category or asset_id or vendor_id):
        stmt = tenant_select(Incident, actor)
        if number:
            stmt = stmt.where(Incident.number == number)
        if prop_ids is not None:
            stmt = stmt.where(Incident.property_id.in_(prop_ids))
        if statuses:
            stmt = stmt.where(Incident.status.in_(statuses))
        if date_from:
            stmt = stmt.where(Incident.occurred_at >= date_from)
        if text and not number:
            stmt = stmt.where(text_match(Incident.title, Incident.description, Incident.number))
        for inc in db.scalars(stmt.order_by(Incident.occurred_at.desc()).limit(limit)):
            hits.append(
                SearchHit(
                    type="incident",
                    id=inc.id,
                    number=inc.number,
                    title=inc.title,
                    status=inc.status,
                    category=inc.category,
                    property_id=inc.property_id,
                    date=inc.occurred_at,
                )
            )

    plain = not (number or statuses or date_from or category or vendor_id or staff_id)
    if f_type in (None, "asset") and actor.can("assets.read") and (text or plot) and plain:
        stmt = tenant_select(Asset, actor)
        if prop_ids is not None:
            stmt = stmt.where(Asset.property_id.in_(prop_ids))
        if text:
            stmt = stmt.where(or_(text_match(Asset.name, Asset.code, Asset.location), Asset.qr_code == text.upper()))
        for a in db.scalars(stmt.limit(limit)):
            hits.append(
                SearchHit(
                    type="asset", id=a.id, number=a.code, title=a.name, status=a.condition, category=a.category, property_id=a.property_id
                )
            )

    if f_type in (None, "property") and actor.can("properties.read") and (text or plot) and plain:
        stmt = tenant_select(Property, actor)
        if prop_ids is not None:
            stmt = stmt.where(Property.id.in_(prop_ids))
        if text:
            stmt = stmt.where(text_match(Property.plot_number, Property.code, Property.owner_name, Property.address))
        for p in db.scalars(stmt.limit(limit)):
            labels[p.id] = f"Plot {p.plot_number}"
            hits.append(
                SearchHit(
                    type="property",
                    id=p.id,
                    number=p.code,
                    title=f"Plot {p.plot_number}" + (f" · {p.owner_name}" if p.owner_name else ""),
                    status=p.condition,
                    property_id=p.id,
                )
            )

    if f_type in (None, "vendor") and actor.can("vendors.read") and text and plain and not plot:
        for v in db.scalars(tenant_select(Vendor, actor).where(text_match(Vendor.name, Vendor.contact_person)).limit(limit)):
            hits.append(SearchHit(type="vendor", id=v.id, number=None, title=v.name, status="active" if v.is_active else "inactive"))

    if f_type in (None, "staff") and actor.can("staff.read") and text and plain and not plot:
        stmt = select(User).where(
            User.tenant_id == actor.tenant_id, User.role.in_([Role.STAFF, Role.GUARD, Role.SUPERVISOR]), text_match(User.full_name)
        )
        for u in db.scalars(stmt.limit(limit)):
            hits.append(SearchHit(type="staff", id=u.id, number=None, title=u.full_name, status=u.role))

    missing = {h.property_id for h in hits if h.property_id and h.property_id not in labels}
    if missing:
        for pid, num in db.execute(select(Property.id, Property.plot_number).where(Property.id.in_(missing))):
            labels[pid] = f"Plot {num}"
    for h in hits:
        h.property_label = labels.get(h.property_id)
    hits.sort(key=lambda h: h.date or datetime.min.replace(tzinfo=utcnow().tzinfo), reverse=True)
    return interpreted, hits[:limit]
