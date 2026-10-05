from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import DB, Actor, CurrentActor, client_ip
from app.core.ratelimit import limiter
from app.core.rbac import permissions_for
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    validate_password_strength,
    verify_password,
)
from app.models import RefreshToken, Tenant, User
from app.models.base import utcnow
from app.schemas.common import Message
from app.schemas.core import AcceptInviteIn, ChangePasswordIn, LoginIn, MeOut, RefreshIn, TokenOut
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue(db, user: User, device: str | None) -> TokenOut:
    s = get_settings()
    refresh = new_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            expires_at=utcnow() + timedelta(days=s.refresh_token_days),
            device=(device or "")[:300] or None,
        )
    )
    return TokenOut(
        access_token=create_access_token(user.id, user.tenant_id, user.role, user.token_version),
        refresh_token=refresh,
        expires_in=s.access_token_minutes * 60,
    )


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: DB):
    ip = client_ip(request) or "unknown"
    s = get_settings()
    if not limiter.allow(f"login:{ip}", s.login_rate_per_minute) or not limiter.allow(
        f"login:{body.email.lower()}", s.login_rate_per_minute
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts. Try again in a minute.")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if user.tenant_id:
        tenant = db.get(Tenant, user.tenant_id)
        if not tenant or tenant.status != "active":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant is not active")
    user.last_login_at = utcnow()
    actor = Actor(user=user, ip=ip, user_agent=request.headers.get("user-agent"))
    audit.record(db, actor, "auth.login", "user", user.id)
    out = _issue(db, user, body.device or request.headers.get("user-agent"))
    db.commit()
    return out


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, request: Request, db: DB):
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token)))
    if row is None or row.revoked_at or row.expires_at < utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please log in again.")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please log in again.")
    row.revoked_at = utcnow()  # rotate
    out = _issue(db, user, row.device)
    db.commit()
    return out


@router.post("/logout", response_model=Message)
def logout(body: RefreshIn, db: DB, actor: CurrentActor):
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token)))
    if row and row.user_id == actor.id and not row.revoked_at:
        row.revoked_at = utcnow()
    audit.record(db, actor, "auth.logout", "user", actor.id)
    db.commit()
    return Message(message="Logged out")


@router.post("/logout-all", response_model=Message)
def logout_all(db: DB, actor: CurrentActor):
    """Device loss: revoke every session and outstanding access token."""
    actor.user.token_version += 1
    for row in db.scalars(select(RefreshToken).where(RefreshToken.user_id == actor.id, RefreshToken.revoked_at.is_(None))):
        row.revoked_at = utcnow()
    audit.record(db, actor, "auth.logout_all", "user", actor.id)
    db.commit()
    return Message(message="All sessions revoked")


@router.get("/me", response_model=MeOut)
def me(actor: CurrentActor, db: DB):
    out = MeOut.model_validate(actor.user)
    out.permissions = permissions_for(actor.role)
    if actor.user.tenant_id:
        t = db.get(Tenant, actor.user.tenant_id)
        out.tenant_name = t.name
        out.tenant_modules = t.modules or []
    return out


@router.post("/change-password", response_model=Message)
def change_password(body: ChangePasswordIn, db: DB, actor: CurrentActor):
    if not verify_password(body.current_password, actor.user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    try:
        validate_password_strength(body.new_password)
    except ValueError as e:
        raise HTTPException(422, str(e))
    actor.user.password_hash = hash_password(body.new_password)
    actor.user.token_version += 1
    audit.record(db, actor, "auth.password_changed", "user", actor.id)
    db.commit()
    return Message(message="Password changed. Please log in again.")


@router.post("/accept-invite", response_model=TokenOut)
def accept_invite(body: AcceptInviteIn, request: Request, db: DB):
    user = db.scalar(select(User).where(User.invite_token_hash == hash_token(body.token)))
    if user is None or not user.invite_expires_at or user.invite_expires_at < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invite link is invalid or has expired")
    try:
        validate_password_strength(body.password)
    except ValueError as e:
        raise HTTPException(422, str(e))
    user.password_hash = hash_password(body.password)
    user.invite_token_hash = None
    user.invite_expires_at = None
    user.is_active = True
    user.last_login_at = utcnow()
    audit.record(db, Actor(user, client_ip(request), request.headers.get("user-agent")), "auth.invite_accepted", "user", user.id)
    out = _issue(db, user, request.headers.get("user-agent"))
    db.commit()
    return out
