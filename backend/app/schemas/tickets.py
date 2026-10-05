import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import CommentVisibility, EvidenceType, TicketPriority
from app.schemas.common import ORM, GeoPoint, Stamped


class TicketIn(BaseModel):
    category: str = Field(min_length=2, max_length=60, description="Category code or id")
    subcategory: str | None = Field(None, max_length=100)
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=3, max_length=5000)
    priority: TicketPriority | None = None
    property_id: uuid.UUID | None = None
    location: str | None = Field(None, max_length=300)
    preferred_time: str | None = Field(None, max_length=120)
    contact_phone: str | None = Field(None, max_length=30)
    customer_id: uuid.UUID | None = None
    source: str | None = Field(None, pattern="^(portal|admin|phone|whatsapp|email|walk_in|offline)$")


class TicketUpdate(BaseModel):
    category: str | None = Field(None, min_length=2, max_length=60)
    subcategory: str | None = Field(None, max_length=100)
    title: str | None = Field(None, min_length=3, max_length=300)
    description: str | None = Field(None, min_length=3, max_length=5000)
    priority: TicketPriority | None = None
    property_id: uuid.UUID | None = None
    location: str | None = Field(None, max_length=300)
    preferred_time: str | None = Field(None, max_length=120)
    contact_phone: str | None = Field(None, max_length=30)


class TicketAssignIn(BaseModel):
    staff_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    due_at: datetime | None = None
    notes: str | None = Field(None, max_length=2000)
    reason: str | None = Field(None, max_length=2000, description="Required when reassigning")


class TicketRejectIn(BaseModel):
    reason_code: str = Field(pattern="^(wrong_category|outside_service_area|no_availability|equipment_unavailable|other)$")
    reason: str = Field(min_length=3, max_length=2000)


class TicketCompleteIn(GeoPoint):
    work_notes: str | None = Field(None, max_length=10000)
    outcome: str | None = Field(None, max_length=5000)


class TicketVerifyIn(BaseModel):
    decision: str = Field(pattern="^(approve|rework)$")
    comment: str | None = Field(None, max_length=4000)


class ResolutionIn(BaseModel):
    resolution: str = Field(min_length=3, max_length=5000)


class TicketCloseIn(BaseModel):
    note: str | None = Field(None, max_length=2000)


class TicketStatusIn(BaseModel):
    action: str = Field(pattern="^(hold|wait|resume|cancel|reject)$")
    reason: str | None = Field(None, max_length=2000)


class FeedbackIn(BaseModel):
    outcome: str | None = Field(None, pattern="^(resolved|still_issue)$")
    rating: int | None = Field(None, ge=1, le=5)
    comment: str | None = Field(None, max_length=2000)


class TicketCommentIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    visibility: CommentVisibility = CommentVisibility.CUSTOMER


class TicketEvidenceIn(BaseModel):
    media_id: uuid.UUID
    evidence_type: EvidenceType = EvidenceType.PHOTO
    caption: str | None = Field(None, max_length=300)


class CategoryIn(BaseModel):
    code: str | None = Field(None, pattern="^[a-z0-9_]{2,40}$")
    name: str | None = Field(None, min_length=2, max_length=100)
    subcategories: list[str] | None = None
    default_priority: TicketPriority | None = None
    task_category: str | None = None
    preferred_vendor_type: str | None = Field(None, max_length=40)
    response_sla_minutes: int | None = Field(None, ge=1, le=60 * 24 * 60)
    resolution_sla_minutes: int | None = Field(None, ge=1, le=60 * 24 * 90)
    customer_sets_priority: bool | None = None
    is_active: bool | None = None
    position: int | None = None


class CategoryOut(Stamped):
    code: str
    name: str
    subcategories: list[str]
    default_priority: str
    task_category: str
    preferred_vendor_type: str | None
    response_sla_minutes: int | None
    resolution_sla_minutes: int | None
    customer_sets_priority: bool
    is_active: bool
    position: int
    # effective SLA for the default priority
    effective_response_minutes: int | None = None
    effective_resolution_minutes: int | None = None


class SlaOut(BaseModel):
    response_due_at: datetime
    resolution_due_at: datetime
    first_response_at: datetime | None
    resolved_at: datetime | None
    response_breached: bool
    resolution_breached: bool
    escalation_level: int
    state: str | None = None


class TicketSummary(Stamped):
    number: str
    title: str
    category_id: uuid.UUID
    category_code: str | None = None
    category_name: str | None = None
    subcategory: str | None
    priority: str
    status: str
    source: str
    property_id: uuid.UUID | None
    property_label: str | None = None
    customer_id: uuid.UUID
    customer_name: str | None = None
    assigned_to_type: str | None
    assigned_to_id: uuid.UUID | None
    assignee_name: str | None = None
    maintenance_task_id: uuid.UUID | None
    due_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    reopen_count: int
    rating: int | None
    sla_state: str | None = None


class TicketCommentOut(ORM):
    id: uuid.UUID
    author_id: uuid.UUID | None
    author_name: str | None = None
    author_role: str | None = None
    comment_type: str
    visibility: str
    message: str
    created_at: datetime


class AttachmentOut(BaseModel):
    id: uuid.UUID
    media_id: uuid.UUID
    source: str  # ticket (customer/office attachment) or work (proof of work)
    evidence_type: str
    caption: str | None = None
    uploaded_by_name: str | None = None
    uploaded_at: datetime | None = None
    content_type: str | None = None
    filename: str | None = None
    sha256: str | None = None
    url: str | None = None
    thumbnail_url: str | None = None


class AssignmentOut(ORM):
    id: uuid.UUID
    assignee_type: str
    assignee_id: uuid.UUID
    assignee_name: str | None = None
    maintenance_task_id: uuid.UUID | None
    assigned_by: uuid.UUID | None
    assigned_by_name: str | None = None
    assigned_at: datetime
    due_at: datetime | None
    notes: str | None
    accepted_at: datetime | None
    rejected_at: datetime | None
    rejection_reason: str | None
    unassigned_at: datetime | None
    unassign_reason: str | None


class TimelineItem(BaseModel):
    at: datetime
    kind: str  # status, assignment, comment, evidence, notification, feedback
    title: str
    detail: str | None = None
    actor_name: str | None = None
    status: str | None = None


class WorkOrderOut(BaseModel):
    id: uuid.UUID
    number: str
    status: str
    category: str
    assignee_name: str | None = None
    rework_count: int
    due_at: datetime | None
    completed_at: datetime | None
    approved_at: datetime | None
    missing: list[str] = []
    pending_checklist: list[str] = []
    checklist_total: int = 0
    checklist_done: int = 0
    evidence_count: int = 0
    materials_count: int = 0


class TicketDetail(TicketSummary):
    description: str
    location: str | None
    preferred_time: str | None
    contact_phone: str | None
    created_by: uuid.UUID
    first_response_at: datetime | None
    assigned_at: datetime | None
    accepted_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    verified_at: datetime | None
    reopened_at: datetime | None
    rework_count: int
    resolution: str | None
    feedback: str | None
    feedback_at: datetime | None
    customer_confirmation: str | None
    customer_phone: str | None = None
    assignee_phone: str | None = None
    sla: SlaOut | None = None
    work_order: WorkOrderOut | None = None
    work_orders: list[WorkOrderOut] = []
    comments: list[TicketCommentOut] = []
    attachments: list[AttachmentOut] = []
    timeline: list[TimelineItem] = []
    allowed_actions: list[str] = []
    comment_visibilities: list[str] = []
    reopen_until: datetime | None = None


class StatusHistoryOut(ORM):
    id: uuid.UUID
    old_status: str | None
    new_status: str
    changed_by: uuid.UUID | None
    changed_by_name: str | None = None
    reason: str | None
    created_at: datetime


class DeliveryOut(ORM):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str | None = None
    event_type: str
    channel: str
    status: str
    attempts: int
    sent_at: datetime | None
    delivered_at: datetime | None
    failure_reason: str | None
    created_at: datetime
