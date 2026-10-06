import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import Role
from app.schemas.common import Stamped

# ---------------------------------------------------------------- auth


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    device: str | None = Field(None, max_length=200)


class TokenOut(BaseModel):
    """Tokens, or (for accounts with 2-step verification) an mfa_token to finish at /auth/2fa/verify."""

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    mfa_required: bool = False
    mfa_token: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class AcceptInviteIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=200)


class UserOut(Stamped):
    tenant_id: uuid.UUID | None
    email: str
    phone: str | None
    full_name: str
    role: str
    is_active: bool
    vendor_id: uuid.UUID | None
    last_login_at: datetime | None
    whatsapp_opt_in: bool = False
    phone_verified_at: datetime | None = None
    totp_enabled: bool = False
    locked_until: datetime | None = None


class MeOut(UserOut):
    permissions: list[str] = []
    mfa_setup_required: bool = False
    recovery_codes_left: int = 0
    tenant_name: str | None = None
    tenant_modules: list[str] = []


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(None, max_length=30)
    role: Role
    vendor_id: uuid.UUID | None = None
    password: str | None = Field(None, min_length=8, max_length=200)
    property_id: uuid.UUID | None = Field(None, description="Link a resident user to a property")


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=200)
    phone: str | None = Field(None, max_length=30)
    role: Role | None = None
    is_active: bool | None = None
    vendor_id: uuid.UUID | None = None


class InviteOut(BaseModel):
    user: UserOut
    invite_token: str | None = None
    invite_url: str | None = None
    sent_via: list[str] = []


# ---------------------------------------------------------------- tenants


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9-]{3,80}$")
    city: str = "Bangalore"
    plan: str = "core"
    modules: list[str] | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    admin_email: EmailStr
    admin_name: str
    admin_password: str | None = Field(None, min_length=8)
    layout_name: str | None = None


class TenantUpdate(BaseModel):
    name: str | None = None
    status: str | None = Field(None, pattern="^(active|suspended)$")
    plan: str | None = None
    modules: list[str] | None = None
    max_properties: int | None = None
    storage_quota_gb: int | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None


class TenantOut(Stamped):
    name: str
    slug: str
    city: str
    status: str
    plan: str
    modules: list[str]
    max_properties: int | None
    storage_quota_gb: int | None
    contact_email: str | None
    contact_phone: str | None
    settings: dict


class TenantSettingsIn(BaseModel):
    auto_close_on_approval: bool | None = None
    routine_media_retention_days: int | None = Field(None, ge=7, le=3650)
    incident_media_retention_days: int | None = Field(None, ge=30, le=3650)
    resident_evidence_visibility: str | None = Field(None, pattern="^(none|after_approval|all)$")
    notification_channels: dict[str, list[str]] | None = None
    sos_escalation_minutes: int | None = Field(None, ge=1, le=120)
    vendor_access_days: int | None = Field(None, ge=1, le=3650)
    # customer ticketing (ticketing requirements §42 open decisions)
    ticket_customer_max_priority: str | None = Field(None, pattern="^(low|medium|high|critical)$")
    ticket_reopen_days: int | None = Field(None, ge=0, le=365)
    ticket_auto_close_days: int | None = Field(None, ge=0, le=90)
    ticket_share_customer_contact: bool | None = None
    ticket_share_vendor_contact: bool | None = None
    ticket_assignee_customer_chat: bool | None = None
    ticket_sla_at_risk_percent: int | None = Field(None, ge=10, le=99)
    ticket_escalate_every_hours: int | None = Field(None, ge=1, le=168)
    ticket_sla: dict[str, dict[str, int]] | None = None


# ---------------------------------------------------------------- layouts / properties / residents


class LayoutIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    address: str | None = None
    city: str = "Bangalore"
    latitude: float | None = None
    longitude: float | None = None


class LayoutOut(Stamped):
    name: str
    address: str | None
    city: str
    latitude: float | None
    longitude: float | None


class PropertyIn(BaseModel):
    layout_id: uuid.UUID
    code: str = Field(min_length=1, max_length=40)
    plot_number: str = Field(min_length=1, max_length=40)
    block: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    area_sqft: float | None = Field(None, gt=0)
    units: int = Field(1, ge=1)
    status: str = "vacant_plot"
    condition: str = "good"
    owner_user_id: uuid.UUID | None = None
    owner_name: str | None = None
    owner_phone: str | None = None
    owner_email: EmailStr | None = None
    notes: str | None = None


class PropertyUpdate(BaseModel):
    plot_number: str | None = None
    block: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    area_sqft: float | None = None
    units: int | None = None
    status: str | None = None
    condition: str | None = None
    owner_user_id: uuid.UUID | None = None
    owner_name: str | None = None
    owner_phone: str | None = None
    owner_email: EmailStr | None = None
    notes: str | None = None


class PropertyOut(Stamped):
    layout_id: uuid.UUID
    code: str
    plot_number: str
    block: str | None
    address: str | None
    latitude: float | None
    longitude: float | None
    area_sqft: float | None
    units: int
    status: str
    condition: str
    owner_user_id: uuid.UUID | None
    owner_name: str | None
    owner_phone: str | None
    owner_email: str | None
    notes: str | None
    layout_name: str | None = None


class ResidentIn(BaseModel):
    property_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    phone: str | None = None
    email: EmailStr | None = None
    relation: str = Field("owner", pattern="^(owner|tenant|family)$")
    is_primary: bool = False
    in_directory: bool = False
    move_in: date | None = None
    user_id: uuid.UUID | None = None
    invite: bool = Field(False, description="Create a resident login and return an invite link")


class ResidentOut(Stamped):
    property_id: uuid.UUID
    user_id: uuid.UUID | None
    name: str
    phone: str | None
    email: str | None
    relation: str
    is_primary: bool
    in_directory: bool
    move_in: date | None


class TimelineEntry(BaseModel):
    at: datetime
    kind: str
    id: uuid.UUID
    number: str | None = None
    title: str
    status: str | None = None


# ---------------------------------------------------------------- assets, vendors, staff


class AssetIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    qr_code: str | None = Field(None, max_length=120)
    nfc_id: str | None = None
    name: str
    category: str
    property_id: uuid.UUID | None = None
    layout_id: uuid.UUID | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    installed_on: date | None = None
    vendor_id: uuid.UUID | None = None
    warranty_until: date | None = None
    condition: str = "good"
    service_interval_days: int | None = Field(None, ge=1)
    next_service_due: date | None = None
    notes: str | None = None


class AssetUpdate(BaseModel):
    name: str | None = None
    nfc_id: str | None = None
    category: str | None = None
    property_id: uuid.UUID | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    installed_on: date | None = None
    vendor_id: uuid.UUID | None = None
    warranty_until: date | None = None
    condition: str | None = None
    service_interval_days: int | None = None
    next_service_due: date | None = None
    notes: str | None = None


class AssetOut(Stamped):
    code: str
    qr_code: str
    nfc_id: str | None
    name: str
    category: str
    property_id: uuid.UUID | None
    layout_id: uuid.UUID | None
    location: str | None
    latitude: float | None
    longitude: float | None
    installed_on: date | None
    vendor_id: uuid.UUID | None
    warranty_until: date | None
    condition: str
    service_interval_days: int | None
    next_service_due: date | None
    notes: str | None


class VendorIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    contact_person: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    service_categories: list[str] = []
    address: str | None = None
    is_active: bool = True
    notes: str | None = None


class VendorUpdate(BaseModel):
    name: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    service_categories: list[str] | None = None
    address: str | None = None
    is_active: bool | None = None
    notes: str | None = None


class VendorOut(Stamped):
    name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    service_categories: list[str]
    address: str | None
    is_active: bool
    notes: str | None


class StaffIn(BaseModel):
    user_id: uuid.UUID
    employee_code: str | None = None
    designation: str | None = None
    skills: list[str] = []
    shift_name: str | None = None
    shift_start: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    shift_end: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    is_active: bool = True


class StaffUpdate(BaseModel):
    employee_code: str | None = None
    designation: str | None = None
    skills: list[str] | None = None
    shift_name: str | None = None
    shift_start: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    shift_end: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    is_active: bool | None = None


class StaffOut(Stamped):
    user_id: uuid.UUID
    employee_code: str | None
    designation: str | None
    skills: list[str]
    shift_name: str | None
    shift_start: str | None
    shift_end: str | None
    is_active: bool
    full_name: str | None = None
    role: str | None = None
    phone: str | None = None


class AttendanceOut(Stamped):
    user_id: uuid.UUID
    work_date: date
    check_in_at: datetime | None
    check_out_at: datetime | None
    latitude: float | None
    longitude: float | None
    method: str
