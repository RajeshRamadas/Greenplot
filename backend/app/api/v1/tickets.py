"""Customer ticketing & vendor service management API (ticketing requirements §24)."""

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_, select

from app.api.v1._util import Limit, Offset, paginate, property_labels, user_names, vendor_names
from app.core.deps import DB, Actor, CurrentActor, Perm
from app.models import (
    AuditLog,
    MaintenanceTask,
    Media,
    Notification,
    NotificationDelivery,
    Ticket,
    TicketAssignment,
    TicketCategory,
    TicketComment,
    TicketEvidence,
    TicketSLA,
    TicketStatusHistory,
    User,
    Vendor,
)
from app.models.base import utcnow
from app.models.enums import ChecklistStatus, Role, TaskCategory, TaskStatus
from app.schemas.common import GeoPoint, Page
from app.schemas.operations import AuditOut
from app.schemas.tickets import (
    AssignmentOut,
    AttachmentOut,
    CategoryIn,
    CategoryOut,
    DeliveryOut,
    FeedbackIn,
    ResolutionIn,
    SlaOut,
    StatusHistoryOut,
    TicketAssignIn,
    TicketCloseIn,
    TicketCommentIn,
    TicketCommentOut,
    TicketCompleteIn,
    TicketDetail,
    TicketEvidenceIn,
    TicketIn,
    TicketRejectIn,
    TicketStatusIn,
    TicketSummary,
    TicketUpdate,
    TicketVerifyIn,
    TimelineItem,
    WorkOrderOut,
)
from app.services import audit
from app.services import maintenance as msvc
from app.services import tickets as svc
from app.services.access import get_scoped, get_ticket, is_ticket_assignee, scope_tickets, tenant_select
from app.services.storage import get_storage

router = APIRouter(prefix="/tickets", tags=["tickets"])
S = svc.S

STATUS_TITLES = {
    "open": "Ticket created",
    "under_review": "Under review by the layout office",
    "assigned": "Assigned",
    "accepted": "Accepted by the assignee",
    "in_progress": "Work in progress",
    "waiting_for_customer": "Waiting for your reply",
    "work_completed": "Work completed",
    "verification": "Awaiting supervisor verification",
    "resolved": "Resolved",
    "closed": "Closed",
    "rejected": "Not accepted",
    "cancelled": "Cancelled",
    "on_hold": "On hold",
    "reopened": "Reopened",
}
# Status reasons a customer may read; others can carry internal detail (e.g. why a vendor declined).
CUSTOMER_REASONS = {"rejected", "on_hold", "waiting_for_customer", "reopened", "cancelled", "resolved", "closed"}


# ------------------------------------------------------------------ presenters


def summaries(db, actor: Actor, tickets: list[Ticket]) -> list[TicketSummary]:
    if not tickets:
        return []
    cats = {c.id: c for c in db.scalars(select(TicketCategory).where(TicketCategory.id.in_({t.category_id for t in tickets})))}
    props = property_labels(db, (t.property_id for t in tickets))
    customers = user_names(db, (t.customer_id for t in tickets))
    staff = user_names(db, (t.assigned_to_id for t in tickets if t.assigned_to_type == "staff"))
    vendors = vendor_names(db, (t.assigned_to_id for t in tickets if t.assigned_to_type == "vendor"))
    slas = {s.ticket_id: s for s in db.scalars(select(TicketSLA).where(TicketSLA.ticket_id.in_([t.id for t in tickets])))}
    now = utcnow()
    out = []
    for t in tickets:
        s = TicketSummary.model_validate(t)
        cat = cats.get(t.category_id)
        s.category_code, s.category_name = (cat.code, cat.name) if cat else (None, None)
        s.property_label = props.get(t.property_id)
        s.customer_name = customers.get(t.customer_id)
        s.assignee_name = (vendors if t.assigned_to_type == "vendor" else staff).get(t.assigned_to_id) if t.assigned_to_id else None
        s.sla_state = svc.sla_state(t, slas.get(t.id), db, now)
        out.append(s)
    return out


def _evidence_visible(db, actor: Actor, task: MaintenanceTask) -> bool:
    if actor.role != Role.RESIDENT:
        return True
    mode = msvc.tenant_setting(db, task.tenant_id, "resident_evidence_visibility", "after_approval")
    if mode == "none":
        return False
    return mode == "all" or task.status in (TaskStatus.APPROVED, TaskStatus.CLOSED)


def _work_order(db, task: MaintenanceTask, include_proof: bool) -> WorkOrderOut:
    names = user_names(db, [task.assigned_staff_id])
    vnames = vendor_names(db, [task.vendor_id])
    w = WorkOrderOut(
        id=task.id,
        number=task.number,
        status=task.status,
        category=task.category,
        assignee_name=vnames.get(task.vendor_id) or names.get(task.assigned_staff_id),
        rework_count=task.rework_count,
        due_at=task.due_at,
        completed_at=task.completed_at,
        approved_at=task.approved_at,
        checklist_total=len(task.checklist),
        checklist_done=sum(1 for i in task.checklist if i.status != ChecklistStatus.PENDING),
        materials_count=len(task.materials),
        evidence_count=len(msvc.current_evidence(db, task)),
    )
    if include_proof and task.status in (TaskStatus.ACCEPTED, TaskStatus.STARTED, TaskStatus.REWORK_REQUIRED):
        proof = msvc.proof_status(db, task)
        w.missing, w.pending_checklist = proof["missing"], proof["pending_checklist"]
    return w


def _attachments(db, actor: Actor, t: Ticket) -> list[AttachmentOut]:
    storage = get_storage()
    out: list[AttachmentOut] = []
    rows = list(db.scalars(select(TicketEvidence).where(TicketEvidence.ticket_id == t.id).order_by(TicketEvidence.created_at)))
    media = {m.id: m for m in db.scalars(select(Media).where(Media.id.in_([r.media_id for r in rows])))} if rows else {}
    work = []
    for task in db.scalars(select(MaintenanceTask).where(MaintenanceTask.ticket_id == t.id, MaintenanceTask.deleted_at.is_(None))):
        if _evidence_visible(db, actor, task):
            work += msvc.current_evidence(db, task)
    names = user_names(db, [r.uploaded_by for r in rows] + [e.uploaded_by for e in work])

    def present(id_, m: Media | None, source, etype, caption, by, at) -> AttachmentOut | None:
        if m is None or m.status != "ready":
            return None
        return AttachmentOut(
            id=id_,
            media_id=m.id,
            source=source,
            evidence_type=etype,
            caption=caption,
            uploaded_by_name=names.get(by),
            uploaded_at=at or m.uploaded_at,
            content_type=m.content_type,
            filename=m.original_filename,
            sha256=m.sha256,
            url=storage.download_url(m.storage_key, m.original_filename),
            thumbnail_url=storage.download_url(m.thumbnail_key) if m.thumbnail_key else None,
        )

    for r in rows:
        a = present(r.id, media.get(r.media_id), "ticket", r.evidence_type, r.caption, r.uploaded_by, r.created_at)
        if a:
            out.append(a)
    for e in work:
        a = present(e.id, e.media, "work", e.evidence_type, e.caption, e.uploaded_by, e.uploaded_at)
        if a:
            out.append(a)
    return out


def _comments(db, actor: Actor, t: Ticket) -> list[TicketCommentOut]:
    rows = list(
        db.scalars(
            select(TicketComment)
            .where(TicketComment.ticket_id == t.id, TicketComment.visibility.in_(svc.visible_to(db, actor, t)))
            .order_by(TicketComment.created_at)
        )
    )
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({r.author_id for r in rows if r.author_id})))} if rows else {}
    out = []
    for r in rows:
        u = users.get(r.author_id)
        out.append(
            TicketCommentOut.model_validate(r).model_copy(
                update={"author_name": u.full_name if u else "GreenPlot", "author_role": u.role if u else "system"}
            )
        )
    return out


def _timeline(db, actor: Actor, t: Ticket, comments: list[TicketCommentOut], attachments: list[AttachmentOut]) -> list[TimelineItem]:
    customer_view = actor.role == Role.RESIDENT
    items: list[TimelineItem] = []
    history = list(db.scalars(select(TicketStatusHistory).where(TicketStatusHistory.ticket_id == t.id)))
    assignments = list(db.scalars(select(TicketAssignment).where(TicketAssignment.ticket_id == t.id)))
    names = user_names(db, [h.changed_by for h in history] + [a.assigned_by for a in assignments])
    for h in history:
        if h.new_status == "assigned":
            continue  # the assignment entry below names who it went to
        reason = h.reason if (not customer_view or h.new_status in CUSTOMER_REASONS) else None
        items.append(
            TimelineItem(
                at=h.created_at,
                kind="status",
                title=STATUS_TITLES.get(h.new_status, h.new_status),
                detail=reason,
                actor_name=names.get(h.changed_by) if h.changed_by else "GreenPlot",
                status=h.new_status,
            )
        )
    staff = user_names(db, [a.assignee_id for a in assignments if a.assignee_type == "staff"])
    vendors = vendor_names(db, [a.assignee_id for a in assignments if a.assignee_type == "vendor"])
    for a in assignments:
        who = (vendors if a.assignee_type == "vendor" else staff).get(a.assignee_id, a.assignee_type)
        items.append(
            TimelineItem(
                at=a.assigned_at, kind="assignment", title=f"Assigned to {who}", actor_name=names.get(a.assigned_by), status="assigned"
            )
        )
        if a.rejected_at and not customer_view:
            items.append(TimelineItem(at=a.rejected_at, kind="assignment", title=f"{who} declined", detail=a.rejection_reason))
    for c in comments:
        if c.comment_type != "system":
            items.append(
                TimelineItem(
                    at=c.created_at,
                    kind="comment",
                    title="Question" if c.comment_type == "question" else "Comment",
                    detail=c.message,
                    actor_name=c.author_name,
                    status=c.visibility,
                )
            )
    for a in attachments:
        items.append(
            TimelineItem(
                at=a.uploaded_at or t.created_at,
                kind="evidence",
                title=("Proof of work: " if a.source == "work" else "Attachment: ") + a.evidence_type.replace("_", " "),
                detail=a.caption,
                actor_name=a.uploaded_by_name,
            )
        )
    if actor.is_manager() or customer_view:
        for n in db.scalars(
            select(Notification).where(
                Notification.entity_type == "ticket", Notification.entity_id == t.id, Notification.user_id == t.customer_id
            )
        ):
            items.append(
                TimelineItem(
                    at=n.created_at,
                    kind="notification",
                    title="Customer notified" if not customer_view else "You were notified",
                    detail=f"{n.title} · via {', '.join(ch.replace('_', '-') for ch in n.channels)}",
                )
            )
    if t.feedback_at:
        stars = f"{t.rating}/5" if t.rating else "no rating"
        items.append(TimelineItem(at=t.feedback_at, kind="feedback", title=f"Customer feedback ({stars})", detail=t.feedback))
    items.sort(key=lambda i: i.at)
    return items


def allowed_actions(db, actor: Actor, t: Ticket, task: MaintenanceTask | None) -> list[str]:
    acts: list[str] = []
    st = S(t.status)
    manager = actor.can("tickets.manage")
    assignee = is_ticket_assignee(actor, t)
    customer = svc.is_customer(db, actor, t)
    live_task = task if task and task.status not in svc.TASK_DONE else None
    if manager:
        acts.append("edit")
        if st in (S.OPEN, S.REOPENED):
            acts.append("review")
        if st in svc.ASSIGNABLE and not (live_task and live_task.status == TaskStatus.COMPLETED):
            acts.append("reassign" if t.assigned_to_id else "assign")
        if (
            st in svc.ACTIVE
            and st not in (S.WORK_COMPLETED, S.VERIFICATION)
            and (live_task is None or live_task.status == TaskStatus.CREATED)
        ):
            acts.append("resolve")
        if st == S.RESOLVED:
            acts.append("close")
        if st in svc.PAUSABLE:
            acts += ["hold", "wait"]
        if st in svc.UNASSIGNED_STATES:
            acts.append("reject")
        if st in svc.ACTIVE and st not in (S.WORK_COMPLETED, S.VERIFICATION):
            acts.append("cancel")
        acts.append("internal_note")
    if actor.can("tickets.verify") and st in (S.VERIFICATION, S.WORK_COMPLETED) and task and task.status == TaskStatus.COMPLETED:
        if task.completed_by != actor.id:
            acts.append("verify")
    if assignee and live_task:
        ts = live_task.status
        if ts == TaskStatus.ASSIGNED:
            acts.append("accept")
        if ts in (TaskStatus.ASSIGNED, TaskStatus.ACCEPTED):
            acts.append("reject_assignment")
        if ts in (TaskStatus.ASSIGNED, TaskStatus.ACCEPTED, TaskStatus.REWORK_REQUIRED):
            acts.append("start")
        if ts in msvc.EVIDENCE_STATES:
            acts.append("upload_evidence")
        if ts == TaskStatus.STARTED:
            acts += ["work", "complete"]
        if st in svc.PAUSABLE and "wait" not in acts:
            acts.append("wait")
        if st in (S.ON_HOLD, S.WAITING_FOR_CUSTOMER):
            acts.append("resume")
    if manager and st in (S.ON_HOLD, S.WAITING_FOR_CUSTOMER):
        acts.append("resume")
    if customer:
        if st in (S.OPEN, S.UNDER_REVIEW):
            acts.append("edit")
        if st in (S.OPEN, S.UNDER_REVIEW, S.REOPENED):
            acts.append("cancel")
        if st == S.RESOLVED:
            acts += ["confirm", "feedback"]
        if st == S.CLOSED and t.feedback_at is None:
            acts.append("feedback")
        if st == S.RESOLVED or (st in (S.CLOSED, S.REJECTED) and _reopen_until(db, t) and utcnow() <= _reopen_until(db, t)):
            acts.append("reopen")
    elif manager and st in svc.REOPENABLE:
        acts.append("reopen")
    if st not in (S.CLOSED, S.CANCELLED) and (customer or manager or assignee):
        acts += ["comment", "attach"]
    return list(dict.fromkeys(acts))


def _reopen_until(db, t: Ticket) -> datetime | None:
    if t.status not in (S.CLOSED, S.REJECTED):
        return None
    since = t.closed_at or t.updated_at
    return since + timedelta(days=svc.setting(db, t.tenant_id, "ticket_reopen_days")) if since else None


def detail(db, actor: Actor, t: Ticket) -> TicketDetail:
    d = TicketDetail.model_validate(t)
    base = summaries(db, actor, [t])[0]
    for f in ("category_code", "category_name", "property_label", "customer_name", "assignee_name", "sla_state"):
        setattr(d, f, getattr(base, f))
    sla = svc.get_sla(db, t)
    if sla:
        d.sla = SlaOut.model_validate(sla, from_attributes=True).model_copy(update={"state": base.sla_state})
    manager = actor.is_manager()
    assignee = is_ticket_assignee(actor, t)
    # Contact details only where required and permitted (§22).
    customer = db.get(User, t.customer_id)
    if manager or (assignee and svc.setting(db, t.tenant_id, "ticket_share_customer_contact")) or actor.id == t.customer_id:
        d.customer_phone = t.contact_phone or (customer.phone if customer else None)
    else:
        d.contact_phone = None
    if manager or assignee or svc.setting(db, t.tenant_id, "ticket_share_vendor_contact"):
        if t.assigned_to_type == "vendor" and t.assigned_to_id:
            v = db.get(Vendor, t.assigned_to_id)
            d.assignee_phone = v.phone if v else None
        elif t.assigned_to_type == "staff" and t.assigned_to_id:
            u = db.get(User, t.assigned_to_id)
            d.assignee_phone = u.phone if u else None
    task = svc.current_task(db, t)
    if task:
        d.work_order = _work_order(db, task, include_proof=manager or assignee)
    if manager:
        d.work_orders = [
            _work_order(db, x, False)
            for x in db.scalars(select(MaintenanceTask).where(MaintenanceTask.ticket_id == t.id).order_by(MaintenanceTask.created_at))
        ]
    if actor.role == Role.RESIDENT:
        d.maintenance_task_id = task.id if task and task.status in (TaskStatus.APPROVED, TaskStatus.CLOSED) else None
    d.comments = _comments(db, actor, t)
    d.attachments = _attachments(db, actor, t)
    d.timeline = _timeline(db, actor, t, d.comments, d.attachments)
    d.allowed_actions = allowed_actions(db, actor, t, task)
    if manager:
        d.comment_visibilities = ["customer", "vendor", "internal"]
    elif assignee:
        d.comment_visibilities = (["customer"] if svc.setting(db, t.tenant_id, "ticket_assignee_customer_chat") else []) + ["vendor"]
    else:
        d.comment_visibilities = ["customer"]
    d.reopen_until = _reopen_until(db, t)
    return d


def _commit(db, actor, t) -> TicketDetail:
    db.commit()
    db.refresh(t)
    return detail(db, actor, t)


# ------------------------------------------------------------------ configuration (declared before /{id})


def _category_out(db, c: TicketCategory) -> CategoryOut:
    o = CategoryOut.model_validate(c)
    o.effective_response_minutes, o.effective_resolution_minutes = svc.sla_minutes(db, c.tenant_id, c, c.default_priority)
    return o


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: DB, actor: Perm("tickets.read"), include_inactive: bool = False):
    svc.ensure_categories(db, actor.tenant_id)
    db.commit()
    stmt = tenant_select(TicketCategory, actor).order_by(TicketCategory.position, TicketCategory.name)
    if not include_inactive:
        stmt = stmt.where(TicketCategory.is_active.is_(True))
    return [_category_out(db, c) for c in db.scalars(stmt)]


def _check_task_category(value: str | None):
    if value is not None and value not in {c.value for c in TaskCategory}:
        raise HTTPException(422, f"task_category must be one of: {', '.join(c.value for c in TaskCategory)}")


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, db: DB, actor: Perm("tickets.configure")):
    if not body.code or not body.name:
        raise HTTPException(422, "code and name are required")
    _check_task_category(body.task_category)
    svc.ensure_categories(db, actor.tenant_id)
    if db.scalar(tenant_select(TicketCategory, actor).where(TicketCategory.code == body.code)):
        raise HTTPException(409, "A category with this code exists")
    c = TicketCategory(tenant_id=actor.tenant_id, **body.model_dump(exclude_none=True))
    db.add(c)
    db.flush()
    audit.record(db, actor, "config.ticket_category_created", "ticket_category", c.id, new=body.model_dump(exclude_none=True))
    db.commit()
    return _category_out(db, c)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: uuid.UUID, body: CategoryIn, db: DB, actor: Perm("tickets.configure")):
    c = get_scoped(db, TicketCategory, category_id, actor, "Category")
    _check_task_category(body.task_category)
    data = body.model_dump(exclude_unset=True)
    data.pop("code", None)  # codes are stable identifiers
    before = audit.snapshot(c)
    for k, v in data.items():
        setattr(c, k, v)
    old, new = audit.diff(before, audit.snapshot(c))
    audit.record(db, actor, "config.ticket_category_changed", "ticket_category", c.id, old=old, new=new)
    db.commit()
    return _category_out(db, c)


@router.get("/config")
def ticket_config(db: DB, actor: Perm("tickets.read")):
    """Effective ticket policy for this layout: SLA table and customer rules."""
    sla = {}
    configured = svc.setting_raw(db, actor.tenant_id, "ticket_sla") or {}
    for p, (resp, resol) in svc.DEFAULT_SLA.items():
        c = configured.get(p.value) or {}
        sla[p.value] = {
            "response_minutes": int(c.get("response_minutes", resp)),
            "resolution_minutes": int(c.get("resolution_minutes", resol)),
        }
    return {"sla": sla, **{k: svc.setting(db, actor.tenant_id, k) for k in svc.SETTINGS_DEFAULTS}}


# ------------------------------------------------------------------ dashboards & reports (§25-27, §34-35)


def _active_with_sla(db, actor: Actor):
    stmt = scope_tickets(tenant_select(Ticket, actor), db, actor).where(Ticket.status.in_([s.value for s in svc.ACTIVE]))
    tickets = list(db.scalars(stmt))
    slas = (
        {s.ticket_id: s for s in db.scalars(select(TicketSLA).where(TicketSLA.ticket_id.in_([t.id for t in tickets])))} if tickets else {}
    )
    now = utcnow()
    return [(t, svc.sla_state(t, slas.get(t.id), db, now)) for t in tickets]


def _sla_ids(db, actor: Actor, state: str) -> list[uuid.UUID]:
    return [t.id for t, s in _active_with_sla(db, actor) if s == state]


@router.get("/dashboard")
def dashboard(db: DB, actor: Perm("tickets.read")):
    """Role-aware counts: KPI cards for the office, work sections for assignees, status tabs for customers."""
    stmt = scope_tickets(tenant_select(Ticket, actor), db, actor)
    rows = list(db.execute(stmt.with_only_columns(Ticket.status, Ticket.resolved_at, Ticket.closed_at, Ticket.assigned_to_id)).all())
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1

    def bucket(name):
        return sum(by_status.get(s.value, 0) for s in svc.BUCKETS[name])

    sla_states = [s for _, s in _active_with_sla(db, actor)]
    ist = timedelta(hours=5, minutes=30)
    today = (utcnow() + ist).replace(hour=0, minute=0, second=0, microsecond=0) - ist  # start of today in IST
    out = {
        "by_status": by_status,
        "kpis": {
            "open": bucket("active"),
            "in_progress": bucket("in_progress"),
            "sla_at_risk": sla_states.count("at_risk"),
            "resolved_today": sum(1 for r in rows if r.resolved_at and r.resolved_at >= today),
            "closed_today": sum(1 for r in rows if r.closed_at and r.closed_at >= today),
            "sla_breached": sla_states.count("breached"),
        },
    }
    if actor.is_manager():
        out["buckets"] = {
            "new": bucket("new"),
            "unassigned": sum(1 for r in rows if r.status in svc.UNASSIGNED_STATES and not r.assigned_to_id),
            "assigned": bucket("assigned"),
            "in_progress": by_status.get("in_progress", 0) + by_status.get("work_completed", 0),
            "sla_at_risk": sla_states.count("at_risk"),
            "sla_breached": sla_states.count("breached"),
            "awaiting_verification": bucket("awaiting_verification"),
            "resolved": bucket("resolved"),
            "reopened": bucket("reopened"),
        }
    elif actor.can("tickets.work"):
        assignee_type, assignee_id = ("vendor", actor.user.vendor_id) if actor.role == Role.VENDOR else ("staff", actor.id)
        rejected = list(
            db.scalars(
                select(TicketAssignment)
                .where(
                    TicketAssignment.tenant_id == actor.tenant_id,
                    TicketAssignment.assignee_type == assignee_type,
                    TicketAssignment.assignee_id == assignee_id,
                    TicketAssignment.rejected_at.is_not(None),
                )
                .order_by(TicketAssignment.rejected_at.desc())
                .limit(20)
            )
        )
        tickets = {t.id: t for t in db.scalars(select(Ticket).where(Ticket.id.in_([r.ticket_id for r in rejected])))} if rejected else {}
        out["sections"] = {
            "new_assignments": bucket("new_assignments"),
            "accepted": bucket("accepted"),
            "in_progress": by_status.get("in_progress", 0),
            "awaiting_verification": bucket("awaiting_verification"),
            "completed": bucket("completed"),
            "rejected": len(rejected),
        }
        out["rejected"] = [
            {
                "ticket_id": r.ticket_id,
                "number": tickets[r.ticket_id].number if r.ticket_id in tickets else None,
                "title": tickets[r.ticket_id].title if r.ticket_id in tickets else None,
                "rejected_at": r.rejected_at,
                "reason": r.rejection_reason,
            }
            for r in rejected
        ]
    else:
        out["tabs"] = {k: bucket(k) for k in ("open", "in_progress", "resolved", "closed", "reopened")}
    return out


def _hours(a: datetime | None, b: datetime | None) -> float | None:
    return (b - a).total_seconds() / 3600 if a and b else None


def _avg(values: list[float | None]) -> float | None:
    v = [x for x in values if x is not None]
    return round(sum(v) / len(v), 2) if v else None


@router.get("/reports")
def reports(db: DB, actor: Perm("reports.read"), date_from: datetime | None = None, date_to: datetime | None = None):
    """Volume, SLA, vendor, category and customer reports (§29, §34)."""
    stmt = tenant_select(Ticket, actor)
    if date_from:
        stmt = stmt.where(Ticket.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Ticket.created_at <= date_to)
    tickets = list(db.scalars(stmt))
    ids = [t.id for t in tickets]
    slas = {s.ticket_id: s for s in db.scalars(select(TicketSLA).where(TicketSLA.ticket_id.in_(ids)))} if ids else {}
    assigns = list(db.scalars(select(TicketAssignment).where(TicketAssignment.ticket_id.in_(ids)))) if ids else []
    tasks = {x.id: x for x in db.scalars(select(MaintenanceTask).where(MaintenanceTask.ticket_id.in_(ids)))} if ids else {}
    now = utcnow()
    states = {t.id: svc.sla_state(t, slas.get(t.id), db, now) for t in tickets}
    finished = [t for t in tickets if t.status in (S.RESOLVED, S.CLOSED)]

    volume = {
        "created": len(tickets),
        "closed": sum(1 for t in tickets if t.status == S.CLOSED),
        "open": sum(1 for t in tickets if t.status in svc.ACTIVE),
        "overdue": sum(1 for t in tickets if t.status in svc.ACTIVE and states[t.id] == "breached"),
        "cancelled_or_rejected": sum(1 for t in tickets if t.status in (S.CANCELLED, S.REJECTED)),
    }
    sla = {
        "met": sum(1 for t in finished if states[t.id] == "met"),
        "breached": sum(1 for t in tickets if states[t.id] == "breached"),
        "avg_response_hours": _avg([_hours(t.created_at, t.first_response_at) for t in tickets]),
        "avg_resolution_hours": _avg([_hours(t.created_at, t.resolved_at) for t in finished]),
    }

    vnames = vendor_names(db, (a.assignee_id for a in assigns if a.assignee_type == "vendor"))
    snames = user_names(db, (a.assignee_id for a in assigns if a.assignee_type == "staff"))
    by_assignee: dict[tuple[str, uuid.UUID], dict] = {}
    tmap = {t.id: t for t in tickets}
    for a in assigns:
        key = (a.assignee_type, a.assignee_id)
        row = by_assignee.setdefault(
            key,
            {
                "assignee_type": a.assignee_type,
                "assignee_id": a.assignee_id,
                "name": (vnames if a.assignee_type == "vendor" else snames).get(a.assignee_id),
                "assigned": 0,
                "accepted": 0,
                "rejected": 0,
                "completed": 0,
                "reopened": 0,
                "rework": 0,
                "sla_breaches": 0,
                "_response": [],
                "_resolution": [],
                "_ratings": [],
            },
        )
        row["assigned"] += 1
        row["accepted"] += bool(a.accepted_at)
        row["rejected"] += bool(a.rejected_at)
        row["_response"].append(_hours(a.assigned_at, a.accepted_at))
        task = tasks.get(a.maintenance_task_id)
        t = tmap.get(a.ticket_id)
        if task:
            row["rework"] += task.rework_count
            if task.status in (TaskStatus.APPROVED, TaskStatus.CLOSED):
                row["completed"] += 1
                row["_resolution"].append(_hours(a.assigned_at, task.approved_at))
        if t and t.assigned_to_id == a.assignee_id and a.unassigned_at is None and a.rejected_at is None:
            row["reopened"] += t.reopen_count
            row["sla_breaches"] += states.get(t.id) == "breached"
            if t.rating:
                row["_ratings"].append(t.rating)
    vendor_rows = []
    for row in by_assignee.values():
        row["avg_accept_hours"] = _avg(row.pop("_response"))
        row["avg_completion_hours"] = _avg(row.pop("_resolution"))
        ratings = row.pop("_ratings")
        row["avg_rating"] = _avg(ratings)
        row["rework_rate"] = round(row["rework"] / row["assigned"], 3) if row["assigned"] else None
        vendor_rows.append(row)
    vendor_rows.sort(key=lambda r: -r["assigned"])

    cats = {c.id: c for c in db.scalars(tenant_select(TicketCategory, actor))}
    by_cat: dict[uuid.UUID, dict] = {}
    for t in tickets:
        r = by_cat.setdefault(
            t.category_id, {"category": cats[t.category_id].name if t.category_id in cats else "?", "count": 0, "_res": []}
        )
        r["count"] += 1
        r["_res"].append(_hours(t.created_at, t.resolved_at))
    category_rows = sorted(
        ({"category": r["category"], "count": r["count"], "avg_resolution_hours": _avg(r["_res"])} for r in by_cat.values()),
        key=lambda r: -r["count"],
    )

    props = property_labels(db, (t.property_id for t in tickets))
    by_prop: dict[uuid.UUID, dict] = {}
    for t in tickets:
        if not t.property_id:
            continue
        r = by_prop.setdefault(t.property_id, {"property": props.get(t.property_id), "count": 0, "_cats": {}})
        r["count"] += 1
        r["_cats"][t.category_id] = r["_cats"].get(t.category_id, 0) + 1
    property_rows = sorted(
        (
            {
                "property_id": pid,
                "property": r["property"],
                "count": r["count"],
                "repeat_complaints": sum(n - 1 for n in r["_cats"].values() if n > 1),
            }
            for pid, r in by_prop.items()
        ),
        key=lambda r: -r["count"],
    )
    ratings = [t.rating for t in tickets if t.rating]
    return {
        "generated_at": now,
        "volume": volume,
        "sla": sla,
        "vendors": vendor_rows,
        "categories": category_rows,
        "properties": property_rows[:50],
        "satisfaction": {
            "avg_rating": _avg(ratings),
            "ratings": len(ratings),
            "confirmed_resolved": sum(1 for t in tickets if t.customer_confirmation == "resolved"),
            "reopened": sum(1 for t in tickets if t.reopen_count),
        },
    }


# ------------------------------------------------------------------ CRUD


@router.post("", response_model=TicketDetail, status_code=201)
def create_ticket(body: TicketIn, db: DB, actor: Perm("tickets.create")):
    t = svc.create(db, actor, body.model_dump())
    return _commit(db, actor, t)


@router.get("", response_model=Page[TicketSummary])
def list_tickets(
    db: DB,
    actor: Perm("tickets.read"),
    status: list[str] | None = Query(None),
    bucket: str | None = Query(None, pattern=f"^({'|'.join([*svc.BUCKETS, 'sla_at_risk', 'sla_breached'])})$"),
    category: str | None = None,
    priority: str | None = None,
    property_id: uuid.UUID | None = None,
    vendor_id: uuid.UUID | None = None,
    staff_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    q: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = Query("-created_at", pattern="^-?(created_at|updated_at|due_at|priority|number)$"),
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = scope_tickets(tenant_select(Ticket, actor), db, actor)
    if status:
        stmt = stmt.where(Ticket.status.in_(status))
    if bucket in ("sla_at_risk", "sla_breached"):
        stmt = stmt.where(Ticket.id.in_(_sla_ids(db, actor, bucket.removeprefix("sla_")) or [uuid.uuid4()]))
    elif bucket == "unassigned":
        stmt = stmt.where(Ticket.status.in_([s.value for s in svc.UNASSIGNED_STATES]), Ticket.assigned_to_id.is_(None))
    elif bucket:
        stmt = stmt.where(Ticket.status.in_([s.value for s in svc.BUCKETS[bucket]]))
    if category:
        cat = svc.get_category(db, actor.tenant_id, category)
        stmt = stmt.where(Ticket.category_id == cat.id)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if property_id:
        stmt = stmt.where(Ticket.property_id == property_id)
    if vendor_id:
        stmt = stmt.where(Ticket.assigned_to_type == "vendor", Ticket.assigned_to_id == vendor_id)
    if staff_id:
        stmt = stmt.where(Ticket.assigned_to_type == "staff", Ticket.assigned_to_id == staff_id)
    if customer_id:
        stmt = stmt.where(Ticket.customer_id == customer_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Ticket.number.ilike(like), Ticket.title.ilike(like), Ticket.description.ilike(like)))
    if date_from:
        stmt = stmt.where(Ticket.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Ticket.created_at <= date_to)
    key = sort.lstrip("-")
    if key == "priority":
        from sqlalchemy import case

        col = case({p: i for i, p in enumerate(svc.PRIORITY_ORDER)}, value=Ticket.priority)
    else:
        col = getattr(Ticket, key)
    stmt = stmt.order_by(col.desc() if sort.startswith("-") else col.asc(), Ticket.number.desc())
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=summaries(db, actor, items), total=total, limit=limit, offset=offset)


@router.get("/{ticket_id}", response_model=TicketDetail)
def get_ticket_detail(ticket_id: uuid.UUID, db: DB, actor: Perm("tickets.read")):
    return detail(db, actor, get_ticket(db, actor, ticket_id))


@router.patch("/{ticket_id}", response_model=TicketDetail)
def update_ticket(ticket_id: uuid.UUID, body: TicketUpdate, db: DB, actor: Perm("tickets.read")):
    t = get_ticket(db, actor, ticket_id)
    svc.update(db, actor, t, body.model_dump(exclude_unset=True))
    return _commit(db, actor, t)


# ------------------------------------------------------------------ lifecycle


@router.post("/{ticket_id}/review", response_model=TicketDetail)
def review(ticket_id: uuid.UUID, db: DB, actor: Perm("tickets.manage")):
    t = get_ticket(db, actor, ticket_id)
    svc.review(db, actor, t)
    return _commit(db, actor, t)


@router.post("/{ticket_id}/assign", response_model=TicketDetail)
def assign(ticket_id: uuid.UUID, body: TicketAssignIn, db: DB, actor: Perm("tickets.manage")):
    t = get_ticket(db, actor, ticket_id)
    svc.assign(db, actor, t, body.staff_id, body.vendor_id, body.due_at, body.notes, body.reason)
    return _commit(db, actor, t)


def _assignee_response(db, actor, t) -> TicketDetail:
    db.commit()
    db.refresh(t)
    if not (actor.is_manager() or is_ticket_assignee(actor, t)):
        # After declining, the assignee no longer has access to the ticket.
        return TicketDetail.model_validate(t).model_copy(update={"description": "", "contact_phone": None})
    return detail(db, actor, t)


@router.post("/{ticket_id}/accept", response_model=TicketDetail)
def accept(ticket_id: uuid.UUID, db: DB, actor: Perm("tickets.work")):
    t = get_ticket(db, actor, ticket_id)
    svc.accept(db, actor, t)
    return _commit(db, actor, t)


@router.post("/{ticket_id}/reject", response_model=TicketDetail)
def reject(ticket_id: uuid.UUID, body: TicketRejectIn, db: DB, actor: Perm("tickets.work")):
    """Assignee declines the assignment; the ticket returns to the office for reassignment (§10)."""
    t = get_ticket(db, actor, ticket_id)
    svc.reject(db, actor, t, body.reason_code, body.reason)
    return _assignee_response(db, actor, t)


@router.post("/{ticket_id}/start", response_model=TicketDetail)
def start(ticket_id: uuid.UUID, db: DB, actor: Perm("tickets.work"), body: GeoPoint | None = None):
    t = get_ticket(db, actor, ticket_id)
    body = body or GeoPoint()
    svc.start(db, actor, t, body.latitude, body.longitude, body.accuracy_m)
    return _commit(db, actor, t)


@router.post("/{ticket_id}/complete", response_model=TicketDetail)
def complete(ticket_id: uuid.UUID, body: TicketCompleteIn, db: DB, actor: Perm("tickets.work")):
    t = get_ticket(db, actor, ticket_id)
    svc.complete(db, actor, t, body.work_notes, body.outcome, body.latitude, body.longitude, body.accuracy_m)
    return _commit(db, actor, t)


@router.post("/{ticket_id}/verify", response_model=TicketDetail)
def verify(ticket_id: uuid.UUID, body: TicketVerifyIn, db: DB, actor: Perm("tickets.verify")):
    t = get_ticket(db, actor, ticket_id)
    svc.verify(db, actor, t, body.decision, body.comment)
    return _commit(db, actor, t)


@router.post("/{ticket_id}/resolve", response_model=TicketDetail)
def resolve(ticket_id: uuid.UUID, body: ResolutionIn, db: DB, actor: Perm("tickets.manage")):
    t = get_ticket(db, actor, ticket_id)
    svc.resolve(db, actor, t, body.resolution)
    return _commit(db, actor, t)


@router.post("/{ticket_id}/close", response_model=TicketDetail)
def close(ticket_id: uuid.UUID, body: TicketCloseIn, db: DB, actor: Perm("tickets.read")):
    t = get_ticket(db, actor, ticket_id)
    if actor.can("tickets.manage"):
        svc.close(db, actor, t, body.note)
    elif svc.is_customer(db, actor, t):
        svc.feedback(db, actor, t, "resolved", None, body.note)
    else:
        raise HTTPException(403, "You cannot close this ticket")
    return _commit(db, actor, t)


@router.post("/{ticket_id}/reopen", response_model=TicketDetail)
def reopen(ticket_id: uuid.UUID, body: ResolutionIn, db: DB, actor: Perm("tickets.read")):
    t = get_ticket(db, actor, ticket_id)
    svc.reopen(db, actor, t, body.resolution)
    return _commit(db, actor, t)


@router.post("/{ticket_id}/feedback", response_model=TicketDetail)
def feedback(ticket_id: uuid.UUID, body: FeedbackIn, db: DB, actor: Perm("tickets.read")):
    t = get_ticket(db, actor, ticket_id)
    svc.feedback(db, actor, t, body.outcome, body.rating, body.comment)
    return _commit(db, actor, t)


@router.post("/{ticket_id}/status", response_model=TicketDetail)
def change_status(ticket_id: uuid.UUID, body: TicketStatusIn, db: DB, actor: Perm("tickets.read")):
    t = get_ticket(db, actor, ticket_id)
    svc.change_status(db, actor, t, body.action, body.reason)
    return _commit(db, actor, t)


@router.post("/{ticket_id}/comments", response_model=TicketCommentOut, status_code=201)
def comment(ticket_id: uuid.UUID, body: TicketCommentIn, db: DB, actor: Perm("tickets.read")):
    t = get_ticket(db, actor, ticket_id)
    c = svc.add_comment(db, actor, t, body.message, body.visibility)
    db.commit()
    return TicketCommentOut.model_validate(c).model_copy(update={"author_name": actor.user.full_name, "author_role": actor.role})


@router.post("/{ticket_id}/evidence", response_model=TicketDetail)
def add_evidence(ticket_id: uuid.UUID, body: TicketEvidenceIn, db: DB, actor: Perm("tickets.read")):
    """Link an uploaded file: a ticket attachment, or proof of work on the ticket's work order."""
    t = get_ticket(db, actor, ticket_id)
    media = get_scoped(db, Media, body.media_id, actor, "Media")
    if media.entity_type == "maintenance_task":
        task = svc.current_task(db, t)
        if task is None or media.entity_id != task.id:
            raise HTTPException(422, "Media belongs to a different record")
        msvc.link_evidence(db, actor, task, media, body.evidence_type, body.caption)
    else:
        svc.attach(db, actor, t, media, body.evidence_type, body.caption)
    return _commit(db, actor, t)


# ------------------------------------------------------------------ read-only views


@router.get("/{ticket_id}/timeline", response_model=list[TimelineItem])
def timeline(ticket_id: uuid.UUID, db: DB, actor: Perm("tickets.read")):
    t = get_ticket(db, actor, ticket_id)
    comments = _comments(db, actor, t)
    return _timeline(db, actor, t, comments, _attachments(db, actor, t))


@router.get("/{ticket_id}/history")
def history(ticket_id: uuid.UUID, db: DB, actor: Perm("tickets.read")):
    """Status history for everyone; the full audit trail for the layout office."""
    t = get_ticket(db, actor, ticket_id)
    rows = list(
        db.scalars(select(TicketStatusHistory).where(TicketStatusHistory.ticket_id == t.id).order_by(TicketStatusHistory.created_at))
    )
    names = user_names(db, (r.changed_by for r in rows))
    customer_view = actor.role == Role.RESIDENT
    status_rows = [
        StatusHistoryOut.model_validate(r).model_copy(
            update={
                "changed_by_name": names.get(r.changed_by),
                "reason": r.reason if (not customer_view or r.new_status in CUSTOMER_REASONS) else None,
            }
        )
        for r in rows
    ]
    out: dict = {"status": status_rows}
    if actor.is_manager():
        logs = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.tenant_id == actor.tenant_id, AuditLog.entity_type == "ticket", AuditLog.entity_id == t.id)
                .order_by(AuditLog.timestamp)
            )
        )
        anames = user_names(db, (r.actor_id for r in logs))
        out["audit"] = [AuditOut.model_validate(r).model_copy(update={"actor_name": anames.get(r.actor_id)}) for r in logs]
    return out


@router.get("/{ticket_id}/sla", response_model=SlaOut | None)
def sla(ticket_id: uuid.UUID, db: DB, actor: Perm("tickets.read")):
    t = get_ticket(db, actor, ticket_id)
    s = svc.get_sla(db, t)
    if s is None:
        return None
    return SlaOut.model_validate(s, from_attributes=True).model_copy(update={"state": svc.sla_state(t, s, db)})


@router.get("/{ticket_id}/evidence", response_model=list[AttachmentOut])
def evidence(ticket_id: uuid.UUID, db: DB, actor: Perm("tickets.read")):
    return _attachments(db, actor, get_ticket(db, actor, ticket_id))


@router.get("/{ticket_id}/assignments", response_model=list[AssignmentOut])
def assignments(ticket_id: uuid.UUID, db: DB, actor: Perm("tickets.manage")):
    t = get_ticket(db, actor, ticket_id)
    rows = list(db.scalars(select(TicketAssignment).where(TicketAssignment.ticket_id == t.id).order_by(TicketAssignment.assigned_at)))
    staff = user_names(db, [r.assignee_id for r in rows if r.assignee_type == "staff"] + [r.assigned_by for r in rows])
    vendors = vendor_names(db, [r.assignee_id for r in rows if r.assignee_type == "vendor"])
    return [
        AssignmentOut.model_validate(r).model_copy(
            update={
                "assignee_name": (vendors if r.assignee_type == "vendor" else staff).get(r.assignee_id),
                "assigned_by_name": staff.get(r.assigned_by),
            }
        )
        for r in rows
    ]


@router.get("/{ticket_id}/notifications", response_model=list[DeliveryOut])
def deliveries(ticket_id: uuid.UUID, db: DB, actor: Perm("tickets.manage")):
    """Notification delivery log for this ticket (§17-18)."""
    t = get_ticket(db, actor, ticket_id)
    rows = list(
        db.scalars(
            select(NotificationDelivery)
            .where(NotificationDelivery.entity_type == "ticket", NotificationDelivery.entity_id == t.id)
            .order_by(NotificationDelivery.created_at)
        )
    )
    names = user_names(db, (r.user_id for r in rows))
    return [DeliveryOut.model_validate(r).model_copy(update={"user_name": names.get(r.user_id)}) for r in rows]


@router.get("/{ticket_id}/work", response_model=WorkOrderOut | None)
def work_order(ticket_id: uuid.UUID, db: DB, actor: CurrentActor):
    t = get_ticket(db, actor, ticket_id)
    task = svc.current_task(db, t)
    return _work_order(db, task, actor.is_manager() or is_ticket_assignee(actor, t)) if task else None
