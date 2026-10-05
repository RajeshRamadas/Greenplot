import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SoftDelete, TenantModel, UTCDateTime


class ChecklistTemplate(TenantModel, SoftDelete):
    __tablename__ = "checklist_templates"

    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40), index=True)
    items: Mapped[list] = mapped_column(JSON, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class EvidencePolicy(TenantModel):
    """Configurable evidence requirements per task category (requirements §10)."""

    __tablename__ = "evidence_policies"
    __table_args__ = (UniqueConstraint("tenant_id", "category"),)

    category: Mapped[str] = mapped_column(String(40))
    before_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    after_photo: Mapped[bool] = mapped_column(Boolean, default=True)
    checklist: Mapped[bool] = mapped_column(Boolean, default=True)
    gps: Mapped[bool] = mapped_column(Boolean, default=False)
    video: Mapped[bool] = mapped_column(Boolean, default=False)
    materials: Mapped[bool] = mapped_column(Boolean, default=False)
    invoice: Mapped[bool] = mapped_column(Boolean, default=False)
    qr_scan: Mapped[bool] = mapped_column(Boolean, default=False)
    supervisor_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    resident_acknowledgement: Mapped[bool] = mapped_column(Boolean, default=False)


class MaintenanceTask(TenantModel, SoftDelete):
    __tablename__ = "maintenance_tasks"
    __table_args__ = (UniqueConstraint("tenant_id", "number"),)

    number: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="created", index=True)
    source: Mapped[str] = mapped_column(String(30), default="manual")  # manual, complaint, ticket, inspection, schedule, asset_scan

    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id"), index=True, nullable=True)
    layout_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("layouts.id"), nullable=True)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("assets.id"), index=True, nullable=True)
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("complaints.id"), nullable=True)
    # Plain reference (no FK) to avoid a tickets <-> maintenance_tasks cycle, like Complaint.maintenance_task_id.
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    inspection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("inspections.id"), nullable=True)
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("maintenance_schedules.id"), nullable=True)
    location_note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    assigned_staff_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), index=True, nullable=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("vendors.id"), index=True, nullable=True)
    supervisor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)

    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True, nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    overdue_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    start_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    complete_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    complete_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    asset_scanned_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    asset_scan_method: Mapped[str | None] = mapped_column(String(10), nullable=True)  # qr, nfc, manual

    work_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_found: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)

    review_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)  # approved, rework, rejected
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    rework_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    resident_ack_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    resident_ack_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    resident_ack_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    checklist = relationship("MaintenanceChecklistItem", order_by="MaintenanceChecklistItem.position", cascade="all, delete-orphan")
    materials = relationship("MaintenanceMaterial", cascade="all, delete-orphan")


class MaintenanceChecklistItem(TenantModel):
    __tablename__ = "maintenance_checklist_items"

    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("maintenance_tasks.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class MaintenanceMaterial(TenantModel):
    __tablename__ = "maintenance_materials"

    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("maintenance_tasks.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[float] = mapped_column(Numeric(12, 3))
    unit: Mapped[str] = mapped_column(String(20))
    unit_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)


class MaintenanceEvidence(TenantModel):
    """Links a media object to a maintenance task as proof (requirements §29 evidence fields)."""

    __tablename__ = "maintenance_evidence"

    maintenance_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("maintenance_tasks.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), default="maintenance_task")
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    media_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("media.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(30), index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    captured_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime())
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, replaced, deleted
    rework_round: Mapped[int] = mapped_column(Integer, default=0)
    caption: Mapped[str | None] = mapped_column(String(300), nullable=True)

    media = relationship("Media", lazy="joined")


class EvidenceException(TenantModel):
    """Worker-declared reason why required evidence could not be captured (requirements §10)."""

    __tablename__ = "evidence_exceptions"

    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("maintenance_tasks.id", ondelete="CASCADE"), index=True)
    requirement: Mapped[str] = mapped_column(String(30))
    reason_code: Mapped[str] = mapped_column(String(40))  # camera_unavailable, no_gps_signal, not_applicable, privacy, other
    reason: Mapped[str] = mapped_column(Text)
    raised_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    review_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, accepted, rejected
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class MaintenanceComment(TenantModel):
    __tablename__ = "maintenance_comments"

    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("maintenance_tasks.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="comment")  # comment, review


class MaintenanceSchedule(TenantModel, SoftDelete):
    """Recurring cleaning / gardening / preventive maintenance (requirements §14-15)."""

    __tablename__ = "maintenance_schedules"

    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(40))
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id"), nullable=True)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("assets.id"), nullable=True)
    location_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    checklist_template_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("checklist_templates.id"), nullable=True)
    interval_days: Mapped[int] = mapped_column(Integer, default=7)
    due_after_hours: Mapped[int] = mapped_column(Integer, default=24)
    next_run_on: Mapped[date] = mapped_column(Date)
    assigned_staff_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("vendors.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_generated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Media(TenantModel):
    """Private object-storage media with integrity metadata (requirements §12-13)."""

    __tablename__ = "media"
    __table_args__ = (UniqueConstraint("uploaded_by", "client_ref"),)

    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    evidence_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(20), nullable=True)  # before, during, after, review
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    client_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(400), unique=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100))
    original_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    replaces_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("media.id"), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("media.id"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    delete_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retention_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    scan_status: Mapped[str] = mapped_column(String(20), default="not_scanned")  # not_scanned, clean, infected


class Complaint(TenantModel, SoftDelete):
    __tablename__ = "complaints"
    __table_args__ = (UniqueConstraint("tenant_id", "number"),)

    number: Mapped[str] = mapped_column(String(40), index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id"), index=True, nullable=True)
    category: Mapped[str] = mapped_column(String(40))
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    raised_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    assigned_staff_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("vendors.id"), nullable=True)
    maintenance_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)


class ComplaintComment(TenantModel):
    __tablename__ = "complaint_comments"

    complaint_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("complaints.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    internal: Mapped[bool] = mapped_column(Boolean, default=False)


class Inspection(TenantModel, SoftDelete):
    __tablename__ = "inspections"
    __table_args__ = (UniqueConstraint("tenant_id", "number"),)

    number: Mapped[str] = mapped_column(String(40), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    inspector_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    is_property_watch: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    scheduled_for: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    overall_condition: Mapped[str | None] = mapped_column(String(20), nullable=True)
    findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    items = relationship("InspectionItem", order_by="InspectionItem.position", cascade="all, delete-orphan")


class InspectionItem(TenantModel):
    __tablename__ = "inspection_items"

    inspection_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    point: Mapped[str] = mapped_column(String(40))
    condition: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("maintenance_tasks.id"), nullable=True)


__all__ = [
    "ChecklistTemplate",
    "EvidencePolicy",
    "MaintenanceTask",
    "MaintenanceChecklistItem",
    "MaintenanceMaterial",
    "MaintenanceEvidence",
    "EvidenceException",
    "MaintenanceComment",
    "MaintenanceSchedule",
    "Media",
    "Complaint",
    "ComplaintComment",
    "Inspection",
    "InspectionItem",
]
