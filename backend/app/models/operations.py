import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Model, SoftDelete, TenantModel, UTCDateTime

# --------------------------------------------------------------------------- security & access (§18)


class Visitor(TenantModel):
    __tablename__ = "visitors"

    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    purpose: Mapped[str] = mapped_column(String(200))
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id"), index=True, nullable=True)
    host_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    vehicle_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    photo_media_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("media.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending_approval", index=True)
    pre_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    entry_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    exit_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    guard_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))


class Vehicle(TenantModel, SoftDelete):
    __tablename__ = "vehicles"
    __table_args__ = (UniqueConstraint("tenant_id", "number"),)

    number: Mapped[str] = mapped_column(String(20), index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id"), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    vehicle_type: Mapped[str] = mapped_column(String(20), default="car")
    make_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    photo_media_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("media.id"), nullable=True)


class VehicleLog(TenantModel):
    __tablename__ = "vehicle_logs"

    vehicle_number: Mapped[str] = mapped_column(String(20), index=True)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("vehicles.id"), nullable=True)
    visitor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("visitors.id"), nullable=True)
    is_visitor: Mapped[bool] = mapped_column(Boolean, default=False)
    direction: Mapped[str] = mapped_column(String(5))  # in / out
    at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    guard_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    photo_media_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("media.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)


class PatrolRoute(TenantModel, SoftDelete):
    __tablename__ = "patrol_routes"

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PatrolCheckpoint(TenantModel):
    __tablename__ = "patrol_checkpoints"

    route_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patrol_routes.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer, default=0)
    qr_code: Mapped[str] = mapped_column(String(120), index=True)
    nfc_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)


class PatrolRun(TenantModel):
    __tablename__ = "patrol_runs"

    route_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patrol_routes.id"), index=True)
    guard_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")  # in_progress, completed, incomplete
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PatrolScan(TenantModel):
    __tablename__ = "patrol_scans"

    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patrol_runs.id", ondelete="CASCADE"), index=True)
    checkpoint_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patrol_checkpoints.id"))
    scanned_at: Mapped[datetime] = mapped_column(UTCDateTime())
    method: Mapped[str] = mapped_column(String(10), default="qr")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    photo_media_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("media.id"), nullable=True)
    exception: Mapped[str | None] = mapped_column(Text, nullable=True)


class Incident(TenantModel, SoftDelete):
    __tablename__ = "incidents"
    __table_args__ = (UniqueConstraint("tenant_id", "number"),)

    number: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(40), default="security")  # security, fire, medical, theft, trespass, other
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id"), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    reported_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    sos_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class IncidentUpdate(TenantModel):
    __tablename__ = "incident_updates"

    incident_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    status_change: Mapped[str | None] = mapped_column(String(40), nullable=True)


class SosAlert(TenantModel):
    __tablename__ = "sos_alerts"

    raised_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id"), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    escalated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("incidents.id"), nullable=True)


# --------------------------------------------------------------------------- billing & dues (§19)


class BillingPlan(TenantModel, SoftDelete):
    __tablename__ = "billing_plans"

    name: Mapped[str] = mapped_column(String(200))
    basis: Mapped[str] = mapped_column(String(20))  # per_plot, per_unit, per_sqft, fixed, custom
    rate: Mapped[float] = mapped_column(Numeric(12, 2))
    frequency_months: Mapped[int] = mapped_column(Integer, default=1)
    due_days: Mapped[int] = mapped_column(Integer, default=15)
    late_fee: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    custom_amounts: Mapped[dict] = mapped_column(JSON, default=dict)  # property_id -> amount for custom basis
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Invoice(TenantModel, SoftDelete):
    """A due raised against a property for a billing period."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        UniqueConstraint("plan_id", "property_id", "period_start"),
    )

    number: Mapped[str] = mapped_column(String(40), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("billing_plans.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(300))
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    amount_paid: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default="unpaid", index=True)


class Payment(TenantModel):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)

    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(20))  # online, upi, cash, cheque, bank_transfer
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="created", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    receipt_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class PaymentWebhookEvent(Model):
    __tablename__ = "payment_webhook_events"

    provider: Mapped[str] = mapped_column(String(30))
    event_id: Mapped[str] = mapped_column(String(120), unique=True)
    event_type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    result: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Expense(TenantModel, SoftDelete):
    __tablename__ = "expenses"

    category: Mapped[str] = mapped_column(String(40))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    spent_on: Mapped[date] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("vendors.id"), nullable=True)
    maintenance_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("maintenance_tasks.id"), nullable=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))


# --------------------------------------------------------------------------- communication (§20, §39)


class Notice(TenantModel, SoftDelete):
    __tablename__ = "notices"

    kind: Mapped[str] = mapped_column(String(20), default="announcement")
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(String(20), default="all")  # all, residents, staff, guards
    channels: Mapped[list] = mapped_column(JSON, default=lambda: ["in_app"])
    starts_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    published_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    published_at: Mapped[datetime] = mapped_column(UTCDateTime())


class Notification(TenantModel):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    channels: Mapped[list] = mapped_column(JSON, default=list)
    delivery: Mapped[dict] = mapped_column(JSON, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class PushSubscription(TenantModel):
    __tablename__ = "push_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    keys: Mapped[dict] = mapped_column(JSON, default=dict)


# --------------------------------------------------------------------------- audit & sync (§30, §38)


class AuditLog(Model):
    __tablename__ = "audit_logs"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), index=True, nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)


class SyncOperation(TenantModel):
    """Server record of an offline-queued client operation; makes replay idempotent."""

    __tablename__ = "sync_operations"
    __table_args__ = (UniqueConstraint("user_id", "client_op_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    client_op_id: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(40))
    operation: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    client_timestamp: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
