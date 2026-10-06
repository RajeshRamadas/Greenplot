"""One-time codes and self-registration requests."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Model, UTCDateTime


class OtpCode(Model):
    """A hashed one-time code sent to a phone or email address."""

    __tablename__ = "otp_codes"

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    purpose: Mapped[str] = mapped_column(String(20), index=True)  # login, reset, phone, signup
    destination: Mapped[str] = mapped_column(String(200), index=True)  # normalised phone or lower-case email
    code_hash: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SignupRequest(Model):
    """A resident or vendor asking to join a layout; the layout office approves or rejects it."""

    __tablename__ = "signup_requests"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # resident, vendor
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(30))
    plot_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    relation: Mapped[str | None] = mapped_column(String(30), nullable=True)  # owner, tenant, family
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    service_categories: Mapped[list] = mapped_column(JSON, default=list)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending, approved, rejected
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
