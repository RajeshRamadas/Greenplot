import csv
import io
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select

from app.core.deps import DB, CurrentActor, Perm
from app.models import (
    Complaint,
    Invoice,
    MaintenanceTask,
    Notice,
    PatrolRun,
    Property,
    SosAlert,
    Visitor,
)
from app.models.base import utcnow
from app.models.enums import Role, TaskCategory, TaskStatus
from app.schemas.operations import SearchOut
from app.services import reports as svc
from app.services.access import resident_property_ids, scope_tasks, tenant_select
from app.services.maintenance import OPEN_STATES
from app.services.search import search

router = APIRouter(tags=["reports"])

REPORTS = ("history", "pending", "completed", "rework", "cost", "proof")


def _filtered_tasks(
    db, actor, *, report, date_from, date_to, layout_id, property_id, asset_id, category, staff_id, vendor_id, status, approval
):
    T = MaintenanceTask
    stmt = scope_tasks(tenant_select(T, actor), db, actor)
    if report == "pending":
        stmt = stmt.where(T.status.in_([s.value for s in OPEN_STATES]))
    elif report in ("completed", "proof"):
        stmt = stmt.where(T.status.in_(["completed", "approved", "closed"]))
    elif report == "rework":
        stmt = stmt.where(T.rework_count > 0)
    elif report == "cost":
        stmt = stmt.where(T.status.in_(["approved", "closed"]))
    if date_from:
        stmt = stmt.where(T.created_at >= date_from)
    if date_to:
        stmt = stmt.where(T.created_at <= date_to)
    if layout_id:
        stmt = stmt.where(or_(T.layout_id == layout_id, T.property_id.in_(select(Property.id).where(Property.layout_id == layout_id))))
    if property_id:
        stmt = stmt.where(T.property_id == property_id)
    if asset_id:
        stmt = stmt.where(T.asset_id == asset_id)
    if category:
        stmt = stmt.where(T.category.in_(category))
    if staff_id:
        stmt = stmt.where(T.assigned_staff_id == staff_id)
    if vendor_id:
        stmt = stmt.where(T.vendor_id == vendor_id)
    if status:
        stmt = stmt.where(T.status.in_(status))
    if approval == "pending":
        stmt = stmt.where(T.status == TaskStatus.COMPLETED)
    elif approval == "approved":
        stmt = stmt.where(T.status.in_(["approved", "closed"]))
    elif approval == "rework":
        stmt = stmt.where(T.rework_count > 0)
    return list(db.scalars(stmt.order_by(T.created_at.desc()).limit(5000)))


@router.get("/reports/maintenance")
def maintenance_report(
    db: DB,
    actor: Perm("reports.read"),
    report: str = Query("history", pattern="^(history|pending|completed|rework|cost|proof)$"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    layout_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    category: list[TaskCategory] | None = Query(None),
    staff_id: uuid.UUID | None = None,
    vendor_id: uuid.UUID | None = None,
    status: list[TaskStatus] | None = Query(None),
    approval: str | None = Query(None, pattern="^(pending|approved|rework)$"),
    format: str = Query("json", pattern="^(json|csv)$"),
):
    tasks = _filtered_tasks(
        db,
        actor,
        report=report,
        date_from=date_from,
        date_to=date_to,
        layout_id=layout_id,
        property_id=property_id,
        asset_id=asset_id,
        category=category,
        staff_id=staff_id,
        vendor_id=vendor_id,
        status=status,
        approval=approval,
    )
    rows = svc.maintenance_rows(db, tasks)
    summary = {
        "count": len(rows),
        "materials_cost": round(sum(r["materials_cost"] for r in rows), 2),
        "rework_tasks": sum(1 for r in rows if r["rework_count"]),
        "overdue": sum(1 for r in rows if r["overdue"]),
        "by_category": {},
        "by_status": {},
    }
    for r in rows:
        summary["by_category"][r["category"]] = summary["by_category"].get(r["category"], 0) + 1
        summary["by_status"][r["status"]] = summary["by_status"].get(r["status"], 0) + 1
    if format == "csv":
        buf = io.StringIO()
        fields = [k for k in (rows[0].keys() if rows else ["number"]) if k != "id"]
        w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (v.isoformat() if isinstance(v, (datetime, date)) else v) for k, v in r.items()})
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="greenplot-{report}-{date.today()}.csv"'},
        )
    return {"report": report, "summary": summary, "rows": rows}


@router.get("/reports/vendors")
def vendor_report(db: DB, actor: Perm("reports.read"), since: datetime | None = None):
    return svc.vendor_performance_rows(db, actor.tenant_id, since=since)


@router.get("/reports/assets/{asset_id}")
def asset_report(asset_id: uuid.UUID, db: DB, actor: Perm("reports.read")):
    from app.api.v1.people import asset_history

    return asset_history(asset_id, db, actor)


@router.get("/reports/staff")
def staff_report(db: DB, actor: Perm("reports.read"), since: datetime | None = None):
    T = MaintenanceTask
    stmt = select(T).where(T.tenant_id == actor.tenant_id, T.assigned_staff_id.is_not(None), T.deleted_at.is_(None))
    if since:
        stmt = stmt.where(T.created_at >= since)
    by: dict[uuid.UUID, dict] = {}
    for t in db.scalars(stmt):
        d = by.setdefault(t.assigned_staff_id, {"user_id": t.assigned_staff_id, "assigned": 0, "completed": 0, "rework": 0, "overdue": 0})
        d["assigned"] += 1
        d["completed"] += t.status in ("approved", "closed")
        d["rework"] += t.rework_count > 0
        d["overdue"] += bool(t.due_at and t.due_at < utcnow() and t.status in [s.value for s in OPEN_STATES])
    from app.api.v1._util import user_names

    names = user_names(db, by.keys())
    return sorted(({**d, "name": names.get(k)} for k, d in by.items()), key=lambda d: -d["assigned"])


# ------------------------------------------------------------------ dashboard


@router.get("/dashboard")
def dashboard(db: DB, actor: Perm("dashboard.read")):
    """Role-specific dashboard."""
    role = actor.role
    now = utcnow()
    if role in (Role.LAYOUT_ADMIN, Role.SUPERVISOR):
        data = svc.dashboard(db, actor.tenant_id)
        data["role"] = role
        return data

    def count(stmt):
        return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    T = MaintenanceTask
    if role in (Role.STAFF, Role.VENDOR):
        mine = select(T.id).where(T.tenant_id == actor.tenant_id, T.deleted_at.is_(None))
        mine = mine.where(T.vendor_id == actor.user.vendor_id) if role == Role.VENDOR else mine.where(T.assigned_staff_id == actor.id)
        return {
            "role": role,
            "assigned": count(mine.where(T.status.in_(["assigned", "accepted"]))),
            "in_progress": count(mine.where(T.status == "started")),
            "rework": count(mine.where(T.status == "rework_required")),
            "awaiting_review": count(mine.where(T.status == "completed")),
            "overdue": count(mine.where(T.status.in_([s.value for s in OPEN_STATES]), T.due_at < now)),
            "completed_this_month": count(
                mine.where(
                    T.status.in_(["approved", "closed"]), T.approved_at >= now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                )
            ),
        }
    if role == Role.GUARD:
        return {
            "role": role,
            "visitors_inside": count(select(Visitor.id).where(Visitor.tenant_id == actor.tenant_id, Visitor.status == "inside")),
            "awaiting_approval": count(
                select(Visitor.id).where(Visitor.tenant_id == actor.tenant_id, Visitor.status == "pending_approval")
            ),
            "active_sos": count(
                select(SosAlert.id).where(SosAlert.tenant_id == actor.tenant_id, SosAlert.status.in_(["active", "acknowledged"]))
            ),
            "my_active_patrols": count(select(PatrolRun.id).where(PatrolRun.guard_id == actor.id, PatrolRun.status == "in_progress")),
            "visitors_today": count(
                select(Visitor.id).where(
                    Visitor.tenant_id == actor.tenant_id, Visitor.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0)
                )
            ),
        }
    # resident
    props = resident_property_ids(db, actor) or {uuid.uuid4()}
    outstanding = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount - Invoice.amount_paid), 0)).where(
            Invoice.property_id.in_(props), Invoice.status.in_(["unpaid", "partial"]), Invoice.deleted_at.is_(None)
        )
    )
    recent = list(db.scalars(select(T).where(T.property_id.in_(props), T.deleted_at.is_(None)).order_by(T.updated_at.desc()).limit(5)))
    properties = list(db.scalars(select(Property).where(Property.id.in_(props))))
    return {
        "role": role,
        "properties": [
            {"id": p.id, "plot_number": p.plot_number, "code": p.code, "condition": p.condition, "status": p.status} for p in properties
        ],
        "dues_outstanding": float(outstanding or 0),
        "open_complaints": count(
            select(Complaint.id).where(
                Complaint.tenant_id == actor.tenant_id,
                or_(Complaint.raised_by == actor.id, Complaint.property_id.in_(props)),
                Complaint.status.in_(["open", "assigned", "in_progress"]),
            )
        ),
        "active_maintenance": count(select(T.id).where(T.property_id.in_(props), T.status.in_([s.value for s in OPEN_STATES]))),
        "visitors_expected": count(
            select(Visitor.id).where(Visitor.property_id.in_(props), Visitor.status == "approved", Visitor.entry_at.is_(None))
        ),
        "notices": count(
            select(Notice.id).where(
                Notice.tenant_id == actor.tenant_id, Notice.deleted_at.is_(None), Notice.audience.in_(["all", "residents"])
            )
        ),
        "recent_maintenance": [
            {"id": t.id, "number": t.number, "title": t.title, "status": t.status, "updated_at": t.updated_at} for t in recent
        ],
    }


# ------------------------------------------------------------------ search


@router.get("/records/search", response_model=SearchOut)
def records_search(
    db: DB,
    actor: Perm("records.search"),
    q: str | None = None,
    type: str | None = Query(None, pattern="^(maintenance|complaint|inspection|incident|asset|property|vendor|staff)$"),
    property_id: uuid.UUID | None = None,
    plot: str | None = None,
    category: str | None = None,
    status: str | None = None,
    asset_id: uuid.UUID | None = None,
    vendor_id: uuid.UUID | None = None,
    staff_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    interpreted, hits = search(
        db, actor, q, type, property_id, plot, category, status, asset_id, vendor_id, staff_id, date_from, date_to, limit
    )
    return SearchOut(query=q, interpreted=interpreted, total=len(hits), items=hits)


@router.get("/meta")
def meta(actor: CurrentActor):
    """Enumerations for building forms."""
    from app.models.enums import INSPECTION_POINTS, EvidenceType, Priority, RequirementKey

    return {
        "task_categories": [c.value for c in TaskCategory],
        "task_statuses": [s.value for s in TaskStatus],
        "priorities": [p.value for p in Priority],
        "evidence_types": [e.value for e in EvidenceType],
        "requirement_keys": [r.value for r in RequirementKey],
        "inspection_points": INSPECTION_POINTS,
        "asset_categories": ["gate", "pump", "motor", "streetlight", "electrical", "water", "security", "infrastructure"],
        "complaint_categories": [
            "gate",
            "fence",
            "plumbing",
            "water",
            "electrical",
            "streetlight",
            "cleaning",
            "garbage",
            "garden",
            "drainage",
            "road",
            "security",
            "other",
        ],
        "exception_reasons": ["camera_unavailable", "no_gps_signal", "not_applicable", "privacy", "device_issue", "other"],
    }
