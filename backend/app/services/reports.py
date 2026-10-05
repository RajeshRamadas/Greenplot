"""Reports, dashboards and PDF documents (requirements §22, §40)."""

import io
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Asset,
    AuditLog,
    Complaint,
    EvidenceException,
    Incident,
    Inspection,
    Invoice,
    MaintenanceEvidence,
    MaintenanceMaterial,
    MaintenanceTask,
    Payment,
    Property,
    SosAlert,
    Tenant,
    User,
    Vendor,
    Visitor,
)
from app.models.base import utcnow
from app.models.enums import TaskStatus
from app.services.maintenance import OPEN_STATES, is_overdue, proof_status
from app.services.storage import get_storage

IST = ZoneInfo("Asia/Kolkata")
GREEN = colors.HexColor("#159a63")
INK = colors.HexColor("#102b24")
MUTED = colors.HexColor("#64756f")
LINE = colors.HexColor("#e2ebe7")


def fmt(dt: datetime | None) -> str:
    return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST") if dt else "—"


def _styles():
    ss = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle("brand", parent=ss["Title"], fontSize=20, textColor=GREEN, alignment=0, spaceAfter=0),
        "title": ParagraphStyle("title", parent=ss["Heading2"], textColor=INK, spaceBefore=2, spaceAfter=6),
        "h": ParagraphStyle("h", parent=ss["Heading4"], textColor=GREEN, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", parent=ss["BodyText"], fontSize=9, leading=12, textColor=INK),
        "small": ParagraphStyle("small", parent=ss["BodyText"], fontSize=7.5, leading=10, textColor=MUTED),
    }


def _kv_table(rows, st):
    data = [[Paragraph(f"<b>{k}</b>", st["small"]), Paragraph(str(v or "—"), st["body"])] for k, v in rows]
    t = Table(data, colWidths=[45 * mm, 125 * mm])
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5fbf8")),
            ]
        )
    )
    return t


def _grid(header, rows, widths, st):
    data = [[Paragraph(f"<b>{h}</b>", st["small"]) for h in header]] + [
        [Paragraph(str(c if c is not None else "—"), st["body"]) for c in r] for r in rows
    ]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf8f1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def _footer(text):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, text)
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw


def proof_report_pdf(db: Session, task: MaintenanceTask, include_evidence: bool = True) -> bytes:
    st = _styles()
    tenant = db.get(Tenant, task.tenant_id)
    names: dict[uuid.UUID, str] = {}

    def name(uid):
        if not uid:
            return None
        if uid not in names:
            u = db.get(User, uid)
            names[uid] = u.full_name if u else str(uid)
        return names[uid]

    prop = db.get(Property, task.property_id) if task.property_id else None
    asset = db.get(Asset, task.asset_id) if task.asset_id else None
    vendor = db.get(Vendor, task.vendor_id) if task.vendor_id else None
    story = [
        Paragraph("GreenPlot", st["brand"]),
        Paragraph("Property Management Made Simple", st["small"]),
        Spacer(1, 4),
        Paragraph("Maintenance Proof of Work", st["title"]),
        _kv_table(
            [
                ("Record ID", task.number),
                ("Layout", tenant.name if tenant else None),
                ("Property", f"Plot {prop.plot_number} ({prop.code})" if prop else task.location_note),
                ("Asset", f"{asset.name} · {asset.code}" if asset else None),
                ("Task", task.title),
                ("Category", task.category.replace("_", " ").title()),
                ("Priority", task.priority.title()),
                ("Status", task.status.replace("_", " ").title()),
                ("Assigned staff / vendor", " / ".join(x for x in [name(task.assigned_staff_id), vendor.name if vendor else None] if x)),
                ("Start time", fmt(task.started_at)),
                ("Completion time", fmt(task.completed_at)),
                ("Completed by", name(task.completed_by)),
            ],
            st,
        ),
    ]

    story.append(Paragraph("Checklist", st["h"]))
    if task.checklist:
        story.append(
            _grid(
                ["Item", "Result", "Reason"],
                [[i.label, i.status.title(), i.reason] for i in task.checklist],
                [90 * mm, 25 * mm, 55 * mm],
                st,
            )
        )
    else:
        story.append(Paragraph("No checklist configured.", st["small"]))

    evidence = [
        e
        for e in db.scalars(
            select(MaintenanceEvidence).where(MaintenanceEvidence.maintenance_id == task.id).order_by(MaintenanceEvidence.uploaded_at)
        )
    ]
    storage = get_storage()

    def evidence_block(title, types):
        items = [e for e in evidence if e.evidence_type in types and e.status == "active"]
        block = [Paragraph(title, st["h"])]
        if not include_evidence:
            block.append(Paragraph("Evidence withheld under the layout's privacy settings.", st["small"]))
            return block
        if not items:
            block.append(Paragraph("None recorded.", st["small"]))
            return block
        cells = []
        for e in items:
            img = None
            m = e.media
            key = m.thumbnail_key if m and m.thumbnail_key else None
            if key:
                try:
                    img = Image(io.BytesIO(storage.get(key)), width=52 * mm, height=39 * mm, kind="proportional")
                except Exception:
                    img = None
            caption = Paragraph(
                f"{e.evidence_type.replace('_', ' ').title()} · {fmt(e.captured_at or e.uploaded_at)}<br/>by {name(e.uploaded_by)}"
                + (f"<br/>GPS {e.latitude:.5f}, {e.longitude:.5f}" if e.latitude is not None else "")
                + f"<br/>SHA-256 {e.sha256[:16]}…"
                + (f"<br/>Rework round {e.rework_round}" if e.rework_round else ""),
                st["small"],
            )
            cells.append([img or Paragraph(m.content_type if m else "file", st["small"]), caption])
        rows = [sum(cells[i : i + 3], []) for i in range(0, len(cells), 3)]
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        t = Table(rows, colWidths=[28 * mm, 28 * mm] * (width // 2))
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.4, LINE)]))
        block.append(t)
        return block

    story += evidence_block("Before Evidence", {"before_photo"})
    story += evidence_block("After Evidence", {"after_photo", "video", "photo"})

    story.append(Paragraph("Work Notes", st["h"]))
    for label, val in (
        ("Work performed", task.work_notes),
        ("Issue found", task.issue_found),
        ("Outcome", task.outcome),
        ("Observations", task.observations),
    ):
        if val:
            story.append(Paragraph(f"<b>{label}:</b> {val}", st["body"]))
    if not any([task.work_notes, task.issue_found, task.outcome, task.observations]):
        story.append(Paragraph("None recorded.", st["small"]))

    story.append(Paragraph("Materials", st["h"]))
    mats = list(db.scalars(select(MaintenanceMaterial).where(MaintenanceMaterial.task_id == task.id)))
    if mats:
        rows = [
            [m.name, f"{float(m.quantity):g} {m.unit}", f"₹{float(m.unit_cost):,.2f}" if m.unit_cost is not None else None, m.supplier]
            for m in mats
        ]
        story.append(_grid(["Material", "Quantity", "Unit cost", "Supplier"], rows, [70 * mm, 30 * mm, 30 * mm, 40 * mm], st))
    else:
        story.append(Paragraph("None recorded.", st["small"]))

    docs = [
        e for e in evidence if e.evidence_type in ("invoice", "receipt", "service_report", "warranty", "document") and e.status == "active"
    ]
    story.append(Paragraph("Invoice / Service Documents", st["h"]))
    if docs:
        story.append(
            _grid(
                ["Document", "Uploaded", "SHA-256"],
                [
                    [
                        d.evidence_type.replace("_", " ").title()
                        + (f" · {d.media.original_filename}" if d.media and d.media.original_filename else ""),
                        fmt(d.uploaded_at),
                        d.sha256,
                    ]
                    for d in docs
                ],
                [60 * mm, 45 * mm, 65 * mm],
                st,
            )
        )
    else:
        story.append(Paragraph("None attached.", st["small"]))

    story.append(Paragraph("Location", st["h"]))
    gps = []
    if task.start_latitude is not None:
        gps.append(f"Start: {task.start_latitude:.5f}, {task.start_longitude:.5f}")
    if task.complete_latitude is not None:
        gps.append(f"Completion: {task.complete_latitude:.5f}, {task.complete_longitude:.5f}")
    if task.gps_accuracy_m:
        gps.append(f"Accuracy ±{task.gps_accuracy_m:.0f} m")
    if task.asset_scanned_at:
        gps.append(f"Asset {task.asset_scan_method.upper()} scan at {fmt(task.asset_scanned_at)}")
    story.append(Paragraph(" · ".join(gps) or "Not captured.", st["body"]))
    story.append(Paragraph("GPS is supporting evidence only and does not by itself prove quality or completion.", st["small"]))

    excs = list(db.scalars(select(EvidenceException).where(EvidenceException.task_id == task.id)))
    if excs:
        story.append(Paragraph("Evidence Exceptions", st["h"]))
        story.append(
            _grid(
                ["Requirement", "Reason", "Review"],
                [[x.requirement.replace("_", " "), f"{x.reason_code}: {x.reason}", x.review_status] for x in excs],
                [35 * mm, 100 * mm, 35 * mm],
                st,
            )
        )

    story.append(Paragraph("Supervisor Decision", st["h"]))
    story.append(
        _kv_table(
            [
                ("Decision", (task.review_decision or ("pending" if task.status == TaskStatus.COMPLETED else "—")).title()),
                ("Reviewer", name(task.reviewed_by)),
                ("Comment", task.review_comment),
                ("Approval timestamp", fmt(task.approved_at)),
                ("Rework rounds", task.rework_count),
                ("Resident acknowledgement", fmt(task.resident_ack_at) if task.resident_ack_at else None),
            ],
            st,
        )
    )

    story.append(Paragraph("Audit Summary", st["h"]))
    logs = list(
        db.scalars(
            select(AuditLog).where(AuditLog.entity_type == "maintenance_task", AuditLog.entity_id == task.id).order_by(AuditLog.timestamp)
        )
    )
    rows = [[fmt(a.timestamp), a.action.replace("maintenance.", "").replace("_", " "), name(a.actor_id) or "system"] for a in logs]
    story.append(KeepTogether(_grid(["Time", "Action", "By"], rows, [50 * mm, 80 * mm, 40 * mm], st)))
    proof = proof_status(db, task)
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "Evidence policy: " + ", ".join(f"{r['key'].replace('_', ' ')} ({r['state']})" for r in proof["requirements"] if r["required"]),
            st["small"],
        )
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"{task.number} Proof of Work",
        author="GreenPlot",
    )
    foot = _footer(f"{task.number} · generated {fmt(utcnow())} · evidence hashes allow independent verification of original files")
    doc.build(story, onFirstPage=foot, onLaterPages=foot)
    return buf.getvalue()


def receipt_pdf(db: Session, p: Payment) -> bytes:
    st = _styles()
    inv = db.get(Invoice, p.invoice_id)
    prop = db.get(Property, p.property_id)
    tenant = db.get(Tenant, p.tenant_id)
    story = [
        Paragraph("GreenPlot", st["brand"]),
        Paragraph(tenant.name, st["small"]),
        Spacer(1, 6),
        Paragraph(f"Payment Receipt · {p.receipt_number}", st["title"]),
        _kv_table(
            [
                ("Received from", prop.owner_name or f"Plot {prop.plot_number}"),
                ("Property", f"Plot {prop.plot_number} ({prop.code})"),
                ("For", f"{inv.number} · {inv.description}"),
                ("Amount", f"₹{float(p.amount):,.2f}"),
                ("Method", p.method.replace("_", " ").title() + (f" · {p.reference}" if p.reference else "")),
                ("Gateway reference", p.provider_payment_id),
                ("Paid at", fmt(p.paid_at)),
                ("Invoice balance", f"₹{float(inv.amount) - float(inv.amount_paid):,.2f}"),
            ],
            st,
        ),
        Spacer(1, 8),
        Paragraph("This is a computer-generated receipt and does not require a signature. It is not a GST tax invoice.", st["small"]),
    ]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, title=p.receipt_number).build(story)
    return buf.getvalue()


# ------------------------------------------------------------------ datasets


def _materials_cost(db: Session, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, float]:
    if not task_ids:
        return {}
    rows = db.execute(
        select(MaintenanceMaterial.task_id, func.sum(MaintenanceMaterial.quantity * func.coalesce(MaintenanceMaterial.unit_cost, 0)))
        .where(MaintenanceMaterial.task_id.in_(task_ids))
        .group_by(MaintenanceMaterial.task_id)
    ).all()
    return {r[0]: float(r[1] or 0) for r in rows}


def maintenance_rows(db: Session, tasks: list[MaintenanceTask]) -> list[dict]:
    costs = _materials_cost(db, [t.id for t in tasks])
    users = (
        {
            u.id: u.full_name
            for u in db.scalars(
                select(User).where(
                    User.id.in_(
                        {t.assigned_staff_id for t in tasks if t.assigned_staff_id} | {t.reviewed_by for t in tasks if t.reviewed_by}
                    )
                )
            )
        }
        if tasks
        else {}
    )
    vendors = (
        {v.id: v.name for v in db.scalars(select(Vendor).where(Vendor.id.in_({t.vendor_id for t in tasks if t.vendor_id})))}
        if tasks
        else {}
    )
    props = (
        {p.id: p.plot_number for p in db.scalars(select(Property).where(Property.id.in_({t.property_id for t in tasks if t.property_id})))}
        if tasks
        else {}
    )
    ev_counts = (
        dict(
            db.execute(
                select(MaintenanceEvidence.maintenance_id, func.count())
                .where(MaintenanceEvidence.maintenance_id.in_([t.id for t in tasks]), MaintenanceEvidence.status == "active")
                .group_by(MaintenanceEvidence.maintenance_id)
            ).all()
        )
        if tasks
        else {}
    )
    rows = []
    for t in tasks:
        hours = None
        if t.started_at and t.completed_at:
            hours = round((t.completed_at - t.started_at).total_seconds() / 3600, 2)
        approval_hours = None
        if t.completed_at and t.approved_at:
            approval_hours = round((t.approved_at - t.completed_at).total_seconds() / 3600, 2)
        rows.append(
            {
                "id": t.id,
                "number": t.number,
                "title": t.title,
                "category": t.category,
                "priority": t.priority,
                "status": t.status,
                "plot": props.get(t.property_id),
                "staff": users.get(t.assigned_staff_id),
                "vendor": vendors.get(t.vendor_id),
                "created_at": t.created_at,
                "due_at": t.due_at,
                "started_at": t.started_at,
                "completed_at": t.completed_at,
                "approved_at": t.approved_at,
                "reviewer": users.get(t.reviewed_by),
                "rework_count": t.rework_count,
                "evidence_items": ev_counts.get(t.id, 0),
                "materials_cost": costs.get(t.id, 0.0),
                "estimated_cost": float(t.estimated_cost) if t.estimated_cost is not None else None,
                "work_hours": hours,
                "approval_hours": approval_hours,
                "overdue": is_overdue(t),
            }
        )
    return rows


def vendor_performance_rows(
    db: Session, tenant_id: uuid.UUID, vendor_id: uuid.UUID | None = None, since: datetime | None = None
) -> list[dict]:
    stmt = select(Vendor).where(Vendor.tenant_id == tenant_id, Vendor.deleted_at.is_(None))
    if vendor_id:
        stmt = stmt.where(Vendor.id == vendor_id)
    out = []
    for v in db.scalars(stmt.order_by(Vendor.name)):
        q = select(MaintenanceTask).where(
            MaintenanceTask.tenant_id == tenant_id, MaintenanceTask.vendor_id == v.id, MaintenanceTask.deleted_at.is_(None)
        )
        if since:
            q = q.where(MaintenanceTask.created_at >= since)
        tasks = list(db.scalars(q))
        done = [t for t in tasks if t.status in (TaskStatus.APPROVED, TaskStatus.CLOSED)]
        on_time = [t for t in done if not t.due_at or (t.completed_at and t.completed_at <= t.due_at)]
        durations = [(t.completed_at - t.started_at).total_seconds() / 3600 for t in done if t.started_at and t.completed_at]
        cost = sum(_materials_cost(db, [t.id for t in tasks]).values())
        out.append(
            {
                "vendor_id": v.id,
                "vendor": v.name,
                "jobs": len(tasks),
                "open": sum(1 for t in tasks if t.status in OPEN_STATES),
                "completed": len(done),
                "first_time_approved": sum(1 for t in done if t.rework_count == 0),
                "rework_jobs": sum(1 for t in tasks if t.rework_count),
                "on_time_rate": round(len(on_time) / len(done), 3) if done else None,
                "avg_hours": round(sum(durations) / len(durations), 2) if durations else None,
                "materials_cost": round(cost, 2),
            }
        )
    return out


def dashboard(db: Session, tenant_id: uuid.UUID) -> dict:
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    T = MaintenanceTask

    def count(stmt):
        return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    base = select(T.id).where(T.tenant_id == tenant_id, T.deleted_at.is_(None))
    open_states = [s.value for s in OPEN_STATES if s != TaskStatus.COMPLETED]
    completed_month = count(base.where(T.status.in_(["approved", "closed"]), T.approved_at >= month_start))
    month_tasks = list(db.scalars(select(T).where(T.tenant_id == tenant_id, T.completed_at >= month_start)))
    cost_month = sum(
        _materials_cost(db, [t.id for t in db.scalars(select(T).where(T.tenant_id == tenant_id, T.approved_at >= month_start))]).values()
    )
    billed = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount), 0)).where(Invoice.tenant_id == tenant_id, Invoice.deleted_at.is_(None))
    )
    paid = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount_paid), 0)).where(Invoice.tenant_id == tenant_id, Invoice.deleted_at.is_(None))
    )
    recent = list(db.scalars(select(T).where(T.tenant_id == tenant_id, T.deleted_at.is_(None)).order_by(T.updated_at.desc()).limit(8)))
    props = (
        {p.id: p.plot_number for p in db.scalars(select(Property).where(Property.id.in_({t.property_id for t in recent if t.property_id})))}
        if recent
        else {}
    )
    approved = list(db.scalars(select(T).where(T.tenant_id == tenant_id, T.approved_at >= now - timedelta(days=90))))
    return {
        "generated_at": now,
        "properties": count(select(Property.id).where(Property.tenant_id == tenant_id, Property.deleted_at.is_(None))),
        "open_complaints": count(
            select(Complaint.id).where(
                Complaint.tenant_id == tenant_id, Complaint.status.in_(["open", "assigned", "in_progress"]), Complaint.deleted_at.is_(None)
            )
        ),
        "active_maintenance": count(base.where(T.status.in_(open_states))),
        "overdue_tasks": count(base.where(T.status.in_([s.value for s in OPEN_STATES]), T.due_at < now)),
        "completed_this_month": completed_month,
        "pending_approvals": count(base.where(T.status == TaskStatus.COMPLETED)),
        "maintenance_cost_this_month": round(cost_month, 2),
        "vendor_active_jobs": count(base.where(T.vendor_id.is_not(None), T.status.in_(open_states))),
        "staff_active_jobs": count(base.where(T.assigned_staff_id.is_not(None), T.status.in_(open_states))),
        "open_incidents": count(
            select(Incident.id).where(Incident.tenant_id == tenant_id, Incident.status.in_(["open", "acknowledged", "investigating"]))
        ),
        "active_sos": count(select(SosAlert.id).where(SosAlert.tenant_id == tenant_id, SosAlert.status.in_(["active", "acknowledged"]))),
        "inspections_this_month": count(
            select(Inspection.id).where(Inspection.tenant_id == tenant_id, Inspection.completed_at >= month_start)
        ),
        "visitors_today": count(
            select(Visitor.id).where(
                Visitor.tenant_id == tenant_id, Visitor.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0)
            )
        ),
        "billing": {"billed": float(billed), "collected": float(paid), "outstanding": float(Decimal(str(billed)) - Decimal(str(paid)))},
        "metrics": success_metrics(approved, month_tasks),
        "recent_activity": [
            {
                "id": t.id,
                "number": t.number,
                "title": t.title,
                "status": t.status,
                "plot": props.get(t.property_id),
                "updated_at": t.updated_at,
            }
            for t in recent
        ],
    }


def success_metrics(approved: list[MaintenanceTask], _month: list[MaintenanceTask]) -> dict:
    """§43 success metrics over recently approved work."""
    if not approved:
        return {"approved_without_rework": None, "avg_completion_hours": None, "avg_approval_hours": None, "sample": 0}
    first = sum(1 for t in approved if t.rework_count == 0)
    comp = [(t.completed_at - t.started_at).total_seconds() / 3600 for t in approved if t.started_at and t.completed_at]
    appr = [(t.approved_at - t.completed_at).total_seconds() / 3600 for t in approved if t.completed_at and t.approved_at]
    return {
        "approved_without_rework": round(first / len(approved), 3),
        "avg_completion_hours": round(sum(comp) / len(comp), 2) if comp else None,
        "avg_approval_hours": round(sum(appr) / len(appr), 2) if appr else None,
        "sample": len(approved),
    }
