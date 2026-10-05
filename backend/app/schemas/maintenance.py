import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import ChecklistStatus, EvidenceType, Priority, RequirementKey, TaskCategory
from app.schemas.common import ORM, GeoPoint, Stamped


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(None, max_length=5000)
    category: TaskCategory
    priority: Priority = Priority.MEDIUM
    property_id: uuid.UUID | None = None
    layout_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    complaint_id: uuid.UUID | None = None
    inspection_id: uuid.UUID | None = None
    location_note: str | None = Field(None, max_length=300)
    due_at: datetime | None = None
    assigned_staff_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    supervisor_id: uuid.UUID | None = None
    estimated_cost: float | None = Field(None, ge=0)
    checklist_template_id: uuid.UUID | None = None
    checklist_items: list[str] | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=300)
    description: str | None = None
    priority: Priority | None = None
    due_at: datetime | None = None
    location_note: str | None = None
    estimated_cost: float | None = Field(None, ge=0)
    supervisor_id: uuid.UUID | None = None
    # worker-editable completion record
    work_notes: str | None = Field(None, max_length=10000)
    issue_found: str | None = Field(None, max_length=5000)
    outcome: str | None = Field(None, max_length=5000)
    observations: str | None = Field(None, max_length=5000)


class AssignIn(BaseModel):
    assigned_staff_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    supervisor_id: uuid.UUID | None = None
    due_at: datetime | None = None


class StartIn(GeoPoint):
    pass


class CompleteIn(GeoPoint):
    work_notes: str | None = Field(None, max_length=10000)
    outcome: str | None = Field(None, max_length=5000)


class ReviewIn(BaseModel):
    comment: str | None = Field(None, max_length=4000)


class RejectIn(BaseModel):
    comment: str = Field(min_length=3, max_length=4000)
    decision: str = Field("rework", pattern="^(rework|rejected)$")


class ScanIn(BaseModel):
    code: str = Field(min_length=1, max_length=200)
    method: str = Field("qr", pattern="^(qr|nfc|manual)$")


class ChecklistUpdate(BaseModel):
    status: ChecklistStatus
    reason: str | None = Field(None, max_length=2000)


class ChecklistAdd(BaseModel):
    label: str = Field(min_length=2, max_length=300)


class MaterialIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=20)
    unit_cost: float | None = Field(None, ge=0)
    supplier: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=1000)


class EvidenceLinkIn(BaseModel):
    media_id: uuid.UUID
    evidence_type: EvidenceType
    caption: str | None = Field(None, max_length=300)


class ExceptionIn(BaseModel):
    requirement: RequirementKey
    reason_code: str = Field(pattern="^(camera_unavailable|no_gps_signal|not_applicable|privacy|device_issue|other)$")
    reason: str = Field(min_length=5, max_length=2000)


class AckIn(BaseModel):
    note: str | None = Field(None, max_length=2000)


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ChecklistItemOut(ORM):
    id: uuid.UUID
    position: int
    label: str
    status: str
    reason: str | None
    updated_by: uuid.UUID | None
    checked_at: datetime | None


class MaterialOut(ORM):
    id: uuid.UUID
    name: str
    quantity: float
    unit: str
    unit_cost: float | None
    supplier: str | None
    notes: str | None
    added_by: uuid.UUID | None
    created_at: datetime


class EvidenceOut(ORM):
    id: uuid.UUID
    media_id: uuid.UUID
    evidence_type: str
    uploaded_by: uuid.UUID
    uploaded_by_name: str | None = None
    captured_at: datetime | None
    uploaded_at: datetime
    latitude: float | None
    longitude: float | None
    sha256: str
    status: str
    rework_round: int
    caption: str | None
    content_type: str | None = None
    url: str | None = None
    thumbnail_url: str | None = None


class ExceptionOut(ORM):
    id: uuid.UUID
    requirement: str
    reason_code: str
    reason: str
    raised_by: uuid.UUID
    review_status: str
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime


class CommentOut(ORM):
    id: uuid.UUID
    author_id: uuid.UUID
    author_name: str | None = None
    body: str
    kind: str
    created_at: datetime


class TaskSummary(Stamped):
    number: str
    title: str
    category: str
    priority: str
    status: str
    source: str
    property_id: uuid.UUID | None
    asset_id: uuid.UUID | None
    complaint_id: uuid.UUID | None
    assigned_staff_id: uuid.UUID | None
    vendor_id: uuid.UUID | None
    supervisor_id: uuid.UUID | None
    due_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    approved_at: datetime | None
    closed_at: datetime | None
    rework_count: int
    review_decision: str | None
    overdue: bool = False
    property_label: str | None = None
    assignee_name: str | None = None
    vendor_name: str | None = None


class TaskDetail(TaskSummary):
    description: str | None
    layout_id: uuid.UUID | None
    inspection_id: uuid.UUID | None
    schedule_id: uuid.UUID | None
    location_note: str | None
    created_by: uuid.UUID | None
    assigned_by: uuid.UUID | None
    completed_by: uuid.UUID | None
    reviewed_by: uuid.UUID | None
    assigned_at: datetime | None
    accepted_at: datetime | None
    reviewed_at: datetime | None
    start_latitude: float | None
    start_longitude: float | None
    complete_latitude: float | None
    complete_longitude: float | None
    gps_accuracy_m: float | None
    asset_scanned_at: datetime | None
    asset_scan_method: str | None
    work_notes: str | None
    issue_found: str | None
    outcome: str | None
    observations: str | None
    review_comment: str | None
    estimated_cost: float | None
    resident_ack_at: datetime | None
    resident_ack_note: str | None
    checklist: list[ChecklistItemOut] = []
    materials: list[MaterialOut] = []
    evidence: list[EvidenceOut] = []
    exceptions: list[ExceptionOut] = []
    comments: list[CommentOut] = []
    proof: dict | None = None
    allowed_actions: list[str] = []
    asset_label: str | None = None
    supervisor_name: str | None = None
    completed_by_name: str | None = None
    reviewed_by_name: str | None = None
    materials_cost: float = 0


class PolicyIn(BaseModel):
    before_photo: bool | None = None
    after_photo: bool | None = None
    checklist: bool | None = None
    gps: bool | None = None
    video: bool | None = None
    materials: bool | None = None
    invoice: bool | None = None
    qr_scan: bool | None = None
    supervisor_approval: bool | None = None
    resident_acknowledgement: bool | None = None


class PolicyOut(ORM):
    category: str
    before_photo: bool
    after_photo: bool
    checklist: bool
    gps: bool
    video: bool
    materials: bool
    invoice: bool
    qr_scan: bool
    supervisor_approval: bool
    resident_acknowledgement: bool


class TemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    category: TaskCategory
    items: list[str] = Field(min_length=1)
    is_default: bool = False


class TemplateOut(Stamped):
    name: str
    category: str
    items: list[str]
    is_default: bool


class ScheduleIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str | None = None
    category: TaskCategory
    priority: Priority = Priority.MEDIUM
    property_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    location_note: str | None = None
    checklist_template_id: uuid.UUID | None = None
    interval_days: int = Field(7, ge=1, le=366)
    due_after_hours: int = Field(24, ge=1, le=24 * 31)
    next_run_on: date
    assigned_staff_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    is_active: bool = True


class ScheduleUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: Priority | None = None
    interval_days: int | None = Field(None, ge=1, le=366)
    due_after_hours: int | None = None
    next_run_on: date | None = None
    assigned_staff_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    is_active: bool | None = None


class ScheduleOut(Stamped):
    title: str
    description: str | None
    category: str
    priority: str
    property_id: uuid.UUID | None
    asset_id: uuid.UUID | None
    location_note: str | None
    checklist_template_id: uuid.UUID | None
    interval_days: int
    due_after_hours: int
    next_run_on: date
    assigned_staff_id: uuid.UUID | None
    vendor_id: uuid.UUID | None
    is_active: bool
    last_generated_at: datetime | None


# ---------------------------------------------------------------- media


class UploadUrlIn(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    content_type: str
    size_bytes: int = Field(gt=0)
    sha256: str | None = Field(None, pattern="^[0-9a-f]{64}$")
    filename: str | None = Field(None, max_length=300)
    evidence_type: EvidenceType | None = None
    stage: str | None = Field(None, pattern="^(before|during|after|review)$")
    captured_at: datetime | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    client_ref: str | None = Field(None, max_length=80)
    replaces_media_id: uuid.UUID | None = None


class UploadUrlOut(BaseModel):
    media_id: uuid.UUID
    status: str
    upload: dict | None


class CompleteUploadIn(BaseModel):
    media_id: uuid.UUID
    caption: str | None = Field(None, max_length=300)


class MediaOut(Stamped):
    entity_type: str
    entity_id: uuid.UUID
    evidence_type: str | None
    stage: str | None
    uploaded_by: uuid.UUID
    captured_at: datetime | None
    uploaded_at: datetime | None
    latitude: float | None
    longitude: float | None
    content_type: str
    original_filename: str | None
    size_bytes: int | None
    sha256: str | None
    status: str
    error: str | None
    replaces_id: uuid.UUID | None
    replaced_by_id: uuid.UUID | None
    deleted_at: datetime | None
    retention_until: date | None
    legal_hold: bool
    scan_status: str
    url: str | None = None
    thumbnail_url: str | None = None
    approved: bool | None = None


# ---------------------------------------------------------------- complaints


class ComplaintIn(BaseModel):
    property_id: uuid.UUID | None = None
    category: str = Field(min_length=2, max_length=40)
    priority: Priority = Priority.MEDIUM
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(None, max_length=5000)


class ComplaintAssignIn(BaseModel):
    assigned_staff_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    create_task: bool = True
    task_category: TaskCategory | None = None
    due_at: datetime | None = None


class ComplaintStatusIn(BaseModel):
    status: str = Field(pattern="^(open|assigned|in_progress|resolved|closed)$")
    resolution: str | None = Field(None, max_length=5000)


class ComplaintCommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    internal: bool = False


class ComplaintCommentOut(ORM):
    id: uuid.UUID
    author_id: uuid.UUID
    author_name: str | None = None
    body: str
    internal: bool
    created_at: datetime


class ComplaintOut(Stamped):
    number: str
    property_id: uuid.UUID | None
    category: str
    priority: str
    title: str
    description: str | None
    status: str
    raised_by: uuid.UUID
    assigned_staff_id: uuid.UUID | None
    vendor_id: uuid.UUID | None
    maintenance_task_id: uuid.UUID | None
    resolution: str | None
    resolved_at: datetime | None
    closed_at: datetime | None
    property_label: str | None = None
    raised_by_name: str | None = None
    comments: list[ComplaintCommentOut] | None = None
    task_number: str | None = None
    task_status: str | None = None


# ---------------------------------------------------------------- inspections


class InspectionIn(BaseModel):
    property_id: uuid.UUID
    inspector_id: uuid.UUID | None = None
    is_property_watch: bool = False
    scheduled_for: datetime | None = None
    points: list[str] | None = None


class InspectionItemIn(BaseModel):
    condition: str = Field(pattern="^(good|attention|issue|na)$")
    notes: str | None = Field(None, max_length=2000)


class InspectionCompleteIn(GeoPoint):
    overall_condition: str = Field(pattern="^(good|attention|issue)$")
    findings: str | None = Field(None, max_length=5000)


class FollowUpIn(BaseModel):
    item_id: uuid.UUID
    title: str | None = None
    category: TaskCategory | None = None
    priority: Priority = Priority.MEDIUM
    assigned_staff_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None


class InspectionItemOut(ORM):
    id: uuid.UUID
    position: int
    point: str
    condition: str | None
    notes: str | None
    follow_up_task_id: uuid.UUID | None


class InspectionOut(Stamped):
    number: str
    property_id: uuid.UUID
    inspector_id: uuid.UUID | None
    is_property_watch: bool
    status: str
    scheduled_for: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    overall_condition: str | None
    findings: str | None
    latitude: float | None
    longitude: float | None
    items: list[InspectionItemOut] = []
    property_label: str | None = None
    inspector_name: str | None = None
    media: list[MediaOut] | None = None
