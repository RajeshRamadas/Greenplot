import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORM, GeoPoint, Stamped

# ---------------------------------------------------------------- visitors & vehicles


class VisitorIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(None, max_length=30)
    purpose: str = Field(min_length=2, max_length=200)
    property_id: uuid.UUID | None = None
    host_name: str | None = None
    vehicle_number: str | None = Field(None, max_length=20)
    photo_media_id: uuid.UUID | None = None
    expected_at: datetime | None = None
    check_in_now: bool = True


class VisitorDecisionIn(BaseModel):
    approve: bool


class VisitorOut(Stamped):
    name: str
    phone: str | None
    purpose: str
    property_id: uuid.UUID | None
    host_name: str | None
    vehicle_number: str | None
    photo_media_id: uuid.UUID | None
    status: str
    pre_approved: bool
    expected_at: datetime | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    entry_at: datetime | None
    exit_at: datetime | None
    guard_id: uuid.UUID | None
    property_label: str | None = None


class VehicleIn(BaseModel):
    number: str = Field(min_length=4, max_length=20)
    property_id: uuid.UUID | None = None
    owner_name: str | None = None
    vehicle_type: str = Field("car", pattern="^(car|bike|truck|van|other)$")
    make_model: str | None = None
    photo_media_id: uuid.UUID | None = None


class VehicleOut(Stamped):
    number: str
    property_id: uuid.UUID | None
    owner_name: str | None
    vehicle_type: str
    make_model: str | None
    photo_media_id: uuid.UUID | None


class VehicleLogIn(BaseModel):
    vehicle_number: str = Field(min_length=4, max_length=20)
    direction: str = Field(pattern="^(in|out)$")
    visitor_id: uuid.UUID | None = None
    photo_media_id: uuid.UUID | None = None
    notes: str | None = Field(None, max_length=300)
    at: datetime | None = None


class VehicleLogOut(Stamped):
    vehicle_number: str
    vehicle_id: uuid.UUID | None
    visitor_id: uuid.UUID | None
    is_visitor: bool
    direction: str
    at: datetime
    guard_id: uuid.UUID
    photo_media_id: uuid.UUID | None
    notes: str | None


# ---------------------------------------------------------------- patrol


class CheckpointIn(BaseModel):
    name: str
    position: int = 0
    qr_code: str | None = None
    nfc_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class RouteIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str | None = None
    checkpoints: list[CheckpointIn] = []


class CheckpointOut(ORM):
    id: uuid.UUID
    name: str
    position: int
    qr_code: str
    nfc_id: str | None
    latitude: float | None
    longitude: float | None


class RouteOut(Stamped):
    name: str
    description: str | None
    is_active: bool
    checkpoints: list[CheckpointOut] = []


class PatrolScanIn(GeoPoint):
    code: str
    method: str = Field("qr", pattern="^(qr|nfc|manual)$")
    photo_media_id: uuid.UUID | None = None
    exception: str | None = Field(None, max_length=2000)
    scanned_at: datetime | None = None


class PatrolScanOut(ORM):
    id: uuid.UUID
    checkpoint_id: uuid.UUID
    scanned_at: datetime
    method: str
    latitude: float | None
    longitude: float | None
    photo_media_id: uuid.UUID | None
    exception: str | None


class PatrolRunOut(Stamped):
    route_id: uuid.UUID
    guard_id: uuid.UUID
    started_at: datetime
    completed_at: datetime | None
    status: str
    notes: str | None
    scans: list[PatrolScanOut] = []
    route_name: str | None = None
    guard_name: str | None = None
    checkpoints_total: int = 0


class PatrolFinishIn(BaseModel):
    notes: str | None = Field(None, max_length=2000)


# ---------------------------------------------------------------- incidents & SOS


class IncidentIn(GeoPoint):
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(None, max_length=5000)
    category: str = Field("security", pattern="^(security|fire|medical|theft|trespass|infrastructure|other)$")
    severity: str = Field("medium", pattern="^(low|medium|high|critical)$")
    property_id: uuid.UUID | None = None
    location: str | None = Field(None, max_length=300)
    occurred_at: datetime | None = None


class IncidentStatusIn(BaseModel):
    status: str = Field(pattern="^(acknowledged|investigating|resolved|closed)$")
    note: str | None = Field(None, max_length=4000)
    assigned_to: uuid.UUID | None = None


class IncidentUpdateOut(ORM):
    id: uuid.UUID
    author_id: uuid.UUID
    author_name: str | None = None
    body: str
    status_change: str | None
    created_at: datetime


class IncidentOut(Stamped):
    number: str
    title: str
    description: str | None
    category: str
    severity: str
    status: str
    property_id: uuid.UUID | None
    location: str | None
    latitude: float | None
    longitude: float | None
    occurred_at: datetime
    reported_by: uuid.UUID
    assigned_to: uuid.UUID | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    resolution: str | None
    sos_id: uuid.UUID | None
    updates: list[IncidentUpdateOut] | None = None
    reported_by_name: str | None = None


class SosIn(GeoPoint):
    property_id: uuid.UUID | None = None
    message: str | None = Field(None, max_length=1000)


class SosActionIn(BaseModel):
    action: str = Field(pattern="^(acknowledge|resolve|false_alarm)$")
    note: str | None = None


class SosOut(Stamped):
    raised_by: uuid.UUID
    property_id: uuid.UUID | None
    latitude: float | None
    longitude: float | None
    message: str | None
    status: str
    escalation_level: int
    escalated_at: datetime | None
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    incident_id: uuid.UUID | None
    raised_by_name: str | None = None


# ---------------------------------------------------------------- billing


class PlanIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    basis: str = Field(pattern="^(per_plot|per_unit|per_sqft|fixed|custom)$")
    rate: float = Field(ge=0)
    frequency_months: int = Field(1, ge=1, le=12)
    due_days: int = Field(15, ge=0, le=90)
    late_fee: float | None = Field(None, ge=0)
    custom_amounts: dict[str, float] = {}
    is_active: bool = True


class PlanOut(Stamped):
    name: str
    basis: str
    rate: float
    frequency_months: int
    due_days: int
    late_fee: float | None
    custom_amounts: dict
    is_active: bool


class GenerateIn(BaseModel):
    plan_id: uuid.UUID
    period_start: date
    property_ids: list[uuid.UUID] | None = None


class InvoiceIn(BaseModel):
    property_id: uuid.UUID
    description: str = Field(min_length=2, max_length=300)
    amount: float = Field(gt=0)
    due_date: date
    period_start: date | None = None
    period_end: date | None = None


class InvoiceOut(Stamped):
    number: str
    property_id: uuid.UUID
    plan_id: uuid.UUID | None
    description: str
    period_start: date | None
    period_end: date | None
    amount: float
    amount_paid: float
    due_date: date
    status: str
    property_label: str | None = None
    overdue: bool = False


class PaymentCreateIn(BaseModel):
    invoice_id: uuid.UUID
    amount: float | None = Field(None, gt=0)


class PaymentRecordIn(BaseModel):
    invoice_id: uuid.UUID
    amount: float = Field(gt=0)
    method: str = Field(pattern="^(cash|upi|cheque|bank_transfer|online)$")
    reference: str | None = Field(None, max_length=100)
    paid_at: datetime | None = None


class PaymentOut(Stamped):
    invoice_id: uuid.UUID
    property_id: uuid.UUID
    amount: float
    method: str
    provider: str | None
    provider_order_id: str | None
    provider_payment_id: str | None
    status: str
    receipt_number: str | None
    paid_at: datetime | None
    reference: str | None
    reconciled_at: datetime | None
    checkout: dict | None = None


class ExpenseIn(BaseModel):
    category: str = Field(min_length=2, max_length=40)
    amount: float = Field(gt=0)
    spent_on: date
    description: str | None = None
    vendor_id: uuid.UUID | None = None
    maintenance_task_id: uuid.UUID | None = None


class ExpenseOut(Stamped):
    category: str
    amount: float
    spent_on: date
    description: str | None
    vendor_id: uuid.UUID | None
    maintenance_task_id: uuid.UUID | None
    recorded_by: uuid.UUID


# ---------------------------------------------------------------- communication


class NoticeIn(BaseModel):
    kind: str = Field("announcement", pattern="^(announcement|notice|alert|event|outage)$")
    title: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=1, max_length=10000)
    audience: str = Field("all", pattern="^(all|residents|staff|guards)$")
    channels: list[str] = ["in_app"]
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    pinned: bool = False


class NoticeOut(Stamped):
    kind: str
    title: str
    body: str
    audience: str
    channels: list[str]
    starts_at: datetime | None
    ends_at: datetime | None
    pinned: bool
    published_by: uuid.UUID
    published_at: datetime


class NotificationOut(ORM):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    channels: list[str]
    read_at: datetime | None
    created_at: datetime


class PushSubscriptionIn(BaseModel):
    endpoint: str
    keys: dict[str, str] = {}


# ---------------------------------------------------------------- audit, sync, search


class AuditOut(ORM):
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    actor_role: str | None
    actor_name: str | None = None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    timestamp: datetime
    old_value: dict | None
    new_value: dict | None
    ip: str | None
    user_agent: str | None


class SyncOpIn(BaseModel):
    client_op_id: str = Field(min_length=8, max_length=80)
    entity: str
    operation: str
    payload: dict[str, Any] = {}
    client_timestamp: datetime | None = None


class SyncIn(BaseModel):
    device_id: str | None = Field(None, max_length=100)
    operations: list[SyncOpIn] = Field(max_length=200)


class SyncResult(BaseModel):
    client_op_id: str
    status: str
    result: dict | None = None
    error: str | None = None


class SyncOut(BaseModel):
    results: list[SyncResult]
    server_time: datetime


class SearchHit(BaseModel):
    type: str
    id: uuid.UUID
    number: str | None
    title: str
    status: str | None
    category: str | None = None
    property_id: uuid.UUID | None = None
    property_label: str | None = None
    date: datetime | None = None


class SearchOut(BaseModel):
    query: str | None
    interpreted: dict
    total: int
    items: list[SearchHit]
