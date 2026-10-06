"""Sign-in, sessions, one-time codes, password reset and 2-step verification."""

import uuid

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import DB, Actor, CurrentActor, client_ip
from app.core.ratelimit import limiter
from app.core.rbac import permissions_for
from app.core.security import (
    decode_access_token,
    decode_mfa_token,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_password,
)
from app.models import RefreshToken, Tenant, User
from app.models.base import utcnow
from app.schemas.common import Message
from app.schemas.core import AcceptInviteIn, ChangePasswordIn, LoginIn, MeOut, RefreshIn, TokenOut
from app.services import accounts, audit, messaging
from app.services.whatsapp import normalize_phone, users_for_phone

router = APIRouter(prefix="/auth", tags=["auth"])


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _throttle(request: Request, *keys: str) -> None:
    s = get_settings()
    for key in (f"ip:{client_ip(request) or 'unknown'}", *keys):
        if not limiter.allow(f"login:{key}", s.login_rate_per_minute):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again in a minute.")


def _set_password(db, user: User, password: str) -> None:
    try:
        validate_password_strength(password)
    except ValueError as e:
        raise HTTPException(422, str(e))
    user.password_hash = hash_password(password)
    user.token_version += 1  # every existing access token stops working
    for row in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))):
        row.revoked_at = utcnow()


# --------------------------------------------------------------------------- password sign-in


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: DB):
    """Email + password. Accounts with 2-step verification get an mfa_token to finish at /auth/2fa/verify."""
    _throttle(request, body.email.lower())
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is not None and user.is_active:
        accounts.ensure_not_locked(user)
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        if user is not None and user.is_active:
            accounts.register_failure(db, user, client_ip(request))
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    accounts.ensure_can_sign_in(db, user)
    out = accounts.complete_sign_in(db, user, "password", body.device or _ua(request), client_ip(request), _ua(request))
    db.commit()
    return out


class MfaVerifyIn(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=20)
    device: str | None = Field(None, max_length=200)


@router.post("/2fa/verify", response_model=TokenOut)
def mfa_verify(body: MfaVerifyIn, request: Request, db: DB):
    """Second step: a code from the authenticator app, or a one-time recovery code."""
    try:
        payload = decode_mfa_token(body.mfa_token)
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in expired. Please start again.")
    if user is None or payload.get("ver") != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in expired. Please start again.")
    _throttle(request, f"mfa:{user.id}")
    accounts.ensure_can_sign_in(db, user)
    method = accounts.verify_second_factor(user, body.code)
    if method is None:
        accounts.register_failure(db, user, client_ip(request))
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid verification code")
    accounts.register_success(user)
    user.last_login_at = utcnow()
    actor = Actor(user=user, ip=client_ip(request), user_agent=_ua(request))
    audit.record(db, actor, "auth.login", "user", user.id, new={"method": payload.get("amr"), "second_factor": method})
    out = accounts.issue_session(db, user, body.device or _ua(request), client_ip(request))
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
    out = accounts.rotate_session(db, row, user, client_ip(request))
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


# --------------------------------------------------------------------------- profile


@router.get("/me", response_model=MeOut)
def me(actor: CurrentActor, db: DB):
    out = MeOut.model_validate(actor.user)
    out.permissions = permissions_for(actor.role)
    out.mfa_setup_required = accounts.mfa_setup_required(actor.user)
    out.recovery_codes_left = len(actor.user.recovery_codes or [])
    if actor.user.tenant_id:
        t = db.get(Tenant, actor.user.tenant_id)
        out.tenant_name = t.name
        out.tenant_modules = t.modules or []
    return out


@router.post("/change-password", response_model=Message)
def change_password(body: ChangePasswordIn, db: DB, actor: CurrentActor):
    if not verify_password(body.current_password, actor.user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    _set_password(db, actor.user, body.new_password)
    audit.record(db, actor, "auth.password_changed", "user", actor.id)
    messaging.send_link(None, actor.user.email, "Your GreenPlot password was changed", "If this wasn't you, reset your password now.")
    db.commit()
    return Message(message="Password changed. Please log in again.")


@router.post("/accept-invite", response_model=TokenOut)
def accept_invite(body: AcceptInviteIn, request: Request, db: DB):
    user = db.scalar(select(User).where(User.invite_token_hash == hash_token(body.token)))
    if user is None or not user.invite_expires_at or user.invite_expires_at < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invite link is invalid or has expired")
    _set_password(db, user, body.password)
    user.invite_token_hash = None
    user.invite_expires_at = None
    user.is_active = True
    user.last_login_at = utcnow()
    audit.record(db, Actor(user, client_ip(request), _ua(request)), "auth.invite_accepted", "user", user.id)
    out = accounts.issue_session(db, user, _ua(request), client_ip(request))
    db.commit()
    return out


# --------------------------------------------------------------------------- sessions


class SessionOut(BaseModel):
    id: uuid.UUID
    device: str | None
    ip: str | None
    created_at: object
    last_used_at: object | None
    current: bool


@router.get("/sessions", response_model=list[SessionOut])
def sessions(request: Request, db: DB, actor: CurrentActor):
    """Devices signed in to this account."""
    current = None
    auth = request.headers.get("authorization", "")
    try:
        current = decode_access_token(auth.removeprefix("Bearer ").strip()).get("sid")
    except jwt.PyJWTError:
        pass
    rows = db.scalars(
        select(RefreshToken)
        .where(RefreshToken.user_id == actor.id, RefreshToken.revoked_at.is_(None), RefreshToken.expires_at > utcnow())
        .order_by(RefreshToken.last_used_at.desc())
    )
    return [
        SessionOut(id=r.id, device=r.device, ip=r.ip, created_at=r.created_at, last_used_at=r.last_used_at, current=str(r.id) == current)
        for r in rows
    ]


@router.delete("/sessions/{session_id}", response_model=Message)
def revoke_session(session_id: uuid.UUID, db: DB, actor: CurrentActor):
    row = db.get(RefreshToken, session_id)
    if row is None or row.user_id != actor.id:
        raise HTTPException(404, "Session not found")
    row.revoked_at = row.revoked_at or utcnow()
    audit.record(db, actor, "auth.session_revoked", "user", actor.id, new={"session": session_id, "device": row.device})
    db.commit()
    return Message(message="Signed out of that device")


# --------------------------------------------------------------------------- phone + one-time code sign-in


class PhoneIn(BaseModel):
    phone: str = Field(min_length=6, max_length=30)


class PhoneCodeIn(PhoneIn):
    code: str = Field(min_length=4, max_length=10)
    device: str | None = Field(None, max_length=200)


def _phone_user(db, phone: str) -> User | None:
    users = [u for u in users_for_phone(db, phone) if u.role != "super_admin"]
    if len(users) > 1:
        raise HTTPException(409, "This number is linked to more than one account. Sign in with your email instead.")
    return users[0] if users else None


@router.post("/otp/request")
def otp_request(body: PhoneIn, request: Request, db: DB):
    """Send a sign-in code to a registered mobile number (WhatsApp, else SMS)."""
    phone = normalize_phone(body.phone)
    if not phone:
        raise HTTPException(422, "Enter a valid mobile number")
    _throttle(request, f"otp:{phone}")
    user = _phone_user(db, phone)
    if user is None or not user.is_active:
        return {"sent": True, "channels": []}  # don't reveal which numbers are registered
    accounts.ensure_not_locked(user)
    code = accounts.issue_otp(db, "login", phone, user, client_ip(request))
    channels = messaging.send_otp(phone=phone, code=code, purpose="sign-in")
    db.commit()
    return accounts.otp_response(code, channels)


@router.post("/otp/verify", response_model=TokenOut)
def otp_verify(body: PhoneCodeIn, request: Request, db: DB):
    phone = normalize_phone(body.phone)
    if not phone:
        raise HTTPException(422, "Enter a valid mobile number")
    _throttle(request, f"otp:{phone}")
    row = accounts.check_otp(db, "login", phone, body.code)
    user = accounts.ensure_can_sign_in(db, db.get(User, row.user_id) if row.user_id else None)
    user.phone_verified_at = user.phone_verified_at or utcnow()
    out = accounts.complete_sign_in(db, user, "phone_otp", body.device or _ua(request), client_ip(request), _ua(request))
    db.commit()
    return out


# --------------------------------------------------------------------------- forgot password


class ForgotIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=200, description="Email or mobile number")


class ResetIn(ForgotIn):
    code: str = Field(min_length=4, max_length=10)
    new_password: str = Field(min_length=8, max_length=200)


def _resolve(db, identifier: str) -> tuple[User | None, str | None, str]:
    ident = identifier.strip()
    if "@" in ident:
        email = ident.lower()
        return db.scalar(select(User).where(User.email == email)), None, email
    phone = normalize_phone(ident)
    if not phone:
        raise HTTPException(422, "Enter your email or a valid mobile number")
    return _phone_user(db, phone), phone, phone


@router.post("/password/forgot")
def forgot_password(body: ForgotIn, request: Request, db: DB):
    """Send a reset code to the email or mobile number on the account. The response never reveals whether it exists."""
    user, phone, dest = _resolve(db, body.identifier)
    _throttle(request, f"reset:{dest}")
    if user is None or not user.is_active:
        return {"sent": True, "channels": []}
    code = accounts.issue_otp(db, "reset", dest, user, client_ip(request))
    channels = messaging.send_otp(phone=phone, email=None if phone else user.email, code=code, purpose="password reset")
    audit.record(db, None, "auth.reset_requested", "user", user.id, new={"via": "phone" if phone else "email"}, tenant_id=user.tenant_id)
    db.commit()
    return accounts.otp_response(code, channels)


@router.post("/password/reset", response_model=Message)
def reset_password(body: ResetIn, request: Request, db: DB):
    user, _, dest = _resolve(db, body.identifier)
    _throttle(request, f"reset:{dest}")
    row = accounts.check_otp(db, "reset", dest, body.code)
    user = db.get(User, row.user_id) if row.user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The code is incorrect or has expired. Request a new one.")
    _set_password(db, user, body.new_password)
    accounts.unlock(user)
    user.invite_token_hash = user.invite_expires_at = None  # a reset also completes a pending invite
    audit.record(db, Actor(user, client_ip(request), _ua(request)), "auth.password_reset", "user", user.id)
    messaging.send_link(None, user.email, "Your GreenPlot password was reset", "If this wasn't you, contact your layout office.")
    db.commit()
    return Message(message="Password updated. You can now sign in.")


# --------------------------------------------------------------------------- verify a new phone number


@router.post("/phone/request")
def phone_request(body: PhoneIn, request: Request, db: DB, actor: CurrentActor):
    phone = normalize_phone(body.phone)
    if not phone:
        raise HTTPException(422, "Enter a valid mobile number")
    _throttle(request, f"phone:{actor.id}")
    code = accounts.issue_otp(db, "phone", phone, actor.user, client_ip(request))
    channels = messaging.send_otp(phone=phone, code=code, purpose="phone verification")
    db.commit()
    return accounts.otp_response(code, channels)


@router.post("/phone/confirm")
def phone_confirm(body: PhoneCodeIn, db: DB, actor: CurrentActor):
    phone = normalize_phone(body.phone)
    if not phone:
        raise HTTPException(422, "Enter a valid mobile number")
    row = accounts.check_otp(db, "phone", phone, body.code)
    if row.user_id != actor.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The code is incorrect or has expired. Request a new one.")
    old = actor.user.phone
    actor.user.phone = body.phone.strip()
    actor.user.phone_verified_at = utcnow()
    audit.record(db, actor, "user.phone_verified", "user", actor.id, old={"phone": old}, new={"phone": actor.user.phone})
    db.commit()
    return {"phone": actor.user.phone, "verified": True}


# --------------------------------------------------------------------------- 2-step verification management


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class DisableIn(CodeIn):
    password: str


@router.post("/2fa/setup")
def mfa_setup(db: DB, actor: CurrentActor):
    """Start enrolment: a new secret to scan into an authenticator app (not active until confirmed)."""
    import segno

    u = actor.user
    if u.totp_enabled:
        raise HTTPException(409, "2-step verification is already on")
    secret = accounts.new_totp_secret()
    u.totp_secret_enc = accounts.encrypt_secret(secret)
    uri = accounts.provisioning_uri(u, secret)
    db.commit()
    return {"secret": secret, "otpauth_uri": uri, "qr_svg": segno.make(uri, error="m").svg_data_uri(scale=5, border=2)}


@router.post("/2fa/enable")
def mfa_enable(body: CodeIn, db: DB, actor: CurrentActor):
    u = actor.user
    secret = accounts.decrypt_secret(u.totp_secret_enc)
    if u.totp_enabled or not secret:
        raise HTTPException(409, "Start the setup first")
    if not accounts.verify_totp(secret, body.code):
        raise HTTPException(400, "That code doesn't match. Check the time on your phone and try again.")
    u.totp_enabled, u.totp_enabled_at = True, utcnow()
    codes = accounts.new_recovery_codes(u)
    audit.record(db, actor, "auth.2fa_enabled", "user", u.id)
    messaging.send_link(None, u.email, "2-step verification turned on", "2-step verification is now on for your GreenPlot account.")
    db.commit()
    return {"enabled": True, "recovery_codes": codes}


@router.post("/2fa/recovery-codes")
def mfa_recovery_codes(body: CodeIn, db: DB, actor: CurrentActor):
    u = actor.user
    if not u.totp_enabled or accounts.verify_second_factor(u, body.code) != "totp":
        raise HTTPException(400, "Enter a current code from your authenticator app")
    codes = accounts.new_recovery_codes(u)
    audit.record(db, actor, "auth.2fa_recovery_codes_regenerated", "user", u.id)
    db.commit()
    return {"recovery_codes": codes}


@router.post("/2fa/disable", response_model=Message)
def mfa_disable(body: DisableIn, db: DB, actor: CurrentActor):
    u = actor.user
    if not u.totp_enabled:
        raise HTTPException(409, "2-step verification is not on")
    if u.role in get_settings().mfa_roles:
        raise HTTPException(403, "2-step verification is required for your role")
    if not verify_password(body.password, u.password_hash) or accounts.verify_second_factor(u, body.code) is None:
        raise HTTPException(400, "Password or code is incorrect")
    u.totp_enabled, u.totp_secret_enc, u.recovery_codes, u.totp_enabled_at = False, None, [], None
    audit.record(db, actor, "auth.2fa_disabled", "user", u.id)
    messaging.send_link(None, u.email, "2-step verification turned off", "If this wasn't you, reset your password now.")
    db.commit()
    return Message(message="2-step verification turned off")
