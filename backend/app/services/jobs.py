"""Background jobs: recurring schedules, due/overdue reminders, SOS escalation,
dues reminders, media retention, ticket SLA escalation and auto-close, and
notification retries. Run by app.worker or the in-process loop."""

import logging
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, MaintenanceSchedule, MaintenanceTask, Media, SosAlert, Tenant
from app.models.base import utcnow
from app.models.enums import MediaStatus, Role, SosStatus
from app.services import audit, billing, notifications
from app.services import maintenance as msvc
from app.services import tickets as tickets_svc
from app.services.storage import get_storage

log = logging.getLogger("greenplot.jobs")


def generate_scheduled_tasks(db: Session, tenant_id: uuid.UUID | None = None, today: date | None = None) -> list[MaintenanceTask]:
    today = today or date.today()
    stmt = select(MaintenanceSchedule).where(
        MaintenanceSchedule.is_active.is_(True), MaintenanceSchedule.deleted_at.is_(None), MaintenanceSchedule.next_run_on <= today
    )
    if tenant_id:
        stmt = stmt.where(MaintenanceSchedule.tenant_id == tenant_id)
    created = []
    for s in db.scalars(stmt):
        while s.next_run_on <= today:
            run_day = s.next_run_on
            start = datetime.combine(run_day, datetime.min.time()).replace(tzinfo=utcnow().tzinfo) + timedelta(
                hours=3, minutes=30
            )  # 09:00 IST
            task = msvc.create_task(
                db,
                None,
                s.tenant_id,
                dict(
                    title=f"{s.title} · {run_day:%d %b}",
                    description=s.description,
                    category=s.category,
                    priority=s.priority,
                    property_id=s.property_id,
                    asset_id=s.asset_id,
                    location_note=s.location_note,
                    schedule_id=s.id,
                    source="schedule",
                    due_at=start + timedelta(hours=s.due_after_hours),
                    checklist_template_id=s.checklist_template_id,
                    assigned_staff_id=s.assigned_staff_id,
                    vendor_id=s.vendor_id,
                ),
            )
            created.append(task)
            s.next_run_on = run_day + timedelta(days=s.interval_days)
        s.last_generated_at = utcnow()
    return created


def remind_due_and_overdue(db: Session) -> int:
    now = utcnow()
    open_states = [x.value for x in msvc.OPEN_STATES if x != "completed"]
    n = 0
    for t in db.scalars(
        select(MaintenanceTask).where(
            MaintenanceTask.status.in_(open_states), MaintenanceTask.due_at < now, MaintenanceTask.overdue_notified_at.is_(None)
        )
    ):
        recipients = [t.assigned_staff_id, t.supervisor_id, *notifications.vendor_users(db, t.tenant_id, t.vendor_id)]
        recipients += notifications.managers(db, t.tenant_id) if not t.supervisor_id else []
        notifications.notify(db, t.tenant_id, recipients, "task_overdue", f"Overdue: {t.number}", t.title, "maintenance_task", t.id)
        t.overdue_notified_at = now
        n += 1
    soon = now + timedelta(hours=4)
    for t in db.scalars(
        select(MaintenanceTask).where(MaintenanceTask.status.in_(["assigned", "accepted"]), MaintenanceTask.due_at.between(now, soon))
    ):
        already = db.scalar(select(AuditLog.id).where(AuditLog.entity_id == t.id, AuditLog.action == "maintenance.due_reminder"))
        if not already:
            notifications.notify(
                db, t.tenant_id, [t.assigned_staff_id], "task_due", f"Due soon: {t.number}", t.title, "maintenance_task", t.id
            )
            audit.record(db, None, "maintenance.due_reminder", "maintenance_task", t.id, tenant_id=t.tenant_id)
    return n


def escalate_sos(db: Session) -> int:
    """Unacknowledged SOS escalates to the layout admins and then re-alerts everyone."""
    now = utcnow()
    n = 0
    for s in db.scalars(select(SosAlert).where(SosAlert.status == SosStatus.ACTIVE)):
        minutes = msvc.tenant_setting(db, s.tenant_id, "sos_escalation_minutes", 3)
        last = s.escalated_at or s.created_at
        if now - last < timedelta(minutes=minutes):
            continue
        s.escalation_level += 1
        s.escalated_at = now
        roles = [Role.LAYOUT_ADMIN, Role.SUPERVISOR] if s.escalation_level == 1 else [Role.LAYOUT_ADMIN, Role.SUPERVISOR, Role.GUARD]
        notifications.notify(
            db,
            s.tenant_id,
            notifications.users_with_roles(db, s.tenant_id, roles),
            "sos",
            f"ESCALATED SOS (level {s.escalation_level}) — no response yet",
            s.message,
            "sos",
            s.id,
            channels=["in_app", "push", "sms", "whatsapp"],
        )
        audit.record(db, None, "sos.escalated", "sos", s.id, new={"level": s.escalation_level}, tenant_id=s.tenant_id)
        n += 1
    return n


def purge_expired_media(db: Session, today: date | None = None) -> int:
    """Delete stored objects past retention. Metadata and hashes are kept for the audit trail."""
    today = today or date.today()
    storage = get_storage()
    n = 0
    stmt = select(Media).where(
        Media.retention_until < today,
        Media.legal_hold.is_(False),
        Media.status.in_([MediaStatus.READY, MediaStatus.DELETED, MediaStatus.FAILED]),
    )
    for m in db.scalars(stmt):
        for key in (m.storage_key, m.thumbnail_key):
            if key:
                try:
                    storage.delete(key)
                except Exception:  # pragma: no cover
                    log.exception("failed to delete %s", key)
        m.status = MediaStatus.DELETED
        m.deleted_at = m.deleted_at or utcnow()
        m.delete_reason = m.delete_reason or "retention_expired"
        audit.record(
            db,
            None,
            "media.retention_purged",
            m.entity_type,
            m.entity_id,
            old={"media_id": m.id, "sha256": m.sha256},
            tenant_id=m.tenant_id,
        )
        n += 1
    return n


def run_all(db: Session) -> dict:
    result = {}
    result["scheduled_tasks"] = len(generate_scheduled_tasks(db))
    result["overdue_notified"] = remind_due_and_overdue(db)
    result["sos_escalated"] = escalate_sos(db)
    result["dues_reminded"] = billing.refresh_overdue(db)
    result["media_purged"] = purge_expired_media(db)
    result["ticket_sla_alerts"] = tickets_svc.run_sla_checks(db)
    result["tickets_auto_closed"] = tickets_svc.auto_close_resolved(db)
    result["notification_retries"] = notifications.retry_failed_deliveries(db)
    db.commit()
    return result


def active_tenants(db: Session) -> list[uuid.UUID]:
    return list(db.scalars(select(Tenant.id).where(Tenant.status == "active")))
