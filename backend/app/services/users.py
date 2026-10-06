import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import Actor
from app.core.security import hash_password, hash_token, new_opaque_token, validate_password_strength
from app.models import StaffProfile, User, Vendor
from app.models.base import utcnow
from app.models.enums import Role
from app.services import audit


def create_user(
    db: Session,
    actor: Actor | None,
    tenant_id: uuid.UUID | None,
    *,
    email: str,
    full_name: str,
    role: str,
    phone: str | None = None,
    vendor_id: uuid.UUID | None = None,
    password: str | None = None,
) -> tuple[User, str | None]:
    """Create a user. Without a password an invite token is issued (resident/staff onboarding)."""
    email = email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "A user with this email already exists")
    if role == Role.SUPER_ADMIN and tenant_id is not None:
        raise HTTPException(422, "Super admins are platform users")
    if role == Role.VENDOR:
        v = db.get(Vendor, vendor_id) if vendor_id else None
        if not v or v.tenant_id != tenant_id:
            raise HTTPException(422, "Vendor users must be linked to a vendor of this layout")
    elif vendor_id:
        raise HTTPException(422, "Only vendor users can be linked to a vendor")
    user = User(tenant_id=tenant_id, email=email, full_name=full_name, role=role, phone=phone, vendor_id=vendor_id)
    invite = None
    if password:
        try:
            validate_password_strength(password)
        except ValueError as e:
            raise HTTPException(422, str(e))
        user.password_hash = hash_password(password)
    else:
        invite = new_opaque_token()
        user.invite_token_hash = hash_token(invite)
        user.invite_expires_at = utcnow() + timedelta(hours=get_settings().invite_token_hours)
    db.add(user)
    db.flush()
    if role in (Role.STAFF, Role.GUARD, Role.SUPERVISOR) and tenant_id:
        db.add(StaffProfile(tenant_id=tenant_id, user_id=user.id, designation=role.title()))
    audit.record(
        db,
        actor,
        "user.created",
        "user",
        user.id,
        new={"email": email, "role": role, "vendor_id": vendor_id},
        tenant_id=tenant_id,
    )
    return user, invite


def invite_url(token: str | None) -> str | None:
    return f"{get_settings().app_url}/accept-invite?token={token}" if token else None
