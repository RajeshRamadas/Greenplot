from enum import StrEnum


class Role(StrEnum):
    RESIDENT = "resident"
    GUARD = "guard"
    STAFF = "staff"
    SUPERVISOR = "supervisor"
    VENDOR = "vendor"
    LAYOUT_ADMIN = "layout_admin"
    SUPER_ADMIN = "super_admin"


class TaskStatus(StrEnum):
    CREATED = "created"
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    STARTED = "started"
    COMPLETED = "completed"
    REWORK_REQUIRED = "rework_required"
    APPROVED = "approved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class TaskCategory(StrEnum):
    CLEANING = "cleaning"
    COMPOUND = "compound_maintenance"
    GATE_FENCE = "gate_fence"
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    CIVIL = "civil"
    PAINTING = "painting"
    GARDENING = "gardening"
    LANDSCAPING = "landscaping"
    REPAIRS = "repairs"
    PREVENTIVE = "preventive"
    ASSET_SERVICING = "asset_servicing"
    INSPECTION = "inspection"
    OTHER = "other"


GARDENING_CATEGORIES = {TaskCategory.GARDENING, TaskCategory.LANDSCAPING}
CLEANING_CATEGORIES = {TaskCategory.CLEANING, TaskCategory.COMPOUND}


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ChecklistStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class EvidenceType(StrEnum):
    BEFORE_PHOTO = "before_photo"
    AFTER_PHOTO = "after_photo"
    PHOTO = "photo"
    VIDEO = "video"
    INVOICE = "invoice"
    RECEIPT = "receipt"
    SERVICE_REPORT = "service_report"
    WARRANTY = "warranty"
    DOCUMENT = "document"
    SUPERVISOR = "supervisor"


DOCUMENT_EVIDENCE = {
    EvidenceType.INVOICE,
    EvidenceType.RECEIPT,
    EvidenceType.SERVICE_REPORT,
    EvidenceType.WARRANTY,
    EvidenceType.DOCUMENT,
}


class RequirementKey(StrEnum):
    """Items an evidence policy can require (requirements §10, §48)."""

    BEFORE_PHOTO = "before_photo"
    AFTER_PHOTO = "after_photo"
    CHECKLIST = "checklist"
    GPS = "gps"
    VIDEO = "video"
    MATERIALS = "materials"
    INVOICE = "invoice"
    QR_SCAN = "qr_scan"


class MediaStatus(StrEnum):
    PENDING = "pending"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class ComplaintStatus(StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IncidentStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    CLOSED = "closed"


class SosStatus(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    FALSE_ALARM = "false_alarm"


class InspectionStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Condition(StrEnum):
    GOOD = "good"
    ATTENTION = "attention"
    ISSUE = "issue"
    NOT_APPLICABLE = "na"


INSPECTION_POINTS = [
    "boundary",
    "gate",
    "fencing",
    "vegetation",
    "garden",
    "water_utilities",
    "streetlights",
    "drainage",
    "security",
    "common_infrastructure",
]


class VisitorStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    DENIED = "denied"
    INSIDE = "inside"
    EXITED = "exited"


class InvoiceStatus(StrEnum):
    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"
    WAIVED = "waived"


class BillingBasis(StrEnum):
    PER_PLOT = "per_plot"
    PER_UNIT = "per_unit"
    PER_SQFT = "per_sqft"
    FIXED = "fixed"
    CUSTOM = "custom"


class PaymentStatus(StrEnum):
    CREATED = "created"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class NoticeType(StrEnum):
    ANNOUNCEMENT = "announcement"
    NOTICE = "notice"
    ALERT = "alert"
    EVENT = "event"
    OUTAGE = "outage"


class SyncState(StrEnum):
    QUEUED = "queued"
    SYNCING = "syncing"
    SYNCED = "synced"
    FAILED = "failed"
    RETRY = "retry"
    CONFLICT = "conflict"


class TicketStatus(StrEnum):
    """Customer ticket lifecycle (ticketing requirements §8)."""

    OPEN = "open"
    UNDER_REVIEW = "under_review"
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_CUSTOMER = "waiting_for_customer"
    WORK_COMPLETED = "work_completed"
    VERIFICATION = "verification"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"
    REOPENED = "reopened"


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CommentVisibility(StrEnum):
    """Who can read a ticket comment (ticketing requirements §13, §23)."""

    CUSTOMER = "customer"
    VENDOR = "vendor"
    INTERNAL = "internal"
    SUPERVISOR = "supervisor"
