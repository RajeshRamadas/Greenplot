"""Maintenance lifecycle and Proof of Work rules (requirements §8-11, §31, §42, §48).

CREATED → ASSIGNED → ACCEPTED → STARTED → COMPLETED → APPROVED → CLOSED
COMPLETED → REWORK_REQUIRED → STARTED → COMPLETED
"""

import uuid
from datetime import date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import (
    Asset,
    ChecklistTemplate,
    Complaint,
    EvidenceException,
    EvidencePolicy,
    MaintenanceChecklistItem,
    MaintenanceComment,
    MaintenanceEvidence,
    MaintenanceTask,
    Media,
    Tenant,
    User,
    Vendor,
)
from app.models.base import utcnow
from app.models.enums import (
    DOCUMENT_EVIDENCE,
    ChecklistStatus,
    ComplaintStatus,
    EvidenceType,
    MediaStatus,
    RequirementKey,
    Role,
    TaskCategory,
    TaskStatus,
)
from app.services import audit, notifications
from app.services.access import is_task_worker
from app.services.numbering import next_number

S = TaskStatus

TRANSITIONS: dict[str, tuple[set[TaskStatus], TaskStatus]] = {
    "assign": ({S.CREATED, S.ASSIGNED, S.ACCEPTED}, S.ASSIGNED),
    "accept": ({S.ASSIGNED}, S.ACCEPTED),
    "decline": ({S.ASSIGNED, S.ACCEPTED}, S.CREATED),
    "start": ({S.ASSIGNED, S.ACCEPTED, S.REWORK_REQUIRED}, S.STARTED),
    "complete": ({S.STARTED}, S.COMPLETED),
    "approve": ({S.COMPLETED}, S.APPROVED),
    "reject": ({S.COMPLETED}, S.REWORK_REQUIRED),
    "close": ({S.APPROVED}, S.CLOSED),
    "reopen": ({S.APPROVED, S.CLOSED}, S.REWORK_REQUIRED),
    "cancel": ({S.CREATED, S.ASSIGNED, S.ACCEPTED, S.STARTED, S.REWORK_REQUIRED}, S.CANCELLED),
}

# Statuses in which the worker may capture evidence / edit the work record.
EVIDENCE_STATES = {S.ACCEPTED, S.STARTED}
EDIT_STATES = {S.STARTED}
OPEN_STATES = {S.CREATED, S.ASSIGNED, S.ACCEPTED, S.STARTED, S.REWORK_REQUIRED, S.COMPLETED}

# §10 example table. "Optional/Required" and "Configurable" default to the lighter option
# except supervisor approval, which the V1 minimum (§48) requires.
DEFAULT_POLICIES: dict[str, dict] = {
    TaskCategory.CLEANING: dict(before_photo=False),
    TaskCategory.COMPOUND: dict(before_photo=False),
    TaskCategory.GATE_FENCE: dict(before_photo=True),
    TaskCategory.GARDENING: dict(before_photo=True),
    TaskCategory.LANDSCAPING: dict(before_photo=True),
    TaskCategory.ELECTRICAL: dict(before_photo=True),
    TaskCategory.PLUMBING: dict(before_photo=True),
    TaskCategory.CIVIL: dict(before_photo=True),
    TaskCategory.PAINTING: dict(before_photo=True),
    TaskCategory.INSPECTION: dict(before_photo=True),
    TaskCategory.ASSET_SERVICING: dict(before_photo=True, qr_scan=True),
}
POLICY_FIELDS = [
    "before_photo",
    "after_photo",
    "checklist",
    "gps",
    "video",
    "materials",
    "invoice",
    "qr_scan",
    "supervisor_approval",
    "resident_acknowledgement",
]

DEFAULT_CHECKLISTS: dict[str, list[str]] = {
    TaskCategory.CLEANING: ["Debris and litter removed", "Weeds cleared", "Waste bagged and disposed", "Area swept"],
    TaskCategory.COMPOUND: ["Compound walls cleaned", "Drains cleared", "Waste removed", "Gate area tidied"],
    TaskCategory.GATE_FENCE: [
        "Hinges inspected",
        "Hinges lubricated",
        "Alignment adjusted",
        "Lock/latch tested",
        "Gate opens and closes smoothly",
    ],
    TaskCategory.GARDENING: ["Lawn mowed", "Hedges trimmed", "Weeding done", "Plants watered", "Clippings removed"],
    TaskCategory.LANDSCAPING: ["Beds prepared", "Planting done", "Pruning done", "Site cleaned"],
    TaskCategory.ELECTRICAL: ["Power isolated before work", "Fault identified", "Repair completed", "Tested after repair"],
    TaskCategory.PLUMBING: ["Leak source identified", "Repair completed", "Pressure tested", "No leaks after test"],
    TaskCategory.INSPECTION: ["Boundary", "Gate", "Fencing", "Vegetation", "Water/utilities", "Drainage"],
    TaskCategory.ASSET_SERVICING: ["Asset identified by scan", "Service performed", "Operation tested"],
}


def http(code: int, msg: str, **extra) -> HTTPException:
    detail = {"message": msg, **extra} if extra else msg
    return HTTPException(code, detail)


# --------------------------------------------------------------------------- policies


def get_policy(db: Session, tenant_id: uuid.UUID, category: str) -> dict:
    row = db.scalar(select(EvidencePolicy).where(EvidencePolicy.tenant_id == tenant_id, EvidencePolicy.category == category))
    if row:
        return {f: getattr(row, f) for f in POLICY_FIELDS}
    base = dict(
        before_photo=False,
        after_photo=True,
        checklist=True,
        gps=False,
        video=False,
        materials=False,
        invoice=False,
        qr_scan=False,
        supervisor_approval=True,
        resident_acknowledgement=False,
    )
    base.update(DEFAULT_POLICIES.get(category, {}))
    return base


def ensure_default_policies(db: Session, tenant_id: uuid.UUID) -> None:
    existing = set(db.scalars(select(EvidencePolicy.category).where(EvidencePolicy.tenant_id == tenant_id)))
    for cat in TaskCategory:
        if cat.value not in existing:
            db.add(EvidencePolicy(tenant_id=tenant_id, category=cat.value, **get_policy(db, tenant_id, cat.value)))
    existing_t = set(db.scalars(select(ChecklistTemplate.category).where(ChecklistTemplate.tenant_id == tenant_id)))
    for cat, items in DEFAULT_CHECKLISTS.items():
        if cat.value not in existing_t:
            db.add(
                ChecklistTemplate(
                    tenant_id=tenant_id, name=f"Standard {cat.value.replace('_', ' ')}", category=cat.value, items=items, is_default=True
                )
            )


def tenant_setting(db: Session, tenant_id: uuid.UUID, key: str, default):
    t = db.get(Tenant, tenant_id)
    return (t.settings or {}).get(key, default) if t else default


# --------------------------------------------------------------------------- creation & assignment


def _validate_assignees(db: Session, tenant_id: uuid.UUID, staff_id: uuid.UUID | None, vendor_id: uuid.UUID | None):
    if staff_id:
        u = db.get(User, staff_id)
        if not u or u.tenant_id != tenant_id or not u.is_active or u.role not in (Role.STAFF, Role.SUPERVISOR):
            raise http(422, "Assigned staff must be an active staff member or supervisor of this layout")
    if vendor_id:
        v = db.get(Vendor, vendor_id)
        if not v or v.tenant_id != tenant_id or v.deleted_at or not v.is_active:
            raise http(422, "Vendor not found or inactive")


def checklist_items_for(db: Session, tenant_id: uuid.UUID, category: str, template_id: uuid.UUID | None, items: list[str] | None):
    if items:
        return items
    tpl = None
    if template_id:
        tpl = db.get(ChecklistTemplate, template_id)
        if not tpl or tpl.tenant_id != tenant_id:
            raise http(422, "Checklist template not found")
    else:
        tpl = db.scalar(
            select(ChecklistTemplate)
            .where(
                ChecklistTemplate.tenant_id == tenant_id,
                ChecklistTemplate.category == category,
                ChecklistTemplate.deleted_at.is_(None),
            )
            .order_by(ChecklistTemplate.is_default.desc(), ChecklistTemplate.created_at)
        )
    return list(tpl.items) if tpl else list(DEFAULT_CHECKLISTS.get(category, []))


def create_task(db: Session, actor: Actor | None, tenant_id: uuid.UUID, data: dict) -> MaintenanceTask:
    checklist = data.pop("checklist_items", None)
    template_id = data.pop("checklist_template_id", None)
    staff_id = data.get("assigned_staff_id")
    vendor_id = data.get("vendor_id")
    _validate_assignees(db, tenant_id, staff_id, vendor_id)
    if data.get("asset_id"):
        asset = db.get(Asset, data["asset_id"])
        if not asset or asset.tenant_id != tenant_id:
            raise http(422, "Asset not found")
        data.setdefault("property_id", asset.property_id)

    task = MaintenanceTask(tenant_id=tenant_id, number=next_number(db, tenant_id, "MNT"), status=S.CREATED, **data)
    task.created_by = actor.id if actor else None
    for i, label in enumerate(checklist_items_for(db, tenant_id, task.category, template_id, checklist)):
        task.checklist.append(MaintenanceChecklistItem(tenant_id=tenant_id, position=i, label=label))
    db.add(task)
    db.flush()
    audit.record(db, actor, "maintenance.created", "maintenance_task", task.id, new=audit.snapshot(task), tenant_id=tenant_id)
    if staff_id or vendor_id:
        task.assigned_staff_id = None
        task.vendor_id = None
        assign(db, actor, task, staff_id, vendor_id, data.get("supervisor_id"))
    return task


def _transition(db: Session, actor: Actor | None, task: MaintenanceTask, action: str, extra: dict | None = None):
    allowed, target = TRANSITIONS[action]
    if task.status not in allowed:
        raise http(
            status.HTTP_409_CONFLICT,
            f"Cannot {action} a task that is {task.status}",
            current_status=task.status,
        )
    old = task.status
    task.status = target
    audit.record(
        db,
        actor,
        f"maintenance.{action}",
        "maintenance_task",
        task.id,
        old={"status": old},
        new={"status": target, **(extra or {})},
        tenant_id=task.tenant_id,
    )


def assign(db, actor, task, staff_id, vendor_id, supervisor_id=None, due_at=None):
    if not staff_id and not vendor_id:
        raise http(422, "Assign to a staff member or a vendor")
    _validate_assignees(db, task.tenant_id, staff_id, vendor_id)
    if supervisor_id:
        sup = db.get(User, supervisor_id)
        if not sup or sup.tenant_id != task.tenant_id or sup.role not in (Role.SUPERVISOR, Role.LAYOUT_ADMIN):
            raise http(422, "Supervisor not found")
    _transition(db, actor, task, "assign", {"assigned_staff_id": staff_id, "vendor_id": vendor_id, "supervisor_id": supervisor_id})
    task.assigned_staff_id = staff_id
    task.vendor_id = vendor_id
    task.supervisor_id = supervisor_id or task.supervisor_id
    task.assigned_by = actor.id if actor else None
    task.assigned_at = utcnow()
    task.accepted_at = None
    if due_at:
        task.due_at = due_at
    recipients = [staff_id, *notifications.vendor_users(db, task.tenant_id, vendor_id)]
    notifications.notify(
        db, task.tenant_id, recipients, "task_assigned", f"New task {task.number}", task.title, "maintenance_task", task.id
    )
    _sync_complaint(db, task, ComplaintStatus.ASSIGNED)


def _require_worker(actor: Actor, task: MaintenanceTask):
    if not is_task_worker(actor, task):
        raise http(status.HTTP_403_FORBIDDEN, "Only the assigned worker can do this")


def accept(db, actor, task):
    _require_worker(actor, task)
    _transition(db, actor, task, "accept")
    task.accepted_at = utcnow()


def decline(db, actor, task, reason: str):
    _require_worker(actor, task)
    _transition(db, actor, task, "decline", {"reason": reason})
    task.assigned_staff_id = None
    task.vendor_id = None
    task.accepted_at = None
    notifications.notify(
        db,
        task.tenant_id,
        notifications.managers(db, task.tenant_id),
        "task_assigned",
        f"Task {task.number} declined",
        reason,
        "maintenance_task",
        task.id,
    )


def start(db, actor, task, lat=None, lng=None, accuracy=None):
    _require_worker(actor, task)
    was = task.status
    _transition(db, actor, task, "start", {"latitude": lat, "longitude": lng})
    now = utcnow()
    if was == S.ASSIGNED:
        task.accepted_at = now
    if was != S.REWORK_REQUIRED or task.started_at is None:
        task.started_at = task.started_at or now
    if lat is not None and lng is not None:
        task.start_latitude, task.start_longitude, task.gps_accuracy_m = lat, lng, accuracy
    _sync_complaint(db, task, ComplaintStatus.IN_PROGRESS)


def record_asset_scan(db, actor, task, code: str, method: str):
    _require_worker(actor, task)
    if task.status not in EVIDENCE_STATES:
        raise http(409, f"Scan the asset after accepting the task (task is {task.status})")
    if not task.asset_id:
        raise http(422, "This task is not linked to an asset")
    asset = db.get(Asset, task.asset_id)
    field = asset.nfc_id if method == "nfc" else asset.qr_code
    if method != "manual" and code != field:
        audit.record(db, actor, "maintenance.asset_scan_mismatch", "maintenance_task", task.id, new={"scanned": code})
        raise http(422, "Scanned code does not match the asset on this task")
    task.asset_scanned_at = utcnow()
    task.asset_scan_method = method
    audit.record(db, actor, "maintenance.asset_scanned", "maintenance_task", task.id, new={"method": method, "asset": asset.code})


def ensure_editable(actor: Actor, task: MaintenanceTask):
    _require_worker(actor, task)
    if task.status not in EDIT_STATES:
        raise http(409, f"Start the task before recording work (task is {task.status})")


def update_checklist_item(db, actor, task, item: MaintenanceChecklistItem, new_status: str, reason: str | None):
    ensure_editable(actor, task)
    if new_status in (ChecklistStatus.FAILED, ChecklistStatus.SKIPPED) and not (reason and reason.strip()):
        raise http(422, "A reason is required when a checklist item is failed or skipped")
    old = {"status": item.status, "reason": item.reason}
    item.status = new_status
    item.reason = reason.strip() if reason else None
    item.updated_by = actor.id
    item.checked_at = utcnow()
    audit.record(
        db,
        actor,
        "maintenance.checklist_changed",
        "maintenance_task",
        task.id,
        old={"item": item.label, **old},
        new={"item": item.label, "status": new_status, "reason": item.reason},
    )


# --------------------------------------------------------------------------- evidence


def current_evidence(db: Session, task: MaintenanceTask) -> list[MaintenanceEvidence]:
    return list(
        db.scalars(
            select(MaintenanceEvidence)
            .where(MaintenanceEvidence.maintenance_id == task.id, MaintenanceEvidence.status == "active")
            .order_by(MaintenanceEvidence.uploaded_at)
        )
    )


def link_evidence(db, actor, task, media: Media, evidence_type: str, caption: str | None = None) -> MaintenanceEvidence:
    if media.status != MediaStatus.READY:
        raise http(409, "Media upload is not complete")
    if media.entity_type != "maintenance_task" or media.entity_id != task.id:
        raise http(422, "Media belongs to a different record")
    if actor.is_manager() and not is_task_worker(actor, task):
        if evidence_type != EvidenceType.SUPERVISOR and task.status not in EVIDENCE_STATES | {S.COMPLETED}:
            raise http(409, f"Cannot add evidence while task is {task.status}")
    else:
        _require_worker(actor, task)
        if task.status not in EVIDENCE_STATES:
            raise http(409, f"Evidence can only be captured on an accepted or started task (task is {task.status})")
        if evidence_type == EvidenceType.SUPERVISOR:
            raise http(403, "Supervisor evidence is added by the reviewer")
    existing = db.scalar(select(MaintenanceEvidence).where(MaintenanceEvidence.media_id == media.id))
    if existing:
        return existing
    photos = db.scalar(
        select(func.count())
        .select_from(MaintenanceEvidence)
        .where(MaintenanceEvidence.maintenance_id == task.id, MaintenanceEvidence.status == "active")
    )
    from app.core.config import get_settings

    if photos >= get_settings().max_photos_per_task:
        raise http(422, "Maximum evidence items for this task reached")
    ev = MaintenanceEvidence(
        tenant_id=task.tenant_id,
        maintenance_id=task.id,
        entity_type="maintenance_task",
        entity_id=task.id,
        media_id=media.id,
        evidence_type=evidence_type,
        uploaded_by=media.uploaded_by,
        captured_at=media.captured_at,
        uploaded_at=media.uploaded_at or utcnow(),
        latitude=media.latitude,
        longitude=media.longitude,
        sha256=media.sha256,
        rework_round=task.rework_count,
        caption=caption,
    )
    db.add(ev)
    if media.replaces_id:
        old = db.scalar(select(MaintenanceEvidence).where(MaintenanceEvidence.media_id == media.replaces_id))
        if old:
            old.status = "replaced"
    db.flush()
    audit.record(
        db,
        actor,
        "maintenance.evidence_uploaded",
        "maintenance_task",
        task.id,
        new={"evidence_id": ev.id, "media_id": media.id, "type": evidence_type, "sha256": media.sha256, "replaces": media.replaces_id},
    )
    return ev


def add_exception(db, actor, task, requirement: str, reason_code: str, reason: str) -> EvidenceException:
    _require_worker(actor, task)
    if task.status not in EVIDENCE_STATES:
        raise http(409, f"Exceptions are recorded while working on the task (task is {task.status})")
    if not reason or len(reason.strip()) < 5:
        raise http(422, "Explain why the evidence could not be captured")
    exc = EvidenceException(
        tenant_id=task.tenant_id,
        task_id=task.id,
        requirement=requirement,
        reason_code=reason_code,
        reason=reason.strip(),
        raised_by=actor.id,
    )
    db.add(exc)
    db.flush()
    audit.record(
        db,
        actor,
        "maintenance.evidence_exception",
        "maintenance_task",
        task.id,
        new={"requirement": requirement, "reason_code": reason_code, "reason": exc.reason},
    )
    return exc


def proof_status(db: Session, task: MaintenanceTask) -> dict:
    """Which configured requirements are satisfied, excepted or missing."""
    policy = get_policy(db, task.tenant_id, task.category)
    evidence = current_evidence(db, task)
    types_any = {e.evidence_type for e in evidence}
    types_this_round = {e.evidence_type for e in evidence if e.rework_round == task.rework_count}
    excepted = {
        e.requirement
        for e in db.scalars(
            select(EvidenceException).where(EvidenceException.task_id == task.id, EvidenceException.review_status != "rejected")
        )
    }
    pending_items = [i for i in task.checklist if i.status == ChecklistStatus.PENDING]
    bad_reason = [i for i in task.checklist if i.status in (ChecklistStatus.FAILED, ChecklistStatus.SKIPPED) and not i.reason]

    checks: dict[str, bool] = {
        RequirementKey.BEFORE_PHOTO: EvidenceType.BEFORE_PHOTO in types_any,
        RequirementKey.AFTER_PHOTO: EvidenceType.AFTER_PHOTO in types_this_round,
        RequirementKey.CHECKLIST: bool(task.checklist) and not pending_items and not bad_reason,
        RequirementKey.GPS: task.complete_latitude is not None or task.start_latitude is not None,
        RequirementKey.VIDEO: EvidenceType.VIDEO in types_any,
        RequirementKey.MATERIALS: bool(task.materials),
        RequirementKey.INVOICE: bool(types_any & {t.value for t in DOCUMENT_EVIDENCE}),
        RequirementKey.QR_SCAN: task.asset_scanned_at is not None,
    }
    required = [k for k in checks if policy.get(k.value)]
    if RequirementKey.QR_SCAN in required and not task.asset_id:
        required.remove(RequirementKey.QR_SCAN)
    result = {"policy": policy, "requirements": []}
    for key in checks:
        state = "satisfied" if checks[key] else ("excepted" if key.value in excepted else "missing")
        result["requirements"].append({"key": key.value, "required": key in required, "state": state})
    result["missing"] = [r["key"] for r in result["requirements"] if r["required"] and r["state"] == "missing"]
    if not (task.work_notes and task.work_notes.strip()):
        result["missing"].append("work_notes")
    result["pending_checklist"] = [i.label for i in pending_items]
    return result


def complete(db, actor, task, lat=None, lng=None, accuracy=None):
    _require_worker(actor, task)
    if task.status != S.STARTED:
        raise http(409, f"Cannot complete a task that is {task.status}", current_status=task.status)
    if lat is not None and lng is not None:
        task.complete_latitude, task.complete_longitude = lat, lng
        task.gps_accuracy_m = accuracy if accuracy is not None else task.gps_accuracy_m
    proof = proof_status(db, task)
    if proof["missing"]:
        # §10: missing required evidence is never silently treated as complete.
        raise http(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Required proof of work is missing",
            missing=proof["missing"],
            pending_checklist=proof["pending_checklist"],
        )
    _transition(db, actor, task, "complete", {"completed_by": actor.id})
    task.completed_at = utcnow()
    task.completed_by = actor.id
    if not proof["policy"]["supervisor_approval"]:
        _approve(db, None, task, "Auto-approved: supervisor approval not required for this category")
        return
    reviewers = [task.supervisor_id] if task.supervisor_id else notifications.managers(db, task.tenant_id)
    notifications.notify(
        db,
        task.tenant_id,
        reviewers,
        "task_completed",
        f"{task.number} submitted for review",
        task.title,
        "maintenance_task",
        task.id,
    )


def _ensure_reviewer(db, actor, task):
    if not actor.can("maintenance.review"):
        raise http(403, "Only supervisors can review work")
    if actor.role == Role.SUPERVISOR and task.supervisor_id and task.supervisor_id != actor.id:
        raise http(403, "This task is assigned to a different supervisor")
    if task.completed_by == actor.id:
        raise http(403, "You cannot approve your own work")


def _approve(db, actor, task, comment):
    now = utcnow()
    _transition(db, actor, task, "approve", {"comment": comment})
    task.approved_at = task.reviewed_at = now
    task.reviewed_by = actor.id if actor else None
    task.review_decision = "approved"
    task.review_comment = comment
    for exc in db.scalars(
        select(EvidenceException).where(EvidenceException.task_id == task.id, EvidenceException.review_status == "pending")
    ):
        exc.review_status = "accepted"
        exc.reviewed_by = actor.id if actor else None
        exc.reviewed_at = now
        audit.record(db, actor, "maintenance.exception_accepted", "maintenance_task", task.id, new={"requirement": exc.requirement})
    if comment and actor:
        db.add(MaintenanceComment(tenant_id=task.tenant_id, task_id=task.id, author_id=actor.id, body=comment, kind="review"))
    recipients = [task.assigned_staff_id, *notifications.vendor_users(db, task.tenant_id, task.vendor_id)]
    notifications.notify(db, task.tenant_id, recipients, "task_approved", f"{task.number} approved", comment, "maintenance_task", task.id)
    if tenant_setting(db, task.tenant_id, "auto_close_on_approval", True):
        close(db, actor, task)


def approve(db, actor, task, comment: str | None):
    _ensure_reviewer(db, actor, task)
    _approve(db, actor, task, comment)


def reject(db, actor, task, comment: str, decision: str = "rework"):
    _ensure_reviewer(db, actor, task)
    if not comment or not comment.strip():
        raise http(422, "Explain what needs to be fixed")
    _transition(db, actor, task, "reject", {"comment": comment, "decision": decision})
    now = utcnow()
    task.reviewed_at = now
    task.reviewed_by = actor.id
    task.review_decision = decision
    task.review_comment = comment
    task.rework_count += 1
    task.completed_at = None
    for exc in db.scalars(
        select(EvidenceException).where(EvidenceException.task_id == task.id, EvidenceException.review_status == "pending")
    ):
        exc.review_status = "rejected"
        exc.reviewed_by = actor.id
        exc.reviewed_at = now
    db.add(MaintenanceComment(tenant_id=task.tenant_id, task_id=task.id, author_id=actor.id, body=comment, kind="review"))
    recipients = [task.assigned_staff_id, *notifications.vendor_users(db, task.tenant_id, task.vendor_id)]
    notifications.notify(
        db, task.tenant_id, recipients, "task_rework", f"Rework required: {task.number}", comment, "maintenance_task", task.id
    )


def close(db, actor, task):
    _transition(db, actor, task, "close")
    task.closed_at = utcnow()
    _sync_complaint(db, task, ComplaintStatus.RESOLVED)
    if task.asset_id:
        asset = db.get(Asset, task.asset_id)
        if asset and asset.service_interval_days:
            asset.next_service_due = date.today() + timedelta(days=asset.service_interval_days)


def reopen(db, actor, task, reason: str):
    if not actor.can("maintenance.review"):
        raise http(403, "Only supervisors can reopen work")
    if not reason or not reason.strip():
        raise http(422, "A reason is required to reopen a task")
    _transition(db, actor, task, "reopen", {"reason": reason})
    task.rework_count += 1
    task.review_decision = "reopened"
    task.review_comment = reason
    task.closed_at = None
    task.approved_at = None
    task.completed_at = None
    db.add(MaintenanceComment(tenant_id=task.tenant_id, task_id=task.id, author_id=actor.id, body=reason, kind="review"))
    recipients = [task.assigned_staff_id, *notifications.vendor_users(db, task.tenant_id, task.vendor_id)]
    notifications.notify(db, task.tenant_id, recipients, "task_rework", f"Reopened: {task.number}", reason, "maintenance_task", task.id)


def cancel(db, actor, task, reason: str):
    _transition(db, actor, task, "cancel", {"reason": reason})
    task.review_comment = reason


def acknowledge(db, actor, task, note: str | None):
    if task.status not in (S.APPROVED, S.CLOSED):
        raise http(409, "Only completed and approved work can be acknowledged")
    task.resident_ack_at = utcnow()
    task.resident_ack_by = actor.id
    task.resident_ack_note = note
    audit.record(db, actor, "maintenance.resident_acknowledged", "maintenance_task", task.id, new={"note": note})


def _sync_complaint(db: Session, task: MaintenanceTask, target: ComplaintStatus):
    if not task.complaint_id:
        return
    c = db.get(Complaint, task.complaint_id)
    if not c or c.status == ComplaintStatus.CLOSED:
        return
    order = list(ComplaintStatus)
    if order.index(target) <= order.index(ComplaintStatus(c.status)):
        return
    old = c.status
    c.status = target
    if target == ComplaintStatus.RESOLVED:
        c.resolved_at = utcnow()
        c.resolution = task.outcome or task.work_notes or f"Resolved by maintenance {task.number}"
    audit.record(
        db,
        None,
        "complaint.status_synced",
        "complaint",
        c.id,
        old={"status": old},
        new={"status": target, "maintenance": task.number},
        tenant_id=c.tenant_id,
    )
    notifications.notify(
        db,
        c.tenant_id,
        [c.raised_by],
        "complaint_update",
        f"{c.number} is now {target.replace('_', ' ')}",
        task.title,
        "complaint",
        c.id,
    )


def is_overdue(task: MaintenanceTask, now: datetime | None = None) -> bool:
    now = now or utcnow()
    return bool(task.due_at and task.due_at < now and task.status in OPEN_STATES)
