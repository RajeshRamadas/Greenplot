import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.v1._util import Limit, Offset, paginate, property_labels, user_names
from app.core.deps import DB, Perm
from app.models import Inspection, InspectionItem, MaintenanceTask, Media, Property, User
from app.models.base import utcnow
from app.models.enums import INSPECTION_POINTS, InspectionStatus, Role, TaskCategory
from app.schemas.common import Page
from app.schemas.maintenance import (
    FollowUpIn,
    InspectionCompleteIn,
    InspectionIn,
    InspectionItemIn,
    InspectionOut,
    TaskDetail,
)
from app.services import audit, notifications
from app.services import maintenance as msvc
from app.services.access import can_view_inspection, get_scoped, not_found, resident_property_ids, scope_inspections, tenant_select
from app.services.numbering import next_number

router = APIRouter(prefix="/inspections", tags=["inspections"])

POINT_TO_CATEGORY = {
    "boundary": TaskCategory.CIVIL,
    "gate": TaskCategory.GATE_FENCE,
    "fencing": TaskCategory.GATE_FENCE,
    "vegetation": TaskCategory.GARDENING,
    "garden": TaskCategory.GARDENING,
    "water_utilities": TaskCategory.PLUMBING,
    "streetlights": TaskCategory.ELECTRICAL,
    "drainage": TaskCategory.CIVIL,
    "security": TaskCategory.REPAIRS,
    "common_infrastructure": TaskCategory.REPAIRS,
}


def _out(db, items: list[Inspection], media=False) -> list[InspectionOut]:
    props = property_labels(db, (i.property_id for i in items))
    names = user_names(db, (i.inspector_id for i in items))
    out = []
    for i in items:
        o = InspectionOut.model_validate(i)
        o.property_label = props.get(i.property_id)
        o.inspector_name = names.get(i.inspector_id)
        if media:
            from app.api.v1.media import present

            o.media = [
                present(db, m)
                for m in db.scalars(
                    select(Media)
                    .where(Media.entity_type == "inspection", Media.entity_id == i.id, Media.status == "ready")
                    .order_by(Media.created_at)
                )
            ]
        out.append(o)
    return out


def _get(db, actor, inspection_id) -> Inspection:
    i = get_scoped(db, Inspection, inspection_id, actor, "Inspection")
    if not can_view_inspection(db, actor, i):
        raise not_found("Inspection")
    return i


@router.get("", response_model=Page[InspectionOut])
def list_inspections(
    db: DB,
    actor: Perm("inspections.read"),
    property_id: uuid.UUID | None = None,
    status: InspectionStatus | None = None,
    property_watch: bool | None = None,
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = scope_inspections(tenant_select(Inspection, actor), db, actor).order_by(Inspection.created_at.desc())
    if property_id:
        stmt = stmt.where(Inspection.property_id == property_id)
    if status:
        stmt = stmt.where(Inspection.status == status)
    if property_watch is not None:
        stmt = stmt.where(Inspection.is_property_watch.is_(property_watch))
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=_out(db, items), total=total, limit=limit, offset=offset)


@router.post("", response_model=InspectionOut, status_code=201)
def create_inspection(body: InspectionIn, db: DB, actor: Perm("inspections.request")):
    """Schedule an inspection. Residents use this to request a Property Watch visit."""
    get_scoped(db, Property, body.property_id, actor, "Property")
    if actor.role == Role.RESIDENT:
        if body.property_id not in resident_property_ids(db, actor):
            raise HTTPException(403, "You can only request visits for your own property")
        body.inspector_id = None
        body.is_property_watch = True
    if body.inspector_id:
        u = db.get(User, body.inspector_id)
        if not u or u.tenant_id != actor.tenant_id or u.role not in (Role.STAFF, Role.SUPERVISOR):
            raise HTTPException(422, "Inspector must be a staff member or supervisor")
    points = body.points or INSPECTION_POINTS
    unknown = set(points) - set(INSPECTION_POINTS)
    if unknown:
        raise HTTPException(422, f"Unknown inspection points: {', '.join(sorted(unknown))}")
    i = Inspection(
        tenant_id=actor.tenant_id,
        number=next_number(db, actor.tenant_id, "INS"),
        property_id=body.property_id,
        inspector_id=body.inspector_id,
        is_property_watch=body.is_property_watch,
        scheduled_for=body.scheduled_for,
    )
    for pos, point in enumerate(points):
        i.items.append(InspectionItem(tenant_id=actor.tenant_id, position=pos, point=point))
    db.add(i)
    db.flush()
    audit.record(db, actor, "inspection.scheduled", "inspection", i.id, new={"property_id": i.property_id, "inspector_id": i.inspector_id})
    if body.inspector_id:
        notifications.notify(db, actor.tenant_id, [body.inspector_id], "task_assigned", f"Inspection {i.number}", None, "inspection", i.id)
    elif actor.role == Role.RESIDENT:
        notifications.notify(
            db,
            actor.tenant_id,
            notifications.managers(db, actor.tenant_id),
            "task_assigned",
            f"Property Watch requested ({i.number})",
            None,
            "inspection",
            i.id,
        )
    db.commit()
    return _out(db, [i])[0]


@router.get("/{inspection_id}", response_model=InspectionOut)
def get_inspection(inspection_id: uuid.UUID, db: DB, actor: Perm("inspections.read")):
    return _out(db, [_get(db, actor, inspection_id)], media=True)[0]


@router.post("/{inspection_id}/assign", response_model=InspectionOut)
def assign_inspector(inspection_id: uuid.UUID, inspector_id: uuid.UUID, db: DB, actor: Perm("inspections.manage")):
    i = _get(db, actor, inspection_id)
    u = db.get(User, inspector_id)
    if not u or u.tenant_id != actor.tenant_id or u.role not in (Role.STAFF, Role.SUPERVISOR):
        raise HTTPException(422, "Inspector must be a staff member or supervisor")
    old = i.inspector_id
    i.inspector_id = inspector_id
    audit.record(db, actor, "inspection.assigned", "inspection", i.id, old={"inspector_id": old}, new={"inspector_id": inspector_id})
    notifications.notify(db, actor.tenant_id, [inspector_id], "task_assigned", f"Inspection {i.number}", None, "inspection", i.id)
    db.commit()
    return _out(db, [i])[0]


def _ensure_inspector(actor, i: Inspection):
    if i.inspector_id != actor.id and not actor.can("inspections.manage"):
        raise HTTPException(403, "Only the assigned inspector can record this inspection")


@router.post("/{inspection_id}/start", response_model=InspectionOut)
def start(inspection_id: uuid.UUID, db: DB, actor: Perm("inspections.perform")):
    i = _get(db, actor, inspection_id)
    _ensure_inspector(actor, i)
    if i.status != InspectionStatus.SCHEDULED:
        raise HTTPException(409, f"Inspection is {i.status}")
    i.status = InspectionStatus.IN_PROGRESS
    i.started_at = utcnow()
    i.inspector_id = i.inspector_id or actor.id
    audit.record(db, actor, "inspection.started", "inspection", i.id)
    db.commit()
    return _out(db, [i])[0]


@router.patch("/{inspection_id}/items/{item_id}", response_model=InspectionOut)
def record_item(inspection_id: uuid.UUID, item_id: uuid.UUID, body: InspectionItemIn, db: DB, actor: Perm("inspections.perform")):
    i = _get(db, actor, inspection_id)
    _ensure_inspector(actor, i)
    if i.status != InspectionStatus.IN_PROGRESS:
        raise HTTPException(409, "Start the inspection first")
    item = next((x for x in i.items if x.id == item_id), None)
    if not item:
        raise HTTPException(404, "Inspection point not found")
    if body.condition in ("attention", "issue") and not body.notes:
        raise HTTPException(422, "Describe the finding for points needing attention")
    item.condition, item.notes = body.condition, body.notes
    db.commit()
    return _out(db, [i])[0]


@router.post("/{inspection_id}/complete", response_model=InspectionOut)
def complete(inspection_id: uuid.UUID, body: InspectionCompleteIn, db: DB, actor: Perm("inspections.perform")):
    i = _get(db, actor, inspection_id)
    _ensure_inspector(actor, i)
    if i.status != InspectionStatus.IN_PROGRESS:
        raise HTTPException(409, f"Inspection is {i.status}")
    missing = [x.point for x in i.items if not x.condition]
    if missing:
        raise HTTPException(422, {"message": "Record every inspection point", "missing": missing})
    photos = db.scalar(select(Media.id).where(Media.entity_type == "inspection", Media.entity_id == i.id, Media.status == "ready").limit(1))
    if not photos and msvc.get_policy(db, i.tenant_id, TaskCategory.INSPECTION)["after_photo"]:
        raise HTTPException(422, {"message": "Attach at least one photo of the property", "missing": ["photo"]})
    i.status = InspectionStatus.COMPLETED
    i.completed_at = utcnow()
    i.overall_condition = body.overall_condition
    i.findings = body.findings
    i.latitude, i.longitude = body.latitude, body.longitude
    prop = db.get(Property, i.property_id)
    prop.condition = body.overall_condition
    audit.record(
        db, actor, "inspection.completed", "inspection", i.id, new={"overall_condition": body.overall_condition, "findings": body.findings}
    )
    owners = [prop.owner_user_id]
    from app.models import Resident

    owners += list(db.scalars(select(Resident.user_id).where(Resident.property_id == prop.id, Resident.user_id.is_not(None))))
    notifications.notify(
        db,
        i.tenant_id,
        owners,
        "task_completed",
        f"Property Watch report ready · Plot {prop.plot_number}",
        body.findings,
        "inspection",
        i.id,
    )
    db.commit()
    return _out(db, [i])[0]


@router.post("/{inspection_id}/follow-up", response_model=TaskDetail, status_code=201)
def follow_up(inspection_id: uuid.UUID, body: FollowUpIn, db: DB, actor: Perm("inspections.manage")):
    """Turn an inspection finding into a maintenance job (§7)."""
    from app.api.v1.maintenance import detail

    i = _get(db, actor, inspection_id)
    item = next((x for x in i.items if x.id == body.item_id), None)
    if not item:
        raise HTTPException(404, "Inspection point not found")
    if item.follow_up_task_id:
        raise HTTPException(409, "A follow-up task already exists for this finding")
    task = msvc.create_task(
        db,
        actor,
        actor.tenant_id,
        dict(
            title=body.title or f"{item.point.replace('_', ' ').title()} follow-up from {i.number}",
            description=item.notes,
            category=body.category or POINT_TO_CATEGORY.get(item.point, TaskCategory.REPAIRS),
            priority=body.priority,
            property_id=i.property_id,
            inspection_id=i.id,
            source="inspection",
            assigned_staff_id=body.assigned_staff_id,
            vendor_id=body.vendor_id,
        ),
    )
    item.follow_up_task_id = task.id
    db.commit()
    db.refresh(task)
    return detail(db, actor, db.get(MaintenanceTask, task.id))
