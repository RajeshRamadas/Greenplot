import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import and_, or_, select

from app.api.v1._util import Limit, Offset, apply, paginate, property_labels, user_names, vendor_names
from app.core.deps import DB, Actor, CurrentActor, Perm
from app.models import (
    Asset,
    AuditLog,
    ChecklistTemplate,
    Complaint,
    EvidenceException,
    EvidencePolicy,
    Inspection,
    MaintenanceChecklistItem,
    MaintenanceComment,
    MaintenanceMaterial,
    MaintenanceSchedule,
    MaintenanceTask,
    Media,
    Property,
)
from app.models.base import utcnow
from app.models.enums import GARDENING_CATEGORIES, Role, TaskCategory, TaskStatus
from app.schemas.common import Page, ReasonIn
from app.schemas.maintenance import (
    AckIn,
    AssignIn,
    ChecklistAdd,
    ChecklistItemOut,
    ChecklistUpdate,
    CommentBody,
    CommentOut,
    CompleteIn,
    EvidenceLinkIn,
    EvidenceOut,
    ExceptionIn,
    ExceptionOut,
    MaterialIn,
    MaterialOut,
    PolicyIn,
    PolicyOut,
    RejectIn,
    ReviewIn,
    ScanIn,
    ScheduleIn,
    ScheduleOut,
    ScheduleUpdate,
    StartIn,
    TaskCreate,
    TaskDetail,
    TaskSummary,
    TaskUpdate,
    TemplateIn,
    TemplateOut,
)
from app.schemas.operations import AuditOut
from app.services import audit
from app.services import maintenance as svc
from app.services.access import get_scoped, get_task, is_task_worker, scope_tasks, tenant_select
from app.services.storage import get_storage

router = APIRouter(prefix="/maintenance", tags=["maintenance"])
S = TaskStatus


# ------------------------------------------------------------------ presenters


def summaries(db, tasks: list[MaintenanceTask]) -> list[TaskSummary]:
    props = property_labels(db, (t.property_id for t in tasks))
    names = user_names(db, (t.assigned_staff_id for t in tasks))
    vendors = vendor_names(db, (t.vendor_id for t in tasks))
    now = utcnow()
    out = []
    for t in tasks:
        s = TaskSummary.model_validate(t)
        s.overdue = svc.is_overdue(t, now)
        s.property_label = props.get(t.property_id)
        s.assignee_name = names.get(t.assigned_staff_id)
        s.vendor_name = vendors.get(t.vendor_id)
        out.append(s)
    return out


def evidence_visible_to(db, actor: Actor, task: MaintenanceTask) -> bool:
    if actor.role != Role.RESIDENT:
        return True
    mode = svc.tenant_setting(db, task.tenant_id, "resident_evidence_visibility", "after_approval")
    if mode == "none":
        return False
    if mode == "after_approval":
        return task.status in (S.APPROVED, S.CLOSED)
    return True


def allowed_actions(actor: Actor, task: MaintenanceTask) -> list[str]:
    acts = []
    worker = is_task_worker(actor, task)
    for action, (sources, _) in svc.TRANSITIONS.items():
        if task.status not in sources:
            continue
        if action in ("accept", "decline", "start", "complete") and worker:
            acts.append(action)
        elif action in ("assign", "cancel") and actor.can("maintenance.assign"):
            acts.append(action)
        elif action in ("approve", "reject", "reopen") and actor.can("maintenance.review") and task.completed_by != actor.id:
            acts.append(action)
        elif action == "close" and actor.can("maintenance.review"):
            acts.append(action)
    if worker and task.status in svc.EVIDENCE_STATES:
        acts += ["upload_evidence", "add_exception"]
        if task.asset_id:
            acts.append("scan_asset")
    if worker and task.status in svc.EDIT_STATES:
        acts += ["edit_checklist", "add_material", "edit_notes"]
    if actor.role == Role.RESIDENT and task.status in (S.APPROVED, S.CLOSED) and not task.resident_ack_at:
        acts.append("acknowledge")
    if actor.can("reports.proof") and task.status in (S.APPROVED, S.CLOSED, S.COMPLETED):
        acts.append("download_report")
    return acts


def detail(db, actor: Actor, task: MaintenanceTask) -> TaskDetail:
    d = TaskDetail.model_validate(task)
    base = summaries(db, [task])[0]
    for f in ("overdue", "property_label", "assignee_name", "vendor_name"):
        setattr(d, f, getattr(base, f))
    names = user_names(db, [task.supervisor_id, task.completed_by, task.reviewed_by])
    d.supervisor_name = names.get(task.supervisor_id)
    d.completed_by_name = names.get(task.completed_by)
    d.reviewed_by_name = names.get(task.reviewed_by)
    if task.asset_id:
        a = db.get(Asset, task.asset_id)
        d.asset_label = f"{a.name} ({a.code})" if a else None
    d.materials_cost = float(sum((m.quantity or 0) * (m.unit_cost or 0) for m in task.materials))
    if evidence_visible_to(db, actor, task):
        storage = get_storage()
        evs = svc.current_evidence(db, task)
        uploader = user_names(db, (e.uploaded_by for e in evs))
        out = []
        for e in evs:
            eo = EvidenceOut.model_validate(e)
            eo.uploaded_by_name = uploader.get(e.uploaded_by)
            if e.media and e.media.status == "ready":
                eo.content_type = e.media.content_type
                eo.url = storage.download_url(e.media.storage_key, e.media.original_filename)
                if e.media.thumbnail_key:
                    eo.thumbnail_url = storage.download_url(e.media.thumbnail_key)
            out.append(eo)
        d.evidence = out
    d.exceptions = [
        ExceptionOut.model_validate(x)
        for x in db.scalars(select(EvidenceException).where(EvidenceException.task_id == task.id).order_by(EvidenceException.created_at))
    ]
    comments = list(
        db.scalars(select(MaintenanceComment).where(MaintenanceComment.task_id == task.id).order_by(MaintenanceComment.created_at))
    )
    authors = user_names(db, (c.author_id for c in comments))
    d.comments = [CommentOut.model_validate(c).model_copy(update={"author_name": authors.get(c.author_id)}) for c in comments]
    if actor.role != Role.RESIDENT:
        d.proof = svc.proof_status(db, task)
    else:
        d.work_notes = d.work_notes if evidence_visible_to(db, actor, task) else None
    d.allowed_actions = allowed_actions(actor, task)
    return d


def _commit_detail(db, actor, task) -> TaskDetail:
    db.commit()
    db.refresh(task)
    return detail(db, actor, task)


# ------------------------------------------------------------------ configuration (declared before /{id})


@router.get("/policies", response_model=list[PolicyOut])
def list_policies(db: DB, actor: Perm("maintenance.read")):
    svc.ensure_default_policies(db, actor.tenant_id)
    db.commit()
    return list(db.scalars(select(EvidencePolicy).where(EvidencePolicy.tenant_id == actor.tenant_id).order_by(EvidencePolicy.category)))


@router.patch("/policies/{category}", response_model=PolicyOut)
def update_policy(category: TaskCategory, body: PolicyIn, db: DB, actor: Perm("maintenance.configure")):
    svc.ensure_default_policies(db, actor.tenant_id)
    db.flush()
    row = db.scalar(select(EvidencePolicy).where(EvidencePolicy.tenant_id == actor.tenant_id, EvidencePolicy.category == category))
    before = audit.snapshot(row, svc.POLICY_FIELDS)
    apply(row, body.model_dump(exclude_none=True))
    old, new = audit.diff(before, audit.snapshot(row, svc.POLICY_FIELDS))
    audit.record(db, actor, "config.evidence_policy_changed", "evidence_policy", row.id, old={"category": category, **old}, new=new)
    db.commit()
    return row


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(db: DB, actor: Perm("maintenance.read"), category: TaskCategory | None = None):
    stmt = tenant_select(ChecklistTemplate, actor).order_by(ChecklistTemplate.category, ChecklistTemplate.name)
    if category:
        stmt = stmt.where(ChecklistTemplate.category == category)
    return list(db.scalars(stmt))


@router.post("/templates", response_model=TemplateOut, status_code=201)
def create_template(body: TemplateIn, db: DB, actor: Perm("maintenance.configure")):
    t = ChecklistTemplate(tenant_id=actor.tenant_id, **body.model_dump())
    db.add(t)
    db.flush()
    audit.record(db, actor, "config.checklist_template_created", "checklist_template", t.id, new=body.model_dump())
    db.commit()
    return t


@router.put("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: uuid.UUID, body: TemplateIn, db: DB, actor: Perm("maintenance.configure")):
    t = get_scoped(db, ChecklistTemplate, template_id, actor, "Template")
    before = audit.snapshot(t)
    apply(t, body.model_dump())
    old, new = audit.diff(before, audit.snapshot(t))
    audit.record(db, actor, "config.checklist_template_changed", "checklist_template", t.id, old=old, new=new)
    db.commit()
    return t


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: uuid.UUID, db: DB, actor: Perm("maintenance.configure")):
    t = get_scoped(db, ChecklistTemplate, template_id, actor, "Template")
    t.deleted_at = utcnow()
    audit.record(db, actor, "config.checklist_template_deleted", "checklist_template", t.id, old={"name": t.name})
    db.commit()


@router.get("/schedules", response_model=list[ScheduleOut])
def list_schedules(db: DB, actor: Perm("maintenance.read"), category: TaskCategory | None = None):
    stmt = tenant_select(MaintenanceSchedule, actor).order_by(MaintenanceSchedule.next_run_on)
    if category:
        stmt = stmt.where(MaintenanceSchedule.category == category)
    return list(db.scalars(stmt))


@router.post("/schedules", response_model=ScheduleOut, status_code=201)
def create_schedule(body: ScheduleIn, db: DB, actor: Perm("schedules.manage")):
    if body.property_id:
        get_scoped(db, Property, body.property_id, actor, "Property")
    if body.asset_id:
        get_scoped(db, Asset, body.asset_id, actor, "Asset")
    s = MaintenanceSchedule(tenant_id=actor.tenant_id, **body.model_dump())
    db.add(s)
    db.flush()
    audit.record(db, actor, "schedule.created", "maintenance_schedule", s.id, new=audit.snapshot(s))
    db.commit()
    return s


@router.patch("/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: uuid.UUID, body: ScheduleUpdate, db: DB, actor: Perm("schedules.manage")):
    s = get_scoped(db, MaintenanceSchedule, schedule_id, actor, "Schedule")
    before = audit.snapshot(s)
    apply(s, body.model_dump(exclude_unset=True))
    old, new = audit.diff(before, audit.snapshot(s))
    audit.record(db, actor, "schedule.updated", "maintenance_schedule", s.id, old=old, new=new)
    db.commit()
    return s


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: uuid.UUID, db: DB, actor: Perm("schedules.manage")):
    s = get_scoped(db, MaintenanceSchedule, schedule_id, actor, "Schedule")
    s.deleted_at = utcnow()
    s.is_active = False
    audit.record(db, actor, "schedule.deleted", "maintenance_schedule", s.id)
    db.commit()


@router.post("/schedules/run")
def run_schedules(db: DB, actor: Perm("schedules.manage")):
    from app.services.jobs import generate_scheduled_tasks

    created = generate_scheduled_tasks(db, tenant_id=actor.tenant_id)
    db.commit()
    return {"created": [t.number for t in created]}


# ------------------------------------------------------------------ CRUD


@router.post("", response_model=TaskDetail, status_code=201)
def create_task(body: TaskCreate, db: DB, actor: Perm("maintenance.create")):
    data = body.model_dump()
    if body.property_id:
        get_scoped(db, Property, body.property_id, actor, "Property")
    if body.complaint_id:
        c = get_scoped(db, Complaint, body.complaint_id, actor, "Complaint")
        data["source"] = "complaint"
        data["property_id"] = data["property_id"] or c.property_id
    if body.inspection_id:
        get_scoped(db, Inspection, body.inspection_id, actor, "Inspection")
        data["source"] = "inspection"
    task = svc.create_task(db, actor, actor.tenant_id, data)
    if body.complaint_id:
        c.maintenance_task_id = task.id
    return _commit_detail(db, actor, task)


@router.get("", response_model=Page[TaskSummary])
def list_tasks(
    db: DB,
    actor: Perm("maintenance.read"),
    status: list[TaskStatus] | None = Query(None),
    category: list[TaskCategory] | None = Query(None),
    property_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    staff_id: uuid.UUID | None = None,
    vendor_id: uuid.UUID | None = None,
    layout_id: uuid.UUID | None = None,
    approval: str | None = Query(None, pattern="^(pending|approved|rework|rejected)$"),
    overdue: bool | None = None,
    mine: bool = False,
    q: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = Query("-created_at", pattern="^-?(created_at|due_at|completed_at|priority|number)$"),
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = scope_tasks(tenant_select(MaintenanceTask, actor), db, actor)
    if status:
        stmt = stmt.where(MaintenanceTask.status.in_(status))
    if category:
        stmt = stmt.where(MaintenanceTask.category.in_(category))
    if property_id:
        stmt = stmt.where(MaintenanceTask.property_id == property_id)
    if asset_id:
        stmt = stmt.where(MaintenanceTask.asset_id == asset_id)
    if staff_id:
        stmt = stmt.where(MaintenanceTask.assigned_staff_id == staff_id)
    if vendor_id:
        stmt = stmt.where(MaintenanceTask.vendor_id == vendor_id)
    if layout_id:
        stmt = stmt.where(
            or_(
                MaintenanceTask.layout_id == layout_id,
                MaintenanceTask.property_id.in_(select(Property.id).where(Property.layout_id == layout_id)),
            )
        )
    if approval == "pending":
        stmt = stmt.where(MaintenanceTask.status == S.COMPLETED)
    elif approval == "approved":
        stmt = stmt.where(MaintenanceTask.status.in_([S.APPROVED, S.CLOSED]))
    elif approval in ("rework", "rejected"):
        stmt = stmt.where(MaintenanceTask.review_decision == approval)
    if overdue:
        stmt = stmt.where(and_(MaintenanceTask.due_at < utcnow(), MaintenanceTask.status.in_(list(svc.OPEN_STATES))))
    if mine:
        if actor.role == Role.SUPERVISOR:
            stmt = stmt.where(or_(MaintenanceTask.supervisor_id == actor.id, MaintenanceTask.assigned_staff_id == actor.id))
        elif actor.role not in (Role.STAFF, Role.VENDOR):
            stmt = stmt.where(MaintenanceTask.created_by == actor.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(MaintenanceTask.number.ilike(like), MaintenanceTask.title.ilike(like), MaintenanceTask.description.ilike(like))
        )
    if date_from:
        stmt = stmt.where(MaintenanceTask.created_at >= date_from)
    if date_to:
        stmt = stmt.where(MaintenanceTask.created_at <= date_to)
    col = getattr(MaintenanceTask, sort.lstrip("-"))
    stmt = stmt.order_by(col.desc() if sort.startswith("-") else col.asc(), MaintenanceTask.number.desc())
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=summaries(db, items), total=total, limit=limit, offset=offset)


@router.get("/scan/{code}")
def scan_lookup(code: str, db: DB, actor: Perm("assets.scan")):
    """SCAN ASSET → CONFIRM ASSET: resolve a QR/NFC code to the asset and its open tasks."""
    if not actor.can("maintenance.read"):
        raise HTTPException(403, "Missing permission: maintenance.read")
    from app.schemas.core import AssetOut

    asset = db.scalar(tenant_select(Asset, actor).where(or_(Asset.qr_code == code, Asset.nfc_id == code, Asset.code == code)))
    if not asset:
        raise HTTPException(404, "No asset matches this code")
    stmt = scope_tasks(tenant_select(MaintenanceTask, actor), db, actor).where(
        MaintenanceTask.asset_id == asset.id, MaintenanceTask.status.in_(list(svc.OPEN_STATES))
    )
    return {"asset": AssetOut.model_validate(asset), "open_tasks": summaries(db, list(db.scalars(stmt)))}


@router.get("/{task_id}", response_model=TaskDetail)
def get_task_detail(task_id: uuid.UUID, db: DB, actor: Perm("maintenance.read")):
    return detail(db, actor, get_task(db, actor, task_id))


@router.patch("/{task_id}", response_model=TaskDetail)
def update_task(task_id: uuid.UUID, body: TaskUpdate, db: DB, actor: CurrentActor):
    task = get_task(db, actor, task_id)
    data = body.model_dump(exclude_unset=True)
    worker_fields = {"work_notes", "issue_found", "outcome", "observations"}
    manager_fields = set(data) - worker_fields
    if manager_fields and not actor.can("maintenance.assign"):
        raise HTTPException(403, "Only supervisors can change task details")
    if set(data) & worker_fields:
        svc.ensure_editable(actor, task)
    if manager_fields and task.status in (S.APPROVED, S.CLOSED, S.CANCELLED):
        raise HTTPException(409, "Approved records cannot be edited")
    before = audit.snapshot(task, list(data))
    apply(task, data)
    old, new = audit.diff(before, audit.snapshot(task, list(data)))
    if new:
        audit.record(db, actor, "maintenance.updated", "maintenance_task", task.id, old=old, new=new)
    return _commit_detail(db, actor, task)


# ------------------------------------------------------------------ lifecycle


@router.post("/{task_id}/assign", response_model=TaskDetail)
def assign(task_id: uuid.UUID, body: AssignIn, db: DB, actor: Perm("maintenance.assign")):
    task = get_task(db, actor, task_id)
    svc.assign(db, actor, task, body.assigned_staff_id, body.vendor_id, body.supervisor_id, body.due_at)
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/accept", response_model=TaskDetail)
def accept(task_id: uuid.UUID, db: DB, actor: Perm("maintenance.work")):
    task = get_task(db, actor, task_id)
    svc.accept(db, actor, task)
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/decline", response_model=TaskDetail)
def decline(task_id: uuid.UUID, body: ReasonIn, db: DB, actor: Perm("maintenance.work")):
    task = get_task(db, actor, task_id)
    svc.decline(db, actor, task, body.reason)
    db.commit()
    return detail(db, actor, task) if actor.is_manager() else TaskDetail.model_validate(task)


@router.post("/{task_id}/start", response_model=TaskDetail)
def start(task_id: uuid.UUID, body: StartIn, db: DB, actor: Perm("maintenance.work")):
    task = get_task(db, actor, task_id)
    svc.start(db, actor, task, body.latitude, body.longitude, body.accuracy_m)
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/scan", response_model=TaskDetail)
def scan(task_id: uuid.UUID, body: ScanIn, db: DB, actor: Perm("maintenance.work")):
    task = get_task(db, actor, task_id)
    try:
        svc.record_asset_scan(db, actor, task, body.code, body.method)
    except HTTPException:
        db.commit()  # keep the mismatch audit entry
        raise
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/evidence", response_model=TaskDetail)
def add_evidence(task_id: uuid.UUID, body: EvidenceLinkIn, db: DB, actor: CurrentActor):
    task = get_task(db, actor, task_id)
    media = get_scoped(db, Media, body.media_id, actor, "Media")
    svc.link_evidence(db, actor, task, media, body.evidence_type, body.caption)
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/exceptions", response_model=TaskDetail)
def add_exception(task_id: uuid.UUID, body: ExceptionIn, db: DB, actor: Perm("maintenance.work")):
    task = get_task(db, actor, task_id)
    svc.add_exception(db, actor, task, body.requirement, body.reason_code, body.reason)
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/checklist", response_model=ChecklistItemOut, status_code=201)
def add_checklist_item(task_id: uuid.UUID, body: ChecklistAdd, db: DB, actor: Perm("maintenance.assign")):
    task = get_task(db, actor, task_id)
    if task.status not in (S.CREATED, S.ASSIGNED, S.ACCEPTED, S.STARTED, S.REWORK_REQUIRED):
        raise HTTPException(409, "Checklist is locked")
    item = MaintenanceChecklistItem(tenant_id=task.tenant_id, task_id=task.id, position=len(task.checklist), label=body.label)
    db.add(item)
    audit.record(db, actor, "maintenance.checklist_item_added", "maintenance_task", task.id, new={"label": body.label})
    db.commit()
    return item


@router.patch("/{task_id}/checklist/{item_id}", response_model=TaskDetail)
def update_checklist(task_id: uuid.UUID, item_id: uuid.UUID, body: ChecklistUpdate, db: DB, actor: Perm("maintenance.work")):
    task = get_task(db, actor, task_id)
    item = next((i for i in task.checklist if i.id == item_id), None)
    if not item:
        raise HTTPException(404, "Checklist item not found")
    svc.update_checklist_item(db, actor, task, item, body.status, body.reason)
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/materials", response_model=MaterialOut, status_code=201)
def add_material(task_id: uuid.UUID, body: MaterialIn, db: DB, actor: Perm("maintenance.work")):
    task = get_task(db, actor, task_id)
    svc.ensure_editable(actor, task)
    m = MaintenanceMaterial(tenant_id=task.tenant_id, task_id=task.id, added_by=actor.id, **body.model_dump())
    db.add(m)
    db.flush()
    audit.record(db, actor, "maintenance.material_added", "maintenance_task", task.id, new=body.model_dump())
    db.commit()
    return m


@router.delete("/{task_id}/materials/{material_id}", status_code=204)
def delete_material(task_id: uuid.UUID, material_id: uuid.UUID, db: DB, actor: Perm("maintenance.work")):
    task = get_task(db, actor, task_id)
    svc.ensure_editable(actor, task)
    m = next((m for m in task.materials if m.id == material_id), None)
    if not m:
        raise HTTPException(404, "Material not found")
    audit.record(db, actor, "maintenance.material_removed", "maintenance_task", task.id, old={"name": m.name, "quantity": m.quantity})
    task.materials.remove(m)
    db.commit()


@router.get("/{task_id}/proof")
def proof(task_id: uuid.UUID, db: DB, actor: Perm("maintenance.read")):
    return svc.proof_status(db, get_task(db, actor, task_id))


@router.post("/{task_id}/complete", response_model=TaskDetail)
def complete(task_id: uuid.UUID, body: CompleteIn, db: DB, actor: Perm("maintenance.work")):
    task = get_task(db, actor, task_id)
    if body.work_notes is not None or body.outcome is not None:
        svc.ensure_editable(actor, task)
        if body.work_notes is not None:
            task.work_notes = body.work_notes
        if body.outcome is not None:
            task.outcome = body.outcome
    svc.complete(db, actor, task, body.latitude, body.longitude, body.accuracy_m)
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/approve", response_model=TaskDetail)
def approve(task_id: uuid.UUID, body: ReviewIn, db: DB, actor: Perm("maintenance.review")):
    task = get_task(db, actor, task_id)
    svc.approve(db, actor, task, body.comment)
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/reject", response_model=TaskDetail)
def reject(task_id: uuid.UUID, body: RejectIn, db: DB, actor: Perm("maintenance.review")):
    task = get_task(db, actor, task_id)
    svc.reject(db, actor, task, body.comment, body.decision)
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/rework", response_model=TaskDetail)
def request_rework(task_id: uuid.UUID, body: ReviewIn, db: DB, actor: Perm("maintenance.review")):
    task = get_task(db, actor, task_id)
    svc.reject(db, actor, task, body.comment or "", "rework")
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/close", response_model=TaskDetail)
def close(task_id: uuid.UUID, db: DB, actor: Perm("maintenance.review")):
    task = get_task(db, actor, task_id)
    svc.close(db, actor, task)
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/reopen", response_model=TaskDetail)
def reopen(task_id: uuid.UUID, body: ReasonIn, db: DB, actor: Perm("maintenance.review")):
    task = get_task(db, actor, task_id)
    svc.reopen(db, actor, task, body.reason)
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/cancel", response_model=TaskDetail)
def cancel(task_id: uuid.UUID, body: ReasonIn, db: DB, actor: Perm("maintenance.cancel")):
    task = get_task(db, actor, task_id)
    svc.cancel(db, actor, task, body.reason)
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/acknowledge", response_model=TaskDetail)
def acknowledge(task_id: uuid.UUID, body: AckIn, db: DB, actor: Perm("maintenance.acknowledge")):
    task = get_task(db, actor, task_id)
    svc.acknowledge(db, actor, task, body.note)
    return _commit_detail(db, actor, task)


@router.post("/{task_id}/comments", response_model=CommentOut, status_code=201)
def comment(task_id: uuid.UUID, body: CommentBody, db: DB, actor: Perm("maintenance.read")):
    task = get_task(db, actor, task_id)
    c = MaintenanceComment(tenant_id=task.tenant_id, task_id=task.id, author_id=actor.id, body=body.body)
    db.add(c)
    db.commit()
    return CommentOut.model_validate(c).model_copy(update={"author_name": actor.user.full_name})


@router.get("/{task_id}/audit", response_model=list[AuditOut])
def task_audit(task_id: uuid.UUID, db: DB, actor: Perm("maintenance.read")):
    task = get_task(db, actor, task_id)
    if actor.role == Role.RESIDENT:
        raise HTTPException(403, "Audit history is available to layout staff")
    rows = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.tenant_id == actor.tenant_id, AuditLog.entity_type == "maintenance_task", AuditLog.entity_id == task.id)
            .order_by(AuditLog.timestamp)
        )
    )
    names = user_names(db, (r.actor_id for r in rows))
    return [AuditOut.model_validate(r).model_copy(update={"actor_name": names.get(r.actor_id)}) for r in rows]


@router.get("/{task_id}/report.pdf")
def proof_report(task_id: uuid.UUID, db: DB, actor: Perm("reports.proof")):
    """Downloadable Maintenance Proof of Work report (§40)."""
    from app.services.reports import proof_report_pdf

    task = get_task(db, actor, task_id)
    if task.status not in (S.COMPLETED, S.APPROVED, S.CLOSED):
        raise HTTPException(409, "The proof report is available once work is submitted")
    pdf = proof_report_pdf(db, task, include_evidence=evidence_visible_to(db, actor, task))
    audit.record(db, actor, "maintenance.proof_report_downloaded", "maintenance_task", task.id)
    db.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{task.number}-proof.pdf"'})


# ------------------------------------------------------------------ /tasks and /gardening

tasks_router = APIRouter(tags=["maintenance"])


@tasks_router.get("/tasks/mine")
def my_tasks(db: DB, actor: CurrentActor):
    """Everything assigned to the caller: maintenance jobs and inspections."""
    tasks = []
    if actor.can("maintenance.work"):
        stmt = tenant_select(MaintenanceTask, actor).where(
            MaintenanceTask.status.in_([S.ASSIGNED, S.ACCEPTED, S.STARTED, S.REWORK_REQUIRED, S.COMPLETED])
        )
        if actor.role == Role.VENDOR:
            stmt = stmt.where(MaintenanceTask.vendor_id == actor.user.vendor_id)
        else:
            stmt = stmt.where(MaintenanceTask.assigned_staff_id == actor.id)
        tasks = summaries(db, list(db.scalars(stmt.order_by(MaintenanceTask.due_at.is_(None), MaintenanceTask.due_at))))
    inspections = []
    if actor.can("inspections.perform"):
        from app.schemas.maintenance import InspectionOut

        stmt = tenant_select(Inspection, actor).where(
            Inspection.inspector_id == actor.id, Inspection.status.in_(["scheduled", "in_progress"])
        )
        inspections = [InspectionOut.model_validate(i) for i in db.scalars(stmt.order_by(Inspection.scheduled_for))]
    return {"maintenance": tasks, "inspections": inspections}


@tasks_router.get("/gardening", response_model=Page[TaskSummary])
def gardening(db: DB, actor: Perm("maintenance.read"), status: TaskStatus | None = None, limit: int = Limit, offset: int = Offset):
    stmt = scope_tasks(tenant_select(MaintenanceTask, actor), db, actor).where(
        MaintenanceTask.category.in_([c.value for c in GARDENING_CATEGORIES])
    )
    if status:
        stmt = stmt.where(MaintenanceTask.status == status)
    items, total = paginate(db, stmt.order_by(MaintenanceTask.created_at.desc()), limit, offset)
    return Page(items=summaries(db, items), total=total, limit=limit, offset=offset)
