import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Model, SoftDelete, TenantModel, UTCDateTime


class Tenant(Model):
    """A layout association / property manager using GreenPlot."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    city: Mapped[str] = mapped_column(String(100), default="Bangalore")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, suspended
    plan: Mapped[str] = mapped_column(String(40), default="core")
    modules: Mapped[list] = mapped_column(
        JSON,
        default=lambda: ["core", "security", "maintenance", "records", "billing", "vendors", "reports"],
    )
    max_properties: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_quota_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Tenant configuration: retention, notification channels, approval behaviour...
    settings: Mapped[dict] = mapped_column(JSON, default=dict)


class User(Model):
    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(30), index=True)
    password_hash: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("vendors.id"), nullable=True)
    invite_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    # WhatsApp consent: business-initiated messages go only to users who opted in.
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    whatsapp_opt_in_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    whatsapp_last_inbound_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    phone_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # Lockout after repeated failed sign-ins
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # 2-step verification (TOTP); the secret is Fernet-encrypted with a key derived from GP_SECRET_KEY
    totp_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_enabled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    recovery_codes: Mapped[list] = mapped_column(JSON, default=list)  # sha256 hashes of unused codes


class RefreshToken(Model):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    device: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Layout(TenantModel, SoftDelete):
    __tablename__ = "layouts"

    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str] = mapped_column(String(100), default="Bangalore")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)


class Property(TenantModel, SoftDelete):
    __tablename__ = "properties"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    layout_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("layouts.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))  # property/plot ID e.g. GV-117
    plot_number: Mapped[str] = mapped_column(String(40), index=True)
    block: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_sqft: Mapped[float | None] = mapped_column(Float, nullable=True)
    units: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="vacant_plot")  # vacant_plot, occupied, under_construction, rented
    condition: Mapped[str] = mapped_column(String(20), default="good")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    owner_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    owner_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    layout = relationship("Layout", lazy="joined")


class Resident(TenantModel, SoftDelete):
    __tablename__ = "residents"

    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    relation: Mapped[str] = mapped_column(String(30), default="owner")  # owner, tenant, family
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    in_directory: Mapped[bool] = mapped_column(Boolean, default=False)
    move_in: Mapped[date | None] = mapped_column(Date, nullable=True)


class Asset(TenantModel, SoftDelete):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("tenant_id", "qr_code"), UniqueConstraint("tenant_id", "code"))

    code: Mapped[str] = mapped_column(String(40))
    qr_code: Mapped[str] = mapped_column(String(120))
    nfc_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40))  # gate, pump, motor, streetlight, electrical, water, security, infrastructure
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id"), nullable=True)
    layout_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("layouts.id"), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    installed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("vendors.id"), nullable=True)
    warranty_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    condition: Mapped[str] = mapped_column(String(20), default="good")
    service_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_service_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Vendor(TenantModel, SoftDelete):
    __tablename__ = "vendors"

    name: Mapped[str] = mapped_column(String(200))
    contact_person: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    service_categories: Mapped[list] = mapped_column(JSON, default=list)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class StaffProfile(TenantModel):
    __tablename__ = "staff_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    employee_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    shift_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    shift_start: Mapped[str | None] = mapped_column(String(5), nullable=True)  # HH:MM local
    shift_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user = relationship("User", lazy="joined")


class Attendance(TenantModel):
    __tablename__ = "attendance"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    check_in_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    check_out_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    method: Mapped[str] = mapped_column(String(20), default="app")


class Counter(Model):
    """Per-tenant sequence for human record numbers (GP-MNT-2026-00418)."""

    __tablename__ = "counters"
    __table_args__ = (UniqueConstraint("tenant_id", "kind", "year"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))
    year: Mapped[int] = mapped_column(Integer)
    value: Mapped[int] = mapped_column(Integer, default=0)
