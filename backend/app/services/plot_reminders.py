"""'Your plot is due for cleaning' reminders to owners, with a one-tap pay link.

Each recurring schedule on a plot reminds the owner once per visit, a few days
before it (tenant setting ``plot_due_reminder_days``, default 7; 0 turns it off).
Schedules that repeat more often than every 14 days are skipped so owners of
weekly jobs are not messaged every week.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invoice, MaintenanceSchedule, Property, Tenant
from app.models.enums import InvoiceStatus
from app.services import audit, owner_contact
from app.services.billing import outstanding
from app.services.maintenance import tenant_setting

MIN_INTERVAL_DAYS = 14
MAX_LEAD_DAYS = 30


def _lead_days(db: Session, tenant_id: uuid.UUID) -> int:
    return max(0, min(int(tenant_setting(db, tenant_id, "plot_due_reminder_days", 7)), MAX_LEAD_DAYS))


def outstanding_invoices(db: Session, property_id: uuid.UUID) -> list[Invoice]:
    return list(
        db.scalars(
            select(Invoice)
            .where(
                Invoice.property_id == property_id,
                Invoice.status.in_([InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL]),
                Invoice.deleted_at.is_(None),
            )
            .order_by(Invoice.due_date)
        )
    )


def reminder_text(db: Session, s: MaintenanceSchedule, prop: Property) -> tuple[str, str, str | None]:
    what = s.category.replace("_", " ")
    title = f"Plot {prop.code} is due for {what} on {s.next_run_on:%d %b}"
    body = f"{s.title}: our team visits on {s.next_run_on:%a %d %b}."
    invoices = outstanding_invoices(db, prop.id)
    if invoices:
        total = sum((outstanding(i) for i in invoices), Decimal("0"))
        link = owner_contact.pay_link(db, invoices[0])
        more = f" across {len(invoices)} bills" if len(invoices) > 1 else ""
        return title, f"{body} ₹{total} is due{more}. Pay in one tap: {link}", link
    return title, f"{body} Nothing to pay right now.", None


def remind_plot_due(db: Session, today: date | None = None) -> int:
    today = today or date.today()
    stmt = (
        select(MaintenanceSchedule)
        .join(Tenant, Tenant.id == MaintenanceSchedule.tenant_id)
        .where(
            Tenant.status == "active",
            MaintenanceSchedule.is_active.is_(True),
            MaintenanceSchedule.deleted_at.is_(None),
            MaintenanceSchedule.property_id.is_not(None),
            MaintenanceSchedule.interval_days >= MIN_INTERVAL_DAYS,
            MaintenanceSchedule.next_run_on > today,
            MaintenanceSchedule.next_run_on <= today + timedelta(days=MAX_LEAD_DAYS),
        )
    )
    n = 0
    for s in db.scalars(stmt):
        if s.owner_reminded_for == s.next_run_on:
            continue
        lead = _lead_days(db, s.tenant_id)
        if not lead or s.next_run_on > today + timedelta(days=lead):
            continue
        prop = db.get(Property, s.property_id)
        if prop is None or prop.deleted_at is not None or not owner_contact.has_owner_contact(db, prop):
            continue
        title, body, link = reminder_text(db, s, prop)
        channels = owner_contact.send(db, prop, "plot_due", title, body, "maintenance_schedule", s.id, link)
        s.owner_reminded_for = s.next_run_on
        audit.record(
            db,
            None,
            "schedule.owner_reminded",
            "maintenance_schedule",
            s.id,
            new={"run_on": s.next_run_on, "channels": channels},
            tenant_id=s.tenant_id,
        )
        n += 1
    return n
