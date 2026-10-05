"""Customer ticketing & vendor service management (ticketing requirements §23).

A ticket is the customer-facing record. The work itself runs on a linked
MaintenanceTask so vendors and staff reuse the Proof of Work flow.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Model, SoftDelete, TenantModel, UTCDateTime


class TicketCategory(TenantModel, SoftDelete):
    """Configurable ticket category (§5): default priority, SLA, work type and evidence rules."""

    __tablename__ = "ticket_categories"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(100))
    subcategories: Mapped[list] = mapped_column(JSON, default=list)
    default_priority: Mapped[str] = mapped_column(String(20), default="medium")
    # Maintenance category used for the linked job; it selects the evidence policy and checklist.
    task_category: Mapped[str] = mapped_column(String(40), default="repairs")
    preferred_vendor_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    response_sla_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_sla_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_sets_priority: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class Ticket(TenantModel, SoftDelete):
    __tablename__ = "tickets"
    __table_args__ = (UniqueConstraint("tenant_id", "number"),)

    number: Mapped[str] = mapped_column(String(40), index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id"), index=True, nullable=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ticket_categories.id"), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    source: Mapped[str] = mapped_column(String(20), default="portal")  # portal, admin, phone, whatsapp, offline
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    preferred_time: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    assigned_to_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # staff, vendor
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    maintenance_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("maintenance_tasks.id"), nullable=True)
    resume_status: Mapped[str | None] = mapped_column(String(30), nullable=True)  # status to return to after hold/waiting

    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True, nullable=True)
    first_response_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)
    rework_count: Mapped[int] = mapped_column(Integer, default=0)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Customer feedback (§30)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    customer_confirmation: Mapped[str | None] = mapped_column(String(20), nullable=True)  # resolved, still_issue


class TicketComment(TenantModel):
    __tablename__ = "ticket_comments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    comment_type: Mapped[str] = mapped_column(String(20), default="comment")  # comment, question, system
    visibility: Mapped[str] = mapped_column(String(20), default="customer")  # customer, vendor, internal, supervisor
    message: Mapped[str] = mapped_column(Text)


class TicketAssignment(TenantModel):
    """Every assignment, acceptance, rejection and reassignment of a ticket (§9-10)."""

    __tablename__ = "ticket_assignments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    assignee_type: Mapped[str] = mapped_column(String(10))  # staff, vendor
    assignee_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    maintenance_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("maintenance_tasks.id"), nullable=True)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime())
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    unassigned_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    unassign_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class TicketSLA(TenantModel):
    __tablename__ = "ticket_slas"

    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tickets.id", ondelete="CASCADE"), unique=True)
    response_due_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    resolution_due_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    first_response_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    response_breached: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_breached: Mapped[bool] = mapped_column(Boolean, default=False)
    at_risk_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    breach_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)


class TicketStatusHistory(TenantModel):
    __tablename__ = "ticket_status_history"

    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    old_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str] = mapped_column(String(30))
    changed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class TicketEvidence(TenantModel):
    """Customer attachments on a ticket. Work proof lives on the linked maintenance task."""

    __tablename__ = "ticket_evidence"
    __table_args__ = (UniqueConstraint("ticket_id", "media_id"),)

    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    media_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("media.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(30), default="photo")
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    caption: Mapped[str | None] = mapped_column(String(300), nullable=True)


class NotificationDelivery(Model):
    """One row per notification per channel, so delivery is auditable (ticketing §18, §31)."""

    __tablename__ = "notification_deliveries"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    notification_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("notifications.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    channel: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True)  # stored, sent, delivered, skipped, failed
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
