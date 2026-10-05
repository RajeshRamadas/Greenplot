import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import or_, select

from app.api.v1._util import Limit, Offset, paginate, property_labels, user_names
from app.core.deps import DB, Perm
from app.models import Complaint, ComplaintComment, MaintenanceTask, Property
from app.models.base import utcnow
from app.models.enums import ComplaintStatus, Role, TaskCategory
from app.schemas.common import Page
from app.schemas.maintenance import (
    ComplaintAssignIn,
    ComplaintCommentIn,
    ComplaintCommentOut,
    ComplaintIn,
    ComplaintOut,
    ComplaintStatusIn,
)
from app.services import audit, notifications
from app.services import maintenance as msvc
from app.services.access import can_view_complaint, get_scoped, not_found, resident_property_ids, scope_complaints, tenant_select
from app.services.numbering import next_number

router = APIRouter(prefix="/complaints", tags=["complaints"])

CATEGORY_TO_TASK = {
    "gate": TaskCategory.GATE_FENCE,
    "fence": TaskCategory.GATE_FENCE,
    "plumbing": TaskCategory.PLUMBING,
    "water": TaskCategory.PLUMBING,
    "electrical": TaskCategory.ELECTRICAL,
    "streetlight": TaskCategory.ELECTRICAL,
    "cleaning": TaskCategory.CLEANING,
    "garbage": TaskCategory.CLEANING,
    "garden": TaskCategory.GARDENING,
    "drainage": TaskCategory.CIVIL,
    "road": TaskCategory.CIVIL,
}


def _out(db, cs: list[Complaint], with_comments=False, actor=None) -> list[ComplaintOut]:
    props = property_labels(db, (c.property_id for c in cs))
    names = user_names(db, (c.raised_by for c in cs))
    tasks = {}
    ids = [c.maintenance_task_id for c in cs if c.maintenance_task_id]
    if ids:
        tasks = {t.id: t for t in db.scalars(select(MaintenanceTask).where(MaintenanceTask.id.in_(ids)))}
    out = []
    for c in cs:
        o = ComplaintOut.model_validate(c)
        o.property_label = props.get(c.property_id)
        o.raised_by_name = names.get(c.raised_by)
        t = tasks.get(c.maintenance_task_id)
        if t:
            o.task_number, o.task_status = t.number, t.status
        if with_comments:
            stmt = select(ComplaintComment).where(ComplaintComment.complaint_id == c.id).order_by(ComplaintComment.created_at)
            if actor and not actor.is_manager():
                stmt = stmt.where(ComplaintComment.internal.is_(False))
            comments = list(db.scalars(stmt))
            authors = user_names(db, (x.author_id for x in comments))
            o.comments = [
                ComplaintCommentOut.model_validate(x).model_copy(update={"author_name": authors.get(x.author_id)}) for x in comments
            ]
        out.append(o)
    return out


def _get(db, actor, complaint_id) -> Complaint:
    c = get_scoped(db, Complaint, complaint_id, actor, "Complaint")
    if not can_view_complaint(db, actor, c):
        raise not_found("Complaint")
    return c


@router.get("", response_model=Page[ComplaintOut])
def list_complaints(
    db: DB,
    actor: Perm("complaints.read"),
    status: ComplaintStatus | None = None,
    property_id: uuid.UUID | None = None,
    category: str | None = None,
    priority: str | None = None,
    q: str | None = None,
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = scope_complaints(tenant_select(Complaint, actor), db, actor).order_by(Complaint.created_at.desc())
    if status:
        stmt = stmt.where(Complaint.status == status)
    if property_id:
        stmt = stmt.where(Complaint.property_id == property_id)
    if category:
        stmt = stmt.where(Complaint.category == category)
    if priority:
        stmt = stmt.where(Complaint.priority == priority)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Complaint.number.ilike(like), Complaint.title.ilike(like), Complaint.description.ilike(like)))
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=_out(db, items), total=total, limit=limit, offset=offset)


@router.post("", response_model=ComplaintOut, status_code=201)
def create_complaint(body: ComplaintIn, db: DB, actor: Perm("complaints.create")):
    if body.property_id:
        get_scoped(db, Property, body.property_id, actor, "Property")
        if actor.role == Role.RESIDENT and body.property_id not in resident_property_ids(db, actor):
            raise HTTPException(403, "You can only raise complaints for your own property")
    elif actor.role == Role.RESIDENT:
        mine = resident_property_ids(db, actor)
        body.property_id = next(iter(mine)) if len(mine) == 1 else None
    c = Complaint(tenant_id=actor.tenant_id, number=next_number(db, actor.tenant_id, "CMP"), raised_by=actor.id, **body.model_dump())
    db.add(c)
    db.flush()
    audit.record(db, actor, "complaint.created", "complaint", c.id, new=audit.snapshot(c))
    notifications.notify(
        db,
        actor.tenant_id,
        notifications.managers(db, actor.tenant_id),
        "complaint_update",
        f"New complaint {c.number}",
        c.title,
        "complaint",
        c.id,
    )
    db.commit()
    return _out(db, [c])[0]


@router.get("/{complaint_id}", response_model=ComplaintOut)
def get_complaint(complaint_id: uuid.UUID, db: DB, actor: Perm("complaints.read")):
    return _out(db, [_get(db, actor, complaint_id)], with_comments=True, actor=actor)[0]


@router.post("/{complaint_id}/assign", response_model=ComplaintOut)
def assign(complaint_id: uuid.UUID, body: ComplaintAssignIn, db: DB, actor: Perm("complaints.manage")):
    """Assign a complaint and (by default) create the linked maintenance job."""
    c = _get(db, actor, complaint_id)
    if c.status in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED):
        raise HTTPException(409, f"Complaint is {c.status}")
    if not body.assigned_staff_id and not body.vendor_id:
        raise HTTPException(422, "Assign to a staff member or a vendor")
    old = {"status": c.status, "assigned_staff_id": c.assigned_staff_id, "vendor_id": c.vendor_id}
    c.assigned_staff_id, c.vendor_id = body.assigned_staff_id, body.vendor_id
    if body.create_task and not c.maintenance_task_id:
        category = body.task_category or CATEGORY_TO_TASK.get(c.category.lower(), TaskCategory.REPAIRS)
        task = msvc.create_task(
            db,
            actor,
            actor.tenant_id,
            dict(
                title=c.title,
                description=c.description,
                category=category,
                priority=c.priority,
                property_id=c.property_id,
                complaint_id=c.id,
                source="complaint",
                due_at=body.due_at,
                assigned_staff_id=body.assigned_staff_id,
                vendor_id=body.vendor_id,
            ),
        )
        c.maintenance_task_id = task.id
    elif c.maintenance_task_id:
        task = db.get(MaintenanceTask, c.maintenance_task_id)
        msvc.assign(db, actor, task, body.assigned_staff_id, body.vendor_id, due_at=body.due_at)
    if c.status == ComplaintStatus.OPEN:
        c.status = ComplaintStatus.ASSIGNED
    audit.record(
        db,
        actor,
        "complaint.assigned",
        "complaint",
        c.id,
        old=old,
        new={"status": c.status, "assigned_staff_id": c.assigned_staff_id, "vendor_id": c.vendor_id, "task": c.maintenance_task_id},
    )
    notifications.notify(db, actor.tenant_id, [c.raised_by], "complaint_update", f"{c.number} assigned", c.title, "complaint", c.id)
    db.commit()
    return _out(db, [c], True, actor)[0]


ALLOWED = {
    ComplaintStatus.OPEN: {ComplaintStatus.ASSIGNED, ComplaintStatus.IN_PROGRESS, ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED},
    ComplaintStatus.ASSIGNED: {ComplaintStatus.IN_PROGRESS, ComplaintStatus.RESOLVED, ComplaintStatus.OPEN},
    ComplaintStatus.IN_PROGRESS: {ComplaintStatus.RESOLVED, ComplaintStatus.ASSIGNED},
    ComplaintStatus.RESOLVED: {ComplaintStatus.CLOSED, ComplaintStatus.IN_PROGRESS},
    ComplaintStatus.CLOSED: {ComplaintStatus.OPEN},
}


@router.post("/{complaint_id}/status", response_model=ComplaintOut)
def change_status(complaint_id: uuid.UUID, body: ComplaintStatusIn, db: DB, actor: Perm("complaints.read")):
    c = _get(db, actor, complaint_id)
    target = ComplaintStatus(body.status)
    is_raiser = c.raised_by == actor.id
    # Raisers may close a resolved complaint or reopen one; everything else is for managers.
    if not actor.can("complaints.manage"):
        if not (
            is_raiser
            and (c.status, target)
            in ((ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED), (ComplaintStatus.RESOLVED, ComplaintStatus.IN_PROGRESS))
        ):
            raise HTTPException(403, "Only supervisors can change complaint status")
    if target not in ALLOWED[ComplaintStatus(c.status)]:
        raise HTTPException(409, f"Cannot move a complaint from {c.status} to {target}")
    if target == ComplaintStatus.RESOLVED and not (body.resolution or c.resolution):
        raise HTTPException(422, "Describe the resolution")
    old = c.status
    c.status = target
    now = utcnow()
    if target == ComplaintStatus.RESOLVED:
        c.resolved_at = now
        c.resolution = body.resolution or c.resolution
    if target == ComplaintStatus.CLOSED:
        c.closed_at, c.closed_by = now, actor.id
    if body.resolution and target != ComplaintStatus.RESOLVED:
        db.add(ComplaintComment(tenant_id=c.tenant_id, complaint_id=c.id, author_id=actor.id, body=body.resolution))
    audit.record(
        db, actor, "complaint.status_changed", "complaint", c.id, old={"status": old}, new={"status": target, "note": body.resolution}
    )
    if not is_raiser:
        notifications.notify(
            db,
            c.tenant_id,
            [c.raised_by],
            "complaint_update",
            f"{c.number} is now {target.replace('_', ' ')}",
            body.resolution,
            "complaint",
            c.id,
        )
    db.commit()
    return _out(db, [c], True, actor)[0]


@router.post("/{complaint_id}/comments", response_model=ComplaintCommentOut, status_code=201)
def comment(complaint_id: uuid.UUID, body: ComplaintCommentIn, db: DB, actor: Perm("complaints.read")):
    c = _get(db, actor, complaint_id)
    if body.internal and not actor.is_manager():
        raise HTTPException(403, "Only supervisors can add internal notes")
    x = ComplaintComment(tenant_id=c.tenant_id, complaint_id=c.id, author_id=actor.id, body=body.body, internal=body.internal)
    db.add(x)
    if not body.internal and actor.id != c.raised_by:
        notifications.notify(
            db, c.tenant_id, [c.raised_by], "complaint_update", f"New comment on {c.number}", body.body[:200], "complaint", c.id
        )
    db.commit()
    return ComplaintCommentOut.model_validate(x).model_copy(update={"author_name": actor.user.full_name})
