"""Customer ticketing & vendor service management (ticketing requirements §6-20, §32-35).

OPEN → UNDER_REVIEW → ASSIGNED → ACCEPTED → IN_PROGRESS → WORK_COMPLETED → VERIFICATION → RESOLVED → CLOSED
Side states: WAITING_FOR_CUSTOMER, ON_HOLD, REOPENED, REJECTED, CANCELLED.

The work itself runs on a linked maintenance task, so vendors and staff reuse the
Proof of Work rules (evidence, checklist, materials, supervisor approval). The
maintenance service calls on_task_event() on every lifecycle step, which keeps the
ticket in step whether the assignee works from the ticket or from the job screen.
"""

import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import (
    MaintenanceTask,
    Property,
    Ticket,
    TicketAssignment,
    TicketCategory,
    TicketComment,
    TicketSLA,
    TicketStatusHistory,
    User,
    Vendor,
)
from app.models.base import utcnow
from app.models.enums import CommentVisibility, Role, TaskStatus, TicketPriority, TicketStatus
from app.services import audit, notifications
from app.services.access import is_ticket_assignee, resident_property_ids
from app.services.numbering import next_number

S = TicketStatus
V = CommentVisibility

# --------------------------------------------------------------------------- configuration

# §5 categories: (code, name, maintenance category, default priority, subcategories)
DEFAULT_CATEGORIES: list[tuple[str, str, str, str, list[str]]] = [
    ("cleaning", "Cleaning", "cleaning", "low", ["Garbage not collected", "Common area dirty", "Drain cleaning"]),
    ("gardening", "Gardening", "gardening", "low", ["Lawn", "Hedge trimming", "Tree pruning", "Watering"]),
    ("plumbing", "Plumbing", "plumbing", "medium", ["Leak", "Pipe burst", "Tap or valve", "Low pressure"]),
    ("electrical", "Electrical", "electrical", "high", ["Power outage", "Wiring", "Switch or socket", "Meter"]),
    ("gate_fence", "Gate/Fence", "gate_fence", "medium", ["Gate not closing", "Hinge", "Fence damage", "Lock"]),
    ("security", "Security", "other", "high", ["Unauthorised entry", "CCTV", "Guard not at post"]),
    ("water", "Water", "plumbing", "high", ["No water supply", "Contamination", "Tank or sump", "Motor or pump"]),
    ("drainage", "Drainage", "civil", "medium", ["Blocked drain", "Overflow", "Manhole"]),
    ("streetlight", "Streetlight", "electrical", "medium", ["Light not working", "Flickering", "Pole damage"]),
    ("common_area", "Common Area", "compound_maintenance", "low", ["Park", "Clubhouse", "Road", "Signage"]),
    ("property_inspection", "Property Inspection", "inspection", "low", ["Vacant plot check", "Boundary check"]),
    ("maintenance", "Maintenance", "repairs", "medium", []),
    ("vendor_service", "Vendor Service", "repairs", "medium", []),
    ("other", "Other", "other", "medium", []),
]

# §15 planning values in minutes: (response, resolution). Tenants override via settings["ticket_sla"].
DEFAULT_SLA: dict[str, tuple[int, int]] = {
    TicketPriority.CRITICAL: (15, 4 * 60),
    TicketPriority.HIGH: (60, 24 * 60),
    TicketPriority.MEDIUM: (4 * 60, 48 * 60),
    TicketPriority.LOW: (24 * 60, 5 * 24 * 60),
}
PRIORITY_ORDER = [p.value for p in TicketPriority]
PRIORITY_TO_TASK = {"critical": "urgent", "high": "high", "medium": "medium", "low": "low"}

# Tenant-configurable policy (open decisions §42), with V1 defaults.
SETTINGS_DEFAULTS = {
    "ticket_customer_max_priority": "high",  # customers may pick up to this priority
    "ticket_reopen_days": 7,  # customers may reopen this long after resolution/closure
    "ticket_auto_close_days": 3,  # resolved tickets close automatically after this (0 = never)
    "ticket_share_customer_contact": False,  # vendors see the customer's phone number
    "ticket_share_vendor_contact": False,  # customers see the vendor's phone number
    "ticket_assignee_customer_chat": True,  # assignees may message the customer directly
    "ticket_sla_at_risk_percent": 80,  # notify when this much of the window has elapsed
    "ticket_escalate_every_hours": 24,  # re-escalate an unresolved breach this often
}

ACTIVE = {S.OPEN, S.UNDER_REVIEW, S.ASSIGNED, S.ACCEPTED, S.IN_PROGRESS, S.WAITING_FOR_CUSTOMER, S.WORK_COMPLETED,
          S.VERIFICATION, S.ON_HOLD, S.REOPENED}  # fmt: skip
UNASSIGNED_STATES = {S.OPEN, S.UNDER_REVIEW, S.REOPENED}
ASSIGNABLE = UNASSIGNED_STATES | {S.ASSIGNED, S.ACCEPTED, S.IN_PROGRESS, S.ON_HOLD, S.WAITING_FOR_CUSTOMER}
PAUSABLE = UNASSIGNED_STATES | {S.ASSIGNED, S.ACCEPTED, S.IN_PROGRESS}
REOPENABLE = {S.RESOLVED, S.CLOSED, S.REJECTED}
TASK_DONE = {TaskStatus.APPROVED, TaskStatus.CLOSED, TaskStatus.CANCELLED}

BUCKETS: dict[str, set[TicketStatus]] = {
    "active": ACTIVE,
    "new": {S.OPEN},
    "open": {S.OPEN, S.UNDER_REVIEW, S.ASSIGNED, S.ACCEPTED, S.WAITING_FOR_CUSTOMER, S.ON_HOLD},
    "unassigned": UNASSIGNED_STATES,
    "assigned": {S.ASSIGNED, S.ACCEPTED},
    "new_assignments": {S.ASSIGNED},
    "accepted": {S.ACCEPTED},
    "in_progress": {S.IN_PROGRESS, S.WORK_COMPLETED, S.VERIFICATION},
    "awaiting_verification": {S.WORK_COMPLETED, S.VERIFICATION},
    "resolved": {S.RESOLVED},
    "closed": {S.CLOSED},
    "completed": {S.RESOLVED, S.CLOSED},
    "reopened": {S.REOPENED},
    "waiting": {S.WAITING_FOR_CUSTOMER, S.ON_HOLD},
}


def http(code: int, msg: str) -> HTTPException:
    return HTTPException(code, msg)


def setting(db: Session, tenant_id: uuid.UUID, key: str):
    from app.services.maintenance import tenant_setting

    return tenant_setting(db, tenant_id, key, SETTINGS_DEFAULTS[key])


def ensure_categories(db: Session, tenant_id: uuid.UUID) -> None:
    existing = set(db.scalars(select(TicketCategory.code).where(TicketCategory.tenant_id == tenant_id)))
    for pos, (code, name, task_cat, prio, subs) in enumerate(DEFAULT_CATEGORIES):
        if code not in existing:
            db.add(
                TicketCategory(
                    tenant_id=tenant_id,
                    code=code,
                    name=name,
                    task_category=task_cat,
                    default_priority=prio,
                    subcategories=subs,
                    position=pos,
                )
            )
    db.flush()


def get_category(db: Session, tenant_id: uuid.UUID, ref: uuid.UUID | str) -> TicketCategory:
    ensure_categories(db, tenant_id)
    stmt = select(TicketCategory).where(TicketCategory.tenant_id == tenant_id, TicketCategory.deleted_at.is_(None))
    if isinstance(ref, uuid.UUID):
        stmt = stmt.where(TicketCategory.id == ref)
    else:
        try:
            stmt = stmt.where(TicketCategory.id == uuid.UUID(str(ref)))
        except ValueError:
            stmt = stmt.where(TicketCategory.code == ref)
    cat = db.scalar(stmt)
    if cat is None:
        raise http(422, "Unknown ticket category")
    return cat


# --------------------------------------------------------------------------- SLA (§15-16)


def sla_minutes(db: Session, tenant_id: uuid.UUID, category: TicketCategory, priority: str) -> tuple[int, int]:
    response, resolution = DEFAULT_SLA[TicketPriority(priority)]
    configured = (setting_raw(db, tenant_id, "ticket_sla") or {}).get(priority) or {}
    response = int(configured.get("response_minutes", response))
    resolution = int(configured.get("resolution_minutes", resolution))
    # A category SLA applies to its default priority and anything less urgent.
    if PRIORITY_ORDER.index(priority) <= PRIORITY_ORDER.index(category.default_priority):
        response = category.response_sla_minutes or response
        resolution = category.resolution_sla_minutes or resolution
    return response, resolution


def setting_raw(db: Session, tenant_id: uuid.UUID, key: str):
    from app.services.maintenance import tenant_setting

    return tenant_setting(db, tenant_id, key, None)


def get_sla(db: Session, t: Ticket) -> TicketSLA | None:
    return db.scalar(select(TicketSLA).where(TicketSLA.ticket_id == t.id))


def apply_sla(db: Session, t: Ticket, start: datetime | None = None) -> TicketSLA:
    """(Re)compute response and resolution due times from the ticket's priority and category."""
    category = db.get(TicketCategory, t.category_id)
    response, resolution = sla_minutes(db, t.tenant_id, category, t.priority)
    start = start or t.reopened_at or t.created_at or utcnow()
    sla = get_sla(db, t)
    if sla is None:
        sla = TicketSLA(tenant_id=t.tenant_id, ticket_id=t.id)
        db.add(sla)
    sla.response_due_at = start + timedelta(minutes=response)
    sla.resolution_due_at = start + timedelta(minutes=resolution)
    sla.response_breached = bool(sla.first_response_at and sla.first_response_at > sla.response_due_at)
    sla.resolution_breached = bool(sla.resolved_at and sla.resolved_at > sla.resolution_due_at)
    t.due_at = sla.resolution_due_at
    db.flush()  # sessions don't autoflush; later lookups in this transaction must see it
    return sla


def sla_state(t: Ticket, sla: TicketSLA | None, db: Session | None = None, now: datetime | None = None) -> str | None:
    """met / breached for finished tickets; on_track / at_risk / breached for active ones."""
    if sla is None or t.status in (S.CANCELLED, S.REJECTED):
        return None
    now = now or utcnow()
    if t.status in (S.RESOLVED, S.CLOSED):
        late = sla.resolution_breached or sla.response_breached or (sla.resolved_at and sla.resolved_at > sla.resolution_due_at)
        return "breached" if late else "met"
    if sla.resolution_breached or sla.response_breached or now > sla.resolution_due_at:
        return "breached"
    if sla.first_response_at is None and now > sla.response_due_at:
        return "breached"
    pct = (setting(db, t.tenant_id, "ticket_sla_at_risk_percent") if db else SETTINGS_DEFAULTS["ticket_sla_at_risk_percent"]) / 100
    start = t.reopened_at or t.created_at
    if now >= start + (sla.resolution_due_at - start) * pct:
        return "at_risk"
    if sla.first_response_at is None and now >= start + (sla.response_due_at - start) * pct:
        return "at_risk"
    return "on_track"


def _first_response(db: Session, t: Ticket, when: datetime | None = None) -> None:
    when = when or utcnow()
    if t.first_response_at is None:
        t.first_response_at = when
    sla = get_sla(db, t)
    if sla and sla.first_response_at is None:
        sla.first_response_at = when
        sla.response_breached = when > sla.response_due_at


# --------------------------------------------------------------------------- helpers


def set_status(db: Session, actor: Actor | None, t: Ticket, new: TicketStatus, reason: str | None = None) -> None:
    old = t.status
    if old == new:
        return
    t.status = new
    db.add(
        TicketStatusHistory(
            tenant_id=t.tenant_id,
            ticket_id=t.id,
            old_status=old,
            new_status=new,
            changed_by=actor.id if actor else None,
            reason=reason,
            created_at=utcnow(),
        )
    )
    audit.record(
        db,
        actor,
        "ticket.status_changed",
        "ticket",
        t.id,
        old={"status": old},
        new={"status": new, "reason": reason},
        tenant_id=t.tenant_id,
    )


def system_note(db: Session, t: Ticket, message: str, visibility: str = V.CUSTOMER, author: uuid.UUID | None = None) -> None:
    db.add(
        TicketComment(
            tenant_id=t.tenant_id, ticket_id=t.id, author_id=author, comment_type="system", visibility=visibility, message=message
        )
    )


def notify_customer(db: Session, t: Ticket, title: str, body: str | None = None, kind: str = "ticket_update"):
    return notifications.notify(db, t.tenant_id, [t.customer_id], kind, title, body, "ticket", t.id)


def assignee_user_ids(db: Session, t: Ticket) -> list[uuid.UUID]:
    if t.assigned_to_type == "vendor":
        return notifications.vendor_users(db, t.tenant_id, t.assigned_to_id)
    if t.assigned_to_type == "staff" and t.assigned_to_id:
        return [t.assigned_to_id]
    return []


def assignee_name(db: Session, t: Ticket) -> str | None:
    if t.assigned_to_type == "vendor" and t.assigned_to_id:
        v = db.get(Vendor, t.assigned_to_id)
        return v.name if v else None
    if t.assigned_to_type == "staff" and t.assigned_to_id:
        u = db.get(User, t.assigned_to_id)
        return u.full_name if u else None
    return None


def current_task(db: Session, t: Ticket) -> MaintenanceTask | None:
    return db.get(MaintenanceTask, t.maintenance_task_id) if t.maintenance_task_id else None


def active_task(db: Session, t: Ticket) -> MaintenanceTask | None:
    task = current_task(db, t)
    return task if task and task.status not in TASK_DONE else None


def open_assignment(db: Session, t: Ticket) -> TicketAssignment | None:
    return db.scalar(
        select(TicketAssignment)
        .where(
            TicketAssignment.ticket_id == t.id,
            TicketAssignment.unassigned_at.is_(None),
            TicketAssignment.rejected_at.is_(None),
        )
        .order_by(TicketAssignment.assigned_at.desc())
    )


def is_customer(db: Session, actor: Actor, t: Ticket) -> bool:
    return actor.role == Role.RESIDENT and (t.customer_id == actor.id or t.property_id in resident_property_ids(db, actor))


def _require_manager(actor: Actor, permission: str = "tickets.manage"):
    if not actor.can(permission):
        raise http(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")


def _require_assignee(actor: Actor, t: Ticket):
    if not is_ticket_assignee(actor, t):
        raise http(status.HTTP_403_FORBIDDEN, "Only the assigned vendor or staff member can do this")


def _require_task(db: Session, t: Ticket) -> MaintenanceTask:
    task = active_task(db, t)
    if task is None:
        raise http(409, "This ticket has no active work order. Ask the layout office to assign it.")
    return task


# --------------------------------------------------------------------------- creation & triage


def create(db: Session, actor: Actor, data: dict) -> Ticket:
    category = get_category(db, actor.tenant_id, data.pop("category"))
    if not category.is_active:
        raise http(422, "This category is not accepting tickets")
    customer_id = data.pop("customer_id", None)
    property_id = data.get("property_id")
    if actor.role == Role.RESIDENT:
        mine = resident_property_ids(db, actor)
        if property_id and property_id not in mine:
            raise http(403, "You can only raise tickets for your own property")
        if not property_id and len(mine) == 1:
            data["property_id"] = next(iter(mine))
        customer_id = actor.id
        data["source"] = "offline" if data.get("source") == "offline" else "portal"
    else:
        if property_id:
            p = db.get(Property, property_id)
            if p is None or p.tenant_id != actor.tenant_id or p.deleted_at:
                raise http(404, "Property not found")
        if customer_id:
            u = db.get(User, customer_id)
            if u is None or u.tenant_id != actor.tenant_id or u.role != Role.RESIDENT:
                raise http(422, "Customer must be a resident of this layout")
        customer_id = customer_id or actor.id
        data["source"] = data.get("source") or "admin"

    priority = data.pop("priority", None)
    if priority is None or (actor.role == Role.RESIDENT and not category.customer_sets_priority):
        priority = category.default_priority
    if actor.role == Role.RESIDENT:
        cap = setting(db, actor.tenant_id, "ticket_customer_max_priority")
        if PRIORITY_ORDER.index(priority) > PRIORITY_ORDER.index(cap):
            priority = cap
    if data.get("subcategory") and category.subcategories and data["subcategory"] not in category.subcategories:
        data["subcategory"] = data["subcategory"][:100]

    t = Ticket(
        tenant_id=actor.tenant_id,
        number=next_number(db, actor.tenant_id, "TKT"),
        customer_id=customer_id,
        created_by=actor.id,
        category_id=category.id,
        priority=priority,
        status=S.OPEN,
        **data,
    )
    t.created_at = utcnow()
    db.add(t)
    db.flush()
    db.add(
        TicketStatusHistory(
            tenant_id=t.tenant_id, ticket_id=t.id, old_status=None, new_status=S.OPEN, changed_by=actor.id, created_at=t.created_at
        )
    )
    apply_sla(db, t)
    audit.record(db, actor, "ticket.created", "ticket", t.id, new=audit.snapshot(t))
    notify_customer(db, t, f"Ticket {t.number} created", f"We have received your request: {t.title}. We will review it shortly.")
    notifications.notify(
        db,
        t.tenant_id,
        [m for m in notifications.managers(db, t.tenant_id) if m != actor.id],
        "ticket_update",
        f"New ticket {t.number} · {category.name} · {t.priority}",
        t.title,
        "ticket",
        t.id,
    )
    return t


def update(db: Session, actor: Actor, t: Ticket, data: dict) -> None:
    manager_fields = {"category", "subcategory", "priority", "location", "title", "description", "property_id"}
    customer_fields = {"title", "description", "preferred_time", "contact_phone", "location"}
    if actor.can("tickets.manage"):
        allowed = manager_fields | customer_fields
    elif is_customer(db, actor, t):
        if t.status not in (S.OPEN, S.UNDER_REVIEW):
            raise http(409, "The ticket can no longer be edited; add a comment instead")
        allowed = customer_fields
    else:
        raise http(403, "You cannot edit this ticket")
    bad = set(data) - allowed
    if bad:
        raise http(403, f"You cannot change: {', '.join(sorted(bad))}")
    if t.status in (S.CLOSED, S.CANCELLED):
        raise http(409, f"Ticket is {t.status}")
    before = audit.snapshot(t)
    resla = False
    if "category" in data:
        cat = get_category(db, t.tenant_id, data.pop("category"))
        if cat.id != t.category_id:
            t.category_id, resla = cat.id, True
    if "priority" in data and data["priority"] != t.priority:
        t.priority, resla = data.pop("priority"), True
    data.pop("priority", None)
    if data.get("property_id"):
        p = db.get(Property, data["property_id"])
        if p is None or p.tenant_id != t.tenant_id or p.deleted_at:
            raise http(404, "Property not found")
    for k, v in data.items():
        setattr(t, k, v)
    if resla:
        apply_sla(db, t)
        task = active_task(db, t)
        if task:
            task.priority = PRIORITY_TO_TASK[t.priority]
            task.due_at = t.due_at
    old, new = audit.diff(before, audit.snapshot(t))
    if new:
        audit.record(db, actor, "ticket.updated", "ticket", t.id, old=old, new=new)
    if "priority" in new and actor.can("tickets.manage"):
        _first_response(db, t)
        notify_customer(db, t, f"{t.number} priority set to {t.priority}")


def review(db: Session, actor: Actor, t: Ticket) -> None:
    _require_manager(actor)
    if t.status not in (S.OPEN, S.REOPENED):
        raise http(409, f"Cannot review a ticket that is {t.status}")
    set_status(db, actor, t, S.UNDER_REVIEW)
    _first_response(db, t)
    notify_customer(db, t, f"{t.number} is under review", "The layout office is looking into your request.")


def assign(
    db: Session,
    actor: Actor,
    t: Ticket,
    staff_id: uuid.UUID | None,
    vendor_id: uuid.UUID | None,
    due_at: datetime | None = None,
    notes: str | None = None,
    reason: str | None = None,
) -> MaintenanceTask:
    """Assign or reassign the ticket. The work order is a maintenance task carrying Proof of Work."""
    from app.services import maintenance as msvc

    _require_manager(actor)
    if bool(staff_id) == bool(vendor_id):
        raise http(422, "Assign to exactly one staff member or one vendor")
    if t.status not in ASSIGNABLE:
        raise http(409, f"Cannot assign a ticket that is {t.status}")
    current = open_assignment(db, t)
    if current and (current.assignee_id != (vendor_id or staff_id)) and not (reason and reason.strip()):
        raise http(422, "Give a reason for reassigning this ticket")
    db.info.setdefault("ticket_assign", {})[t.id] = {"notes": notes, "reason": reason, "due_at": due_at}
    category = db.get(TicketCategory, t.category_id)
    due = due_at or t.due_at
    task = active_task(db, t)
    if task is not None and task.status == TaskStatus.COMPLETED:
        raise http(409, "The work is awaiting verification; approve it or request rework first")
    if task is not None and task.status in (TaskStatus.STARTED, TaskStatus.REWORK_REQUIRED):
        # Work already began under the previous assignee: keep that job as history.
        msvc.cancel(db, actor, task, f"Ticket reassigned: {reason or 'no reason given'}")
        task = None
    if task is None:
        task = msvc.create_task(
            db,
            actor,
            t.tenant_id,
            dict(
                title=t.title,
                description=f"{t.number}: {t.description}",
                category=category.task_category,
                priority=PRIORITY_TO_TASK[t.priority],
                property_id=t.property_id,
                location_note=t.location,
                ticket_id=t.id,
                source="ticket",
                due_at=due,
                assigned_staff_id=staff_id,
                vendor_id=vendor_id,
            ),
        )
    else:
        msvc.assign(db, actor, task, staff_id, vendor_id, due_at=due)
    db.info.get("ticket_assign", {}).pop(t.id, None)
    return task


# --------------------------------------------------------------------------- assignee actions (delegated to the job)


def accept(db: Session, actor: Actor, t: Ticket) -> None:
    from app.services import maintenance as msvc

    _require_assignee(actor, t)
    msvc.accept(db, actor, _require_task(db, t))


def reject(db: Session, actor: Actor, t: Ticket, reason_code: str, reason: str) -> None:
    from app.services import maintenance as msvc

    _require_assignee(actor, t)
    msvc.decline(db, actor, _require_task(db, t), f"{reason_code.replace('_', ' ')}: {reason}")


def start(db: Session, actor: Actor, t: Ticket, lat=None, lng=None, accuracy=None) -> None:
    from app.services import maintenance as msvc

    _require_assignee(actor, t)
    msvc.start(db, actor, _require_task(db, t), lat, lng, accuracy)


def complete(db: Session, actor: Actor, t: Ticket, work_notes=None, outcome=None, lat=None, lng=None, accuracy=None) -> None:
    from app.services import maintenance as msvc

    _require_assignee(actor, t)
    task = _require_task(db, t)
    if work_notes is not None or outcome is not None:
        msvc.ensure_editable(actor, task)
        if work_notes is not None:
            task.work_notes = work_notes
        if outcome is not None:
            task.outcome = outcome
    msvc.complete(db, actor, task, lat, lng, accuracy)


def verify(db: Session, actor: Actor, t: Ticket, decision: str, comment: str | None) -> None:
    """Supervisor verification: approve the proof of work, or send it back for rework (§19)."""
    from app.services import maintenance as msvc

    _require_manager(actor, "tickets.verify")
    task = current_task(db, t)
    if t.status not in (S.VERIFICATION, S.WORK_COMPLETED) or task is None or task.status != TaskStatus.COMPLETED:
        raise http(409, "There is no completed work awaiting verification")
    if decision == "approve":
        msvc.approve(db, actor, task, comment)
    else:
        msvc.reject(db, actor, task, comment or "", "rework")


# --------------------------------------------------------------------------- resolution, closure & reopening


def resolve(db: Session, actor: Actor, t: Ticket, resolution: str) -> None:
    """Resolve without field work (e.g. advice given, duplicate fixed elsewhere)."""
    _require_manager(actor)
    if t.status not in ACTIVE or t.status in (S.WORK_COMPLETED, S.VERIFICATION):
        raise http(409, f"Cannot resolve a ticket that is {t.status}")
    from app.services import maintenance as msvc

    task = active_task(db, t)
    if task is not None and task.status != TaskStatus.CREATED:
        raise http(409, f"Work order {task.number} is still open; verify it, or cancel the ticket")
    if task is not None:
        # Unassigned work order left behind by a declined assignment: retire it with the ticket.
        t.maintenance_task_id = None
        msvc.cancel(db, actor, task, f"Ticket {t.number} resolved without field work")
        t.maintenance_task_id = task.id
    _mark_resolved(db, actor, t, resolution)


def _mark_resolved(db: Session, actor: Actor | None, t: Ticket, resolution: str | None) -> None:
    now = utcnow()
    t.resolution = resolution or t.resolution
    t.resolved_at = now
    t.resume_status = None
    _first_response(db, t, now)
    sla = get_sla(db, t)
    if sla:
        sla.resolved_at = now
        sla.resolution_breached = now > sla.resolution_due_at
    set_status(db, actor, t, S.RESOLVED, resolution)
    days = setting(db, t.tenant_id, "ticket_auto_close_days")
    hint = f" It will close automatically in {days} days if we don't hear back." if days else ""
    notify_customer(
        db,
        t,
        f"{t.number} resolved — please confirm",
        f"{resolution or 'The work has been completed and verified.'} Tell us if it's resolved or still an issue.{hint}",
    )


def close(db: Session, actor: Actor | None, t: Ticket, note: str | None = None, by_customer: bool = False) -> None:
    """Close a resolved ticket and send the mandatory closure notification (§17)."""
    if actor is not None and not by_customer:
        _require_manager(actor)
    if t.status != S.RESOLVED:
        raise http(409, f"Only resolved tickets can be closed (ticket is {t.status})")
    now = utcnow()
    t.closed_at = now
    t.closed_by = actor.id if actor else None
    set_status(db, actor, t, S.CLOSED, note)
    system_note(db, t, note or "Ticket closed.", V.CUSTOMER, actor.id if actor else None)
    audit.record(
        db, actor, "ticket.closed", "ticket", t.id, new={"closed_at": now, "closed_by": t.closed_by, "note": note}, tenant_id=t.tenant_id
    )
    sent = notify_customer(
        db,
        t,
        "GreenPlot Ticket Closed",
        f"Your service request {t.number} has been completed and closed.",
        kind="ticket_closed",
    )
    audit.record(
        db,
        None,
        "ticket.customer_notified",
        "ticket",
        t.id,
        new={"event": "closed", "delivery": [n.delivery for n in sent]},
        tenant_id=t.tenant_id,
    )
    recipients = assignee_user_ids(db, t)
    notifications.notify(db, t.tenant_id, recipients, "ticket_update", f"{t.number} closed", t.title, "ticket", t.id)


def reopen(db: Session, actor: Actor, t: Ticket, reason: str) -> None:
    if not reason or not reason.strip():
        raise http(422, "A reason is required to reopen a ticket")
    if t.status not in REOPENABLE:
        raise http(409, f"Cannot reopen a ticket that is {t.status}")
    customer = is_customer(db, actor, t)
    if not (actor.can("tickets.manage") or customer):
        raise http(403, "You cannot reopen this ticket")
    if customer and not actor.can("tickets.manage") and t.status != S.RESOLVED:
        days = setting(db, t.tenant_id, "ticket_reopen_days")
        since = t.closed_at or t.updated_at
        if since and utcnow() - since > timedelta(days=days):
            raise http(409, f"Tickets can be reopened within {days} days; please raise a new ticket")
    now = utcnow()
    current = open_assignment(db, t)
    if current:
        current.unassigned_at = now
        current.unassign_reason = "Ticket reopened"
    t.reopened_at = now
    t.reopen_count += 1
    t.closed_at = t.closed_by = t.resolved_at = None
    t.verified_at = t.verified_by = None
    t.assigned_to_type = t.assigned_to_id = None
    if customer:
        t.customer_confirmation = "still_issue"
    sla = get_sla(db, t)
    if sla:
        sla.resolved_at = None
    apply_sla(db, t, now)
    if sla:
        sla.first_response_at = None
        sla.at_risk_notified_at = sla.breach_notified_at = None
        sla.response_breached = sla.resolution_breached = False
        sla.escalation_level = 0
    t.first_response_at = None
    set_status(db, actor, t, S.REOPENED, reason)
    system_note(db, t, f"Reopened: {reason}", V.CUSTOMER, actor.id)
    notify_customer(db, t, f"{t.number} reopened", reason)
    notifications.notify(
        db,
        t.tenant_id,
        [m for m in notifications.managers(db, t.tenant_id) if m != actor.id],
        "ticket_update",
        f"Ticket {t.number} reopened",
        reason,
        "ticket",
        t.id,
    )


def feedback(db: Session, actor: Actor, t: Ticket, outcome: str | None, rating: int | None, comment: str | None) -> None:
    """Customer confirmation and rating after resolution (§19, §30)."""
    if not is_customer(db, actor, t):
        raise http(403, "Only the customer can give feedback")
    if t.status not in (S.RESOLVED, S.CLOSED):
        raise http(409, "Feedback can be given once the ticket is resolved")
    if outcome == "still_issue":
        reopen(db, actor, t, comment or "Customer reports the issue is not fixed")
        return
    if rating is not None:
        t.rating = rating
    if comment:
        t.feedback = comment
    t.feedback_at = utcnow()
    audit.record(db, actor, "ticket.feedback", "ticket", t.id, new={"rating": rating, "comment": comment, "outcome": outcome})
    if outcome == "resolved":
        t.customer_confirmation = "resolved"
        if t.status == S.RESOLVED:
            close(db, actor, t, "Customer confirmed the issue is resolved.", by_customer=True)


def change_status(db: Session, actor: Actor, t: Ticket, action: str, reason: str | None) -> None:
    """Hold, wait for customer, resume, cancel, or reject an invalid ticket."""
    from app.services import maintenance as msvc

    manager = actor.can("tickets.manage")
    assignee = is_ticket_assignee(actor, t)
    customer = is_customer(db, actor, t)
    if action in ("hold", "wait", "reject") and not (reason and reason.strip()):
        raise http(422, "Give a reason")
    if action == "hold":
        _require_manager(actor)
        if t.status not in PAUSABLE:
            raise http(409, f"Cannot put a ticket on hold while it is {t.status}")
        t.resume_status = t.status
        set_status(db, actor, t, S.ON_HOLD, reason)
        notify_customer(db, t, f"{t.number} is on hold", reason)
    elif action == "wait":
        if not (manager or assignee):
            raise http(403, "Only the office or the assignee can ask the customer for information")
        if t.status not in PAUSABLE:
            raise http(409, f"Cannot wait for the customer while the ticket is {t.status}")
        t.resume_status = t.status
        set_status(db, actor, t, S.WAITING_FOR_CUSTOMER, reason)
        db.add(
            TicketComment(
                tenant_id=t.tenant_id, ticket_id=t.id, author_id=actor.id, comment_type="question", visibility=V.CUSTOMER, message=reason
            )
        )
        notify_customer(db, t, f"{t.number}: we need more information", reason)
    elif action == "resume":
        if not (manager or assignee):
            raise http(403, "You cannot resume this ticket")
        if t.status not in (S.ON_HOLD, S.WAITING_FOR_CUSTOMER):
            raise http(409, "The ticket is not paused")
        _resume(db, actor, t, reason)
    elif action == "cancel":
        if not (manager or (customer and t.status in (S.OPEN, S.UNDER_REVIEW, S.REOPENED))):
            raise http(403, "You can cancel a ticket only before it is assigned")
        if t.status not in ACTIVE or t.status in (S.WORK_COMPLETED, S.VERIFICATION):
            raise http(409, f"Cannot cancel a ticket that is {t.status}")
        task = active_task(db, t)
        if task and task.status != TaskStatus.COMPLETED:
            t.maintenance_task_id = None  # detach first so the job's cancellation doesn't re-route the ticket
            msvc.cancel(db, actor, task, f"Ticket {t.number} cancelled: {reason or 'no reason given'}")
            t.maintenance_task_id = task.id
        current = open_assignment(db, t)
        if current:
            current.unassigned_at = utcnow()
            current.unassign_reason = "Ticket cancelled"
        set_status(db, actor, t, S.CANCELLED, reason)
        if not customer:
            notify_customer(db, t, f"{t.number} cancelled", reason)
        notifications.notify(db, t.tenant_id, assignee_user_ids(db, t), "ticket_update", f"{t.number} cancelled", reason, "ticket", t.id)
    elif action == "reject":
        _require_manager(actor)
        if t.status not in UNASSIGNED_STATES:
            raise http(409, "Only unassigned tickets can be rejected")
        _first_response(db, t)
        set_status(db, actor, t, S.REJECTED, reason)
        system_note(db, t, f"Ticket not accepted: {reason}", V.CUSTOMER, actor.id)
        notify_customer(db, t, f"{t.number} could not be accepted", reason)
    else:
        raise http(422, f"Unknown action {action}")


def _resume(db: Session, actor: Actor | None, t: Ticket, note: str | None = None) -> None:
    target = S(t.resume_status) if t.resume_status in {s.value for s in ACTIVE} else S.UNDER_REVIEW
    t.resume_status = None
    set_status(db, actor, t, target, note or "Resumed")


# --------------------------------------------------------------------------- comments


def visible_to(db: Session, actor: Actor, t: Ticket) -> set[str]:
    if actor.is_manager():
        return {v.value for v in V}
    if is_ticket_assignee(actor, t):
        return {V.CUSTOMER, V.VENDOR}
    return {V.CUSTOMER}


def add_comment(db: Session, actor: Actor, t: Ticket, message: str, visibility: str) -> TicketComment:
    if t.status in (S.CLOSED, S.CANCELLED) and not actor.is_manager():
        raise http(409, f"Ticket is {t.status}; reopen it or raise a new ticket")
    assignee = is_ticket_assignee(actor, t)
    customer = is_customer(db, actor, t)
    if actor.is_manager():
        pass
    elif assignee:
        if visibility == V.CUSTOMER and not setting(db, t.tenant_id, "ticket_assignee_customer_chat"):
            raise http(403, "Messages to the customer go through the layout office")
        if visibility not in (V.CUSTOMER, V.VENDOR):
            raise http(403, "Internal notes are for the layout office")
    elif customer:
        if visibility != V.CUSTOMER:
            raise http(403, "Customers can only post customer-visible comments")
    else:
        raise http(403, "You cannot comment on this ticket")
    c = TicketComment(tenant_id=t.tenant_id, ticket_id=t.id, author_id=actor.id, visibility=visibility, message=message)
    db.add(c)
    db.flush()
    audit.record(db, actor, "ticket.comment_added", "ticket", t.id, new={"comment_id": c.id, "visibility": visibility})
    if actor.is_manager() and visibility == V.CUSTOMER:
        _first_response(db, t)
    if customer and t.status == S.WAITING_FOR_CUSTOMER:
        _resume(db, actor, t, "Customer replied")
    # Notify the other parties who can read it.
    snippet = message[:200]
    if visibility == V.CUSTOMER and not customer:
        notify_customer(db, t, f"New message on {t.number}", snippet)
    recipients: list[uuid.UUID | None] = []
    if customer:
        recipients = assignee_user_ids(db, t) or notifications.managers(db, t.tenant_id)
    elif assignee and visibility == V.VENDOR:
        recipients = notifications.managers(db, t.tenant_id)
    elif actor.is_manager() and visibility in (V.CUSTOMER, V.VENDOR):
        recipients = assignee_user_ids(db, t)
    notifications.notify(
        db, t.tenant_id, [r for r in recipients if r != actor.id], "ticket_update", f"New message on {t.number}", snippet, "ticket", t.id
    )
    return c


def attach(db: Session, actor: Actor | None, t: Ticket, media, evidence_type: str | None = None, caption: str | None = None):
    """Link an uploaded file to the ticket as an attachment (§21). Idempotent per media."""
    from app.models import TicketEvidence
    from app.models.enums import MediaStatus

    if media.status != MediaStatus.READY:
        raise http(409, "Media upload is not complete")
    if media.entity_type != "ticket" or media.entity_id != t.id:
        raise http(422, "Media belongs to a different record")
    existing = db.scalar(select(TicketEvidence).where(TicketEvidence.ticket_id == t.id, TicketEvidence.media_id == media.id))
    if existing:
        return existing
    ev = TicketEvidence(
        tenant_id=t.tenant_id,
        ticket_id=t.id,
        media_id=media.id,
        evidence_type=evidence_type or media.evidence_type or ("video" if media.content_type.startswith("video/") else "photo"),
        uploaded_by=media.uploaded_by,
        caption=caption,
    )
    db.add(ev)
    db.flush()
    audit.record(
        db, actor, "ticket.attachment_added", "ticket", t.id, new={"media_id": media.id, "sha256": media.sha256}, tenant_id=t.tenant_id
    )
    return ev


# --------------------------------------------------------------------------- maintenance → ticket sync (§32)


def on_task_event(db: Session, actor: Actor | None, task: MaintenanceTask, event: str, **info) -> None:
    """Called by the maintenance service on every lifecycle step of a ticket's work order."""
    if not task.ticket_id:
        return
    t = db.get(Ticket, task.ticket_id)
    if t is None or t.deleted_at or t.status in (S.CLOSED, S.CANCELLED, S.REJECTED):
        return
    if event == "assigned":
        _on_assigned(db, actor, t, task)
        return
    if t.maintenance_task_id != task.id:
        return  # an older work order for this ticket
    now = utcnow()
    current = open_assignment(db, t)
    who = assignee_name(db, t) or "The assignee"
    if event == "accepted":
        if current and current.accepted_at is None:
            current.accepted_at = now
        t.accepted_at = t.accepted_at or now
        if t.status == S.ASSIGNED:
            set_status(db, actor, t, S.ACCEPTED)
        notify_customer(db, t, f"{t.number} accepted by {who}", "Work will be scheduled shortly.")
    elif event == "declined":
        reason = info.get("reason")
        if current:
            current.rejected_at = now
            current.rejection_reason = reason
        t.assigned_to_type = t.assigned_to_id = None
        set_status(db, actor, t, S.UNDER_REVIEW, f"Rejected by {who}: {reason}")
        system_note(db, t, f"{who} declined the assignment: {reason}", V.INTERNAL, actor.id if actor else None)
        notifications.notify(
            db,
            t.tenant_id,
            notifications.managers(db, t.tenant_id),
            "ticket_assigned",
            f"{t.number} rejected by {who} — reassign",
            reason,
            "ticket",
            t.id,
        )
    elif event == "started":
        if current and current.accepted_at is None:
            current.accepted_at = now
        t.accepted_at = t.accepted_at or now
        first = t.started_at is None
        t.started_at = t.started_at or now
        if t.status in (S.ASSIGNED, S.ACCEPTED, S.WAITING_FOR_CUSTOMER, S.ON_HOLD, S.VERIFICATION, S.RESOLVED):
            t.resume_status = None
            set_status(db, actor, t, S.IN_PROGRESS)
        if first:
            notify_customer(db, t, f"Work started on {t.number}", f"{who} has started work.")
    elif event == "completed":
        t.completed_at = now
        set_status(db, actor, t, S.WORK_COMPLETED)
        set_status(db, None, t, S.VERIFICATION, "Awaiting supervisor verification")
        notify_customer(db, t, f"Work completed on {t.number}", "The work is being verified by the layout supervisor.")
    elif event == "approved":
        t.verified_at = now
        t.verified_by = actor.id if actor else None
        system_note(
            db,
            t,
            "Work verified by the supervisor." if actor else "Work accepted (no supervisor approval required).",
            V.CUSTOMER,
            actor.id if actor else None,
        )
        _mark_resolved(db, actor, t, task.outcome or task.work_notes or f"Completed under work order {task.number}")
    elif event == "rework":
        t.rework_count += 1
        t.verified_at = t.verified_by = t.resolved_at = None
        set_status(db, actor, t, S.IN_PROGRESS, f"Rework requested: {info.get('comment')}")
        system_note(db, t, f"Rework requested: {info.get('comment')}", V.VENDOR, actor.id if actor else None)
    elif event == "cancelled":
        if current:
            current.unassigned_at = now
            current.unassign_reason = info.get("reason")
        t.assigned_to_type = t.assigned_to_id = None
        if t.status in ACTIVE:
            set_status(db, actor, t, S.UNDER_REVIEW, f"Work order {task.number} cancelled")


def _on_assigned(db: Session, actor: Actor | None, t: Ticket, task: MaintenanceTask) -> None:
    ctx = db.info.get("ticket_assign", {}).get(t.id, {})
    now = utcnow()
    kind, target = ("vendor", task.vendor_id) if task.vendor_id else ("staff", task.assigned_staff_id)
    previous = open_assignment(db, t)
    if previous:
        previous.unassigned_at = now
        previous.unassign_reason = ctx.get("reason") or "Reassigned"
    db.add(
        TicketAssignment(
            tenant_id=t.tenant_id,
            ticket_id=t.id,
            assignee_type=kind,
            assignee_id=target,
            maintenance_task_id=task.id,
            assigned_by=actor.id if actor else None,
            assigned_at=now,
            due_at=task.due_at,
            notes=ctx.get("notes"),
        )
    )
    db.flush()
    t.assigned_to_type, t.assigned_to_id = kind, target
    t.maintenance_task_id = task.id
    t.assigned_at = now
    t.accepted_at = None
    t.resume_status = None
    _first_response(db, t, now)
    set_status(db, actor, t, S.ASSIGNED, ctx.get("reason") if previous else None)
    audit.record(
        db,
        actor,
        "ticket.assigned",
        "ticket",
        t.id,
        old={"assignee_type": previous.assignee_type, "assignee_id": previous.assignee_id} if previous else None,
        new={"assignee_type": kind, "assignee_id": target, "task": task.number, "reason": ctx.get("reason")},
        tenant_id=t.tenant_id,
    )
    who = assignee_name(db, t) or kind
    notify_customer(db, t, f"{t.number} assigned to {who}", f"Work order {task.number} has been raised.")
    notifications.notify(
        db,
        t.tenant_id,
        assignee_user_ids(db, t),
        "ticket_assigned",
        f"New ticket {t.number} assigned to you",
        f"{t.title} · priority {t.priority}" + (f" · {ctx['notes']}" if ctx.get("notes") else ""),
        "ticket",
        t.id,
    )


# --------------------------------------------------------------------------- background jobs (§16)


def run_sla_checks(db: Session, now: datetime | None = None) -> int:
    """Flag breaches, warn when the SLA is at risk, and escalate unresolved breaches."""
    now = now or utcnow()
    n = 0
    rows = db.execute(
        select(Ticket, TicketSLA)
        .join(TicketSLA, TicketSLA.ticket_id == Ticket.id)
        .where(Ticket.status.in_([s.value for s in ACTIVE]), Ticket.deleted_at.is_(None))
    ).all()
    for t, sla in rows:
        if sla.first_response_at is None and now > sla.response_due_at and not sla.response_breached:
            sla.response_breached = True
        if now > sla.resolution_due_at and not sla.resolution_breached:
            sla.resolution_breached = True
        state = sla_state(t, sla, db, now)
        managers = notifications.managers(db, t.tenant_id)
        if state == "breached":
            every = timedelta(hours=setting(db, t.tenant_id, "ticket_escalate_every_hours"))
            if sla.breach_notified_at is None or now - sla.breach_notified_at >= every:
                sla.escalation_level += 1
                sla.breach_notified_at = now
                which = "resolution" if sla.resolution_breached else "response"
                recipients = managers if sla.escalation_level == 1 else notifications.users_with_roles(db, t.tenant_id, [Role.LAYOUT_ADMIN])
                notifications.notify(
                    db,
                    t.tenant_id,
                    recipients + (assignee_user_ids(db, t) if sla.escalation_level == 1 else []),
                    "ticket_sla",
                    f"SLA breached: {t.number} ({which}) · escalation level {sla.escalation_level}",
                    t.title,
                    "ticket",
                    t.id,
                )
                audit.record(
                    db,
                    None,
                    "ticket.sla_breached",
                    "ticket",
                    t.id,
                    new={"level": sla.escalation_level, "which": which},
                    tenant_id=t.tenant_id,
                )
                n += 1
        elif state == "at_risk" and sla.at_risk_notified_at is None:
            sla.at_risk_notified_at = now
            notifications.notify(
                db,
                t.tenant_id,
                managers + assignee_user_ids(db, t),
                "ticket_sla",
                f"SLA at risk: {t.number} due {sla.resolution_due_at:%d %b %H:%M} UTC",
                t.title,
                "ticket",
                t.id,
            )
            audit.record(db, None, "ticket.sla_at_risk", "ticket", t.id, tenant_id=t.tenant_id)
            n += 1
    return n


def auto_close_resolved(db: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    n = 0
    for t in db.scalars(select(Ticket).where(Ticket.status == S.RESOLVED, Ticket.deleted_at.is_(None))):
        days = setting(db, t.tenant_id, "ticket_auto_close_days")
        if days and t.resolved_at and now - t.resolved_at >= timedelta(days=days):
            close(db, None, t, f"Closed automatically {days} days after resolution.")
            n += 1
    return n
