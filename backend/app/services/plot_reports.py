"""Monthly plot health report for owners (visits done, photos, issues spotted).

On the first worker run of each month every plot with an owner gets last month's
report: a short WhatsApp/email summary plus a link to a PDF with the details and
a few of the after photos. Tenant setting ``plot_report_enabled`` (default on).
"""

import io
import logging
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import (
    Complaint,
    Incident,
    Inspection,
    MaintenanceEvidence,
    MaintenanceSchedule,
    MaintenanceTask,
    Media,
    PlotReport,
    Property,
    Resident,
    Tenant,
)
from app.models.base import utcnow
from app.models.enums import Condition, EvidenceType, InspectionStatus, MediaStatus, TaskStatus
from app.services import audit, owner_contact
from app.services.billing import add_months, outstanding
from app.services.maintenance import OPEN_STATES, tenant_setting
from app.services.plot_reminders import outstanding_invoices
from app.services.reports import IST, LINE, _footer, _grid, _kv_table, _styles, fmt
from app.services.storage import get_storage

log = logging.getLogger("greenplot.plot_reports")

TOKEN_KIND = "plot-report"
LINK_DAYS = 400
PHOTO_TYPES = [EvidenceType.BEFORE_PHOTO, EvidenceType.AFTER_PHOTO, EvidenceType.PHOTO]
MAX_PDF_PHOTOS = 6


def month_bounds(any_day: date) -> tuple[date, date]:
    start = any_day.replace(day=1)
    return start, add_months(start, 1) - timedelta(days=1)


def _utc_range(start: date, end: date) -> tuple[datetime, datetime]:
    lo = datetime.combine(start, time.min, IST)
    hi = datetime.combine(end + timedelta(days=1), time.min, IST)
    return lo, hi


def build_summary(db: Session, prop: Property, start: date, end: date) -> dict:
    lo, hi = _utc_range(start, end)
    T = MaintenanceTask
    visits = list(
        db.scalars(
            select(T)
            .where(
                T.property_id == prop.id,
                T.deleted_at.is_(None),
                T.status.in_([TaskStatus.APPROVED, TaskStatus.CLOSED]),
                T.approved_at >= lo,
                T.approved_at < hi,
            )
            .order_by(T.approved_at)
        )
    )
    inspections = list(
        db.scalars(
            select(Inspection)
            .where(
                Inspection.property_id == prop.id,
                Inspection.deleted_at.is_(None),
                Inspection.status == InspectionStatus.COMPLETED,
                Inspection.completed_at >= lo,
                Inspection.completed_at < hi,
            )
            .order_by(Inspection.completed_at)
        )
    )
    photos = list(
        db.scalars(
            select(MaintenanceEvidence).where(
                MaintenanceEvidence.maintenance_id.in_([t.id for t in visits] or [uuid.uuid4()]),
                MaintenanceEvidence.status == "active",
                MaintenanceEvidence.evidence_type.in_(PHOTO_TYPES),
            )
        )
    )
    inspection_photos = db.scalars(
        select(Media.id).where(
            Media.entity_type == "inspection",
            Media.entity_id.in_([i.id for i in inspections] or [uuid.uuid4()]),
            Media.status == MediaStatus.READY,
            Media.content_type.like("image/%"),
        )
    ).all()

    issues = []
    for i in inspections:
        for item in i.items:
            if item.condition in (Condition.ISSUE, Condition.ATTENTION):
                label = item.point.replace("_", " ").capitalize()
                issues.append(
                    {
                        "source": "inspection",
                        "severity": item.condition,
                        "text": f"{label}: {item.notes or ('needs attention' if item.condition == Condition.ATTENTION else 'issue found')}",
                        "date": i.completed_at.astimezone(IST).date().isoformat(),
                    }
                )
    for inc in db.scalars(
        select(Incident).where(
            Incident.property_id == prop.id, Incident.deleted_at.is_(None), Incident.occurred_at >= lo, Incident.occurred_at < hi
        )
    ):
        issues.append(
            {"source": "incident", "severity": "issue", "text": inc.title, "date": inc.occurred_at.astimezone(IST).date().isoformat()}
        )
    for c in db.scalars(
        select(Complaint).where(
            Complaint.property_id == prop.id, Complaint.deleted_at.is_(None), Complaint.created_at >= lo, Complaint.created_at < hi
        )
    ):
        issues.append(
            {
                "source": "complaint",
                "severity": "attention",
                "text": f"{c.title} ({c.status.replace('_', ' ')})",
                "date": c.created_at.astimezone(IST).date().isoformat(),
            }
        )

    open_jobs = db.scalar(
        select(T.id).where(T.property_id == prop.id, T.deleted_at.is_(None), T.status.in_([s.value for s in OPEN_STATES])).limit(1)
    )
    next_visit = db.scalar(
        select(MaintenanceSchedule.next_run_on)
        .where(
            MaintenanceSchedule.property_id == prop.id,
            MaintenanceSchedule.is_active.is_(True),
            MaintenanceSchedule.deleted_at.is_(None),
        )
        .order_by(MaintenanceSchedule.next_run_on)
        .limit(1)
    )
    due = sum((outstanding(i) for i in outstanding_invoices(db, prop.id)), Decimal("0"))
    return {
        "visits": [
            {
                "number": t.number,
                "title": t.title,
                "category": t.category,
                "date": t.approved_at.astimezone(IST).date().isoformat(),
                "task_id": str(t.id),
            }
            for t in visits
        ],
        "inspections": [
            {"number": i.number, "condition": i.overall_condition, "date": i.completed_at.astimezone(IST).date().isoformat()}
            for i in inspections
        ],
        "visit_count": len(visits) + len(inspections),
        "photo_count": len(photos) + len(inspection_photos),
        "issues": issues,
        "has_open_jobs": open_jobs is not None,
        "next_visit": next_visit.isoformat() if next_visit else None,
        "outstanding": str(due),
        "condition": prop.condition,
    }


def summary_line(s: dict) -> str:
    v, p, issues = s["visit_count"], s["photo_count"], s["issues"]
    parts = [f"{v} visit{'s' if v != 1 else ''}", f"{p} photo{'s' if p != 1 else ''}"]
    if issues:
        parts.append(f"{len(issues)} issue{'s' if len(issues) != 1 else ''} spotted ({issues[0]['text']})")
    else:
        parts.append("no issues spotted")
    line = ", ".join(parts) + "."
    if s.get("next_visit"):
        line += f" Next visit {date.fromisoformat(s['next_visit']):%d %b}."
    return line


def report_pdf(db: Session, prop: Property, report: PlotReport) -> bytes:
    st = _styles()
    s = report.summary
    tenant = db.get(Tenant, prop.tenant_id)
    period = f"{report.period_start:%B %Y}"
    story = [
        Paragraph("GreenPlot", st["brand"]),
        Paragraph(tenant.name if tenant else "Property Management Made Simple", st["small"]),
        Spacer(1, 4),
        Paragraph(f"Plot Health Report · {period}", st["title"]),
        _kv_table(
            [
                ("Property", f"Plot {prop.plot_number} ({prop.code})"),
                ("Layout", prop.layout.name if prop.layout else None),
                ("Owner", prop.owner_name),
                ("Period", f"{report.period_start:%d %b %Y} – {report.period_end:%d %b %Y}"),
                ("Plot condition", (s.get("condition") or "—").replace("_", " ").title()),
                ("Summary", summary_line(s)),
                ("Next visit", fmt_date(s.get("next_visit"))),
                ("Outstanding dues", f"₹{Decimal(s.get('outstanding') or '0'):,.2f}"),
            ],
            st,
        ),
        Paragraph("Visits", st["h"]),
    ]
    rows = [[v["date"], v["number"], v["title"]] for v in s["visits"]]
    rows += [[i["date"], i["number"], f"Property watch inspection · {(i['condition'] or 'done').title()}"] for i in s["inspections"]]
    if rows:
        story.append(_grid(["Date", "Record", "Work"], [[fmt_date(r[0]), *r[1:]] for r in sorted(rows)], [30 * mm, 45 * mm, 95 * mm], st))
    else:
        story.append(Paragraph("No visits were completed this month.", st["small"]))

    story.append(Paragraph("Issues spotted", st["h"]))
    if s["issues"]:
        story.append(
            _grid(
                ["Date", "Source", "Details"],
                [[fmt_date(i["date"]), i["source"].title(), i["text"]] for i in s["issues"]],
                [30 * mm, 30 * mm, 110 * mm],
                st,
            )
        )
    else:
        story.append(Paragraph("Nothing to report: no encroachment, dumping or damage was recorded.", st["small"]))

    photos = _pdf_photos(db, s)
    if photos:
        story.append(Paragraph("Photos", st["h"]))
        rows = [photos[i : i + 3] for i in range(0, len(photos), 3)]
        rows[-1] += [""] * (3 - len(rows[-1]))
        t = Table(rows, colWidths=[57 * mm] * 3)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.4, LINE)]))
        story.append(t)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"Plot {prop.code} · {period}",
        author="GreenPlot",
    )
    foot = _footer(f"Plot {prop.code} · {period} · generated {fmt(utcnow())}")
    doc.build(story, onFirstPage=foot, onLaterPages=foot)
    return buf.getvalue()


def fmt_date(iso: str | None) -> str:
    return f"{date.fromisoformat(iso):%d %b %Y}" if iso else "—"


def _pdf_photos(db: Session, s: dict) -> list:
    task_ids = [uuid.UUID(v["task_id"]) for v in s["visits"]]
    if not task_ids:
        return []
    storage = get_storage()
    out = []
    for e in db.scalars(
        select(MaintenanceEvidence)
        .where(
            MaintenanceEvidence.maintenance_id.in_(task_ids),
            MaintenanceEvidence.status == "active",
            MaintenanceEvidence.evidence_type == EvidenceType.AFTER_PHOTO,
        )
        .order_by(MaintenanceEvidence.uploaded_at.desc())
        .limit(MAX_PDF_PHOTOS)
    ):
        m = e.media
        if not (m and m.thumbnail_key and m.status == MediaStatus.READY):
            continue
        try:
            out.append(Image(io.BytesIO(storage.get(m.thumbnail_key)), width=54 * mm, height=40 * mm, kind="proportional"))
        except Exception:  # a missing thumbnail must not stop the report
            log.warning("thumbnail %s unavailable", m.thumbnail_key)
    return out


def report_url(report: PlotReport) -> str:
    return owner_contact.app_link(f"/api/v1/public/plot-reports/{owner_contact.link_token(TOKEN_KIND, report.id, LINK_DAYS)}")


def generate(db: Session, actor: Actor | None, prop: Property, period_start: date, send: bool = True) -> PlotReport:
    """Build (or rebuild) the report for the month containing period_start, store the PDF, and send it."""
    start, end = month_bounds(period_start)
    report = db.scalar(select(PlotReport).where(PlotReport.property_id == prop.id, PlotReport.period_start == start))
    if report is None:
        report = PlotReport(tenant_id=prop.tenant_id, property_id=prop.id, period_start=start, period_end=end, channels=[])
        db.add(report)
        db.flush()
    report.summary = build_summary(db, prop, start, end)
    key = f"{prop.tenant_id}/plot_report/{prop.id}/{start:%Y-%m}.pdf"
    get_storage().put(key, report_pdf(db, prop, report), "application/pdf")
    report.storage_key = key
    if send:
        url = report_url(report)
        title = f"Plot {prop.code}: {start:%B} report"
        body = f"{summary_line(report.summary)} Full report: {url}"
        report.channels = owner_contact.send(db, prop, "plot_report", title, body, "plot_report", report.id, url)
        report.sent_at = utcnow()
    audit.record(
        db,
        actor,
        "plot_report.generated",
        "property",
        prop.id,
        new={"period": f"{start:%Y-%m}", "sent": send, "channels": report.channels},
        tenant_id=prop.tenant_id,
    )
    return report


def send_monthly(db: Session, today: date | None = None) -> int:
    """Last month's report for every plot with an owner, once."""
    today = today or datetime.now(IST).date()
    start, end = month_bounds(add_months(today.replace(day=1), -1))
    _, created_before = _utc_range(start, end)
    has_resident_owner = (
        select(Resident.id)
        .where(
            Resident.property_id == Property.id, Resident.relation == "owner", Resident.user_id.is_not(None), Resident.deleted_at.is_(None)
        )
        .exists()
    )
    already = (
        select(PlotReport.id)
        .where(PlotReport.property_id == Property.id, PlotReport.period_start == start, PlotReport.sent_at.is_not(None))
        .exists()
    )
    stmt = (
        select(Property)
        .join(Tenant, Tenant.id == Property.tenant_id)
        .where(
            Tenant.status == "active",
            Property.deleted_at.is_(None),
            Property.created_at < created_before,
            or_(
                Property.owner_user_id.is_not(None),
                Property.owner_phone.is_not(None),
                Property.owner_email.is_not(None),
                has_resident_owner,
            ),
            ~already,
        )
    )
    n = 0
    for prop in db.scalars(stmt):
        if not tenant_setting(db, prop.tenant_id, "plot_report_enabled", True):
            continue
        generate(db, None, prop, start)
        n += 1
    return n
