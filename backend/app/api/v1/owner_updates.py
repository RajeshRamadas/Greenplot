"""Owner updates: job photo proof, monthly plot reports, and their public links."""

import re
import uuid
from datetime import date, datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.deps import DB, Perm
from app.core.ratelimit import limiter
from app.models import MaintenanceTask, PlotReport, Property
from app.models.enums import TaskStatus
from app.services import audit, job_proof, owner_contact, plot_reports
from app.services.access import can_view_property, get_scoped, get_task
from app.services.maintenance import tenant_setting
from app.services.reports import IST
from app.services.storage import get_storage

router = APIRouter(tags=["owner updates"])

DONE = (TaskStatus.APPROVED, TaskStatus.CLOSED)


def _public_limit(kind: str, token: str) -> None:
    if not limiter.allow(f"{kind}:{token[:32]}", 120, 3600):
        raise HTTPException(429, "Too many requests")


# ------------------------------------------------------------------ job photo proof


class ProofPhoto(BaseModel):
    url: str
    thumbnail_url: str | None
    taken_at: datetime | None


class ProofOut(BaseModel):
    number: str
    title: str
    category: str
    plot: str | None
    layout: str | None
    completed_at: datetime | None
    closed_at: datetime | None
    before: list[ProofPhoto]
    after: list[ProofPhoto]


@router.get("/public/job-proof/{token}", response_model=ProofOut)
def public_job_proof(token: str, db: DB):
    """Before/after photos of a finished job, opened from the owner's WhatsApp or email link."""
    _public_limit("proof", token)
    task_id = owner_contact.read_link_token(job_proof.TOKEN_KIND, token)
    task = db.get(MaintenanceTask, task_id) if task_id else None
    if (
        task is None
        or task.deleted_at is not None
        or task.status not in DONE
        or tenant_setting(db, task.tenant_id, "resident_evidence_visibility", "after_approval") == "none"
    ):
        raise HTTPException(404, "This link has expired or the job is no longer available")
    return job_proof.public_view(db, task)


@router.post("/maintenance/{task_id}/send-proof")
def send_proof(task_id: uuid.UUID, db: DB, actor: Perm("maintenance.review")):
    """Send (or resend) the before/after photos of a finished job to the plot owner."""
    task = get_task(db, actor, task_id)
    if task.status not in DONE:
        raise HTTPException(409, "Photo proof is sent once the job is approved")
    channels = job_proof.send_job_proof(db, actor, task)
    if channels is None:
        raise HTTPException(422, "Nothing to send: the job needs a plot with an owner and at least one after photo")
    db.commit()
    return {"channels": channels, "url": job_proof.proof_url(db, task)}


# ------------------------------------------------------------------ monthly plot reports


class PlotReportOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    period_start: date
    period_end: date
    summary: dict
    sent_at: datetime | None
    channels: list[str]

    model_config = {"from_attributes": True}


class PlotReportIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM")
    send: bool = True


def _property(db, actor, property_id: uuid.UUID) -> Property:
    if not can_view_property(db, actor, property_id):
        raise HTTPException(404, "Property not found")
    return get_scoped(db, Property, property_id, actor, "Property")


def _pdf(report: PlotReport, prop: Property) -> Response:
    try:
        pdf = get_storage().get(report.storage_key) if report.storage_key else None
    except (OSError, FileNotFoundError):
        pdf = None
    if pdf is None:
        raise HTTPException(404, "Report file not found")
    name = re.sub(r"[^A-Za-z0-9_-]", "-", f"{prop.code}-{report.period_start:%Y-%m}")
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="plot-report-{name}.pdf"'})


@router.get("/properties/{property_id}/plot-reports", response_model=list[PlotReportOut])
def list_plot_reports(property_id: uuid.UUID, db: DB, actor: Perm("properties.read")):
    _property(db, actor, property_id)
    return list(
        db.scalars(
            select(PlotReport)
            .where(PlotReport.tenant_id == actor.tenant_id, PlotReport.property_id == property_id)
            .order_by(PlotReport.period_start.desc())
        )
    )


@router.get("/properties/{property_id}/plot-reports/{report_id}/report.pdf")
def plot_report_pdf(property_id: uuid.UUID, report_id: uuid.UUID, db: DB, actor: Perm("properties.read")):
    prop = _property(db, actor, property_id)
    report = db.get(PlotReport, report_id)
    if report is None or report.property_id != prop.id:
        raise HTTPException(404, "Report not found")
    return _pdf(report, prop)


@router.post("/properties/{property_id}/plot-reports", response_model=PlotReportOut, status_code=201)
def create_plot_report(property_id: uuid.UUID, body: PlotReportIn, db: DB, actor: Perm("properties.manage")):
    """Build a month's report now (e.g. to resend it or after correcting records)."""
    prop = _property(db, actor, property_id)
    year, month = map(int, body.month.split("-"))
    if date(year, month, 1) > datetime.now(IST).date():
        raise HTTPException(422, "That month has not started yet")
    report = plot_reports.generate(db, actor, prop, date(year, month, 1), send=body.send)
    db.commit()
    return report


@router.get("/public/plot-reports/{token}")
def public_plot_report(token: str, db: DB):
    """The report PDF, opened from the owner's WhatsApp or email link."""
    _public_limit("plot-report", token)
    report_id = owner_contact.read_link_token(plot_reports.TOKEN_KIND, token)
    report = db.get(PlotReport, report_id) if report_id else None
    prop = db.get(Property, report.property_id) if report else None
    if report is None or prop is None or prop.deleted_at is not None:
        raise HTTPException(404, "This link has expired or the report is no longer available")
    audit.record(db, None, "plot_report.opened", "property", prop.id, new={"report": report.id}, tenant_id=prop.tenant_id)
    db.commit()
    return _pdf(report, prop)
