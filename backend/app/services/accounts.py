"""Sign-in and account protection: sessions, one-time codes, lockout, 2-step verification, invites."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import timedelta
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import Actor
from app.core.security import create_access_token, create_mfa_token, hash_token, new_opaque_token
from app.models import OtpCode, RefreshToken, Tenant, User
from app.models.base import utcnow
from app.services import audit, messaging

# --------------------------------------------------------------------------- sessions


def issue_session(db: Session, user: User, device: str | None, ip: str | None) -> dict:
    """Create a session (refresh token row) and return the token pair. The access token carries the session id."""
    s = get_settings()
    refresh = new_opaque_token()
    row = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh),
        expires_at=utcnow() + timedelta(days=s.refresh_token_days),
        device=(device or "")[:300] or None,
        ip=ip,
        last_used_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return {
        "access_token": create_access_token(user.id, user.tenant_id, user.role, user.token_version, row.id),
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": s.access_token_minutes * 60,
    }


def rotate_session(db: Session, row: RefreshToken, user: User, ip: str | None) -> dict:
    """Rotate the refresh token in place, so one row is one device session."""
    s = get_settings()
    refresh = new_opaque_token()
    row.token_hash = hash_token(refresh)
    row.last_used_at = utcnow()
    row.expires_at = utcnow() + timedelta(days=s.refresh_token_days)
    row.ip = ip or row.ip
    return {
        "access_token": create_access_token(user.id, user.tenant_id, user.role, user.token_version, row.id),
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": s.access_token_minutes * 60,
    }


def ensure_can_sign_in(db: Session, user: User | None) -> User:
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid sign-in details")
    if user.tenant_id:
        tenant = db.get(Tenant, user.tenant_id)
        if not tenant or tenant.status != "active":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant is not active")
    ensure_not_locked(user)
    return user


def complete_sign_in(db: Session, user: User, method: str, device: str | None, ip: str | None, user_agent: str | None) -> dict:
    """First factor succeeded: issue tokens, or ask for the second factor."""
    register_success(user)
    actor = Actor(user=user, ip=ip, user_agent=user_agent)
    if user.totp_enabled:
        audit.record(db, actor, "auth.mfa_challenged", "user", user.id, new={"method": method})
        return {"mfa_required": True, "mfa_token": create_mfa_token(user.id, user.token_version, method), "expires_in": None}
    user.last_login_at = utcnow()
    audit.record(db, actor, "auth.login", "user", user.id, new={"method": method})
    return issue_session(db, user, device, ip)


# --------------------------------------------------------------------------- lockout


def ensure_not_locked(user: User) -> None:
    if user.locked_until and user.locked_until > utcnow():
        minutes = max(1, int((user.locked_until - utcnow()).total_seconds() // 60) + 1)
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"Too many failed attempts. Try again in {minutes} min, or reset your password.",
        )


def register_failure(db: Session, user: User, ip: str | None) -> None:
    s = get_settings()
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= s.lockout_threshold:
        user.locked_until = utcnow() + timedelta(minutes=s.lockout_minutes)
        user.failed_login_count = 0
        audit.record(db, None, "auth.locked", "user", user.id, new={"minutes": s.lockout_minutes, "ip": ip}, tenant_id=user.tenant_id)
        messaging.send_link(
            None,
            user.email,
            "GreenPlot sign-in locked",
            f"Hello {user.full_name}, your account was locked for {s.lockout_minutes} minutes after "
            f"{s.lockout_threshold} failed sign-in attempts. If this wasn't you, reset your password: {s.app_url}/forgot-password",
        )


def register_success(user: User) -> None:
    user.failed_login_count = 0
    user.locked_until = None


def unlock(user: User) -> None:
    register_success(user)


# --------------------------------------------------------------------------- one-time codes

PURPOSE_LABEL = {"login": "sign-in", "reset": "password reset", "phone": "phone verification", "signup": "registration"}


def _otp_hash(purpose: str, destination: str, code: str) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"{purpose}:{destination}:{code}".encode(), hashlib.sha256).hexdigest()


def issue_otp(db: Session, purpose: str, destination: str, user: User | None = None, ip: str | None = None) -> str:
    s = get_settings()
    now = utcnow()
    recent = db.scalar(
        select(func.count())
        .select_from(OtpCode)
        .where(OtpCode.destination == destination, OtpCode.purpose == purpose, OtpCode.created_at > now - timedelta(hours=1))
    )
    if (recent or 0) >= s.otp_per_hour:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many codes requested. Try again later.")
    for old in db.scalars(
        select(OtpCode).where(OtpCode.destination == destination, OtpCode.purpose == purpose, OtpCode.consumed_at.is_(None))
    ):
        old.consumed_at = now  # only the newest code is valid
    code = f"{secrets.randbelow(10**6):06d}"
    db.add(
        OtpCode(
            user_id=user.id if user else None,
            purpose=purpose,
            destination=destination,
            code_hash=_otp_hash(purpose, destination, code),
            expires_at=now + timedelta(minutes=s.otp_minutes),
            ip=ip,
            created_at=now,
        )
    )
    db.flush()
    return code


def check_otp(db: Session, purpose: str, destination: str, code: str) -> OtpCode:
    """Consume a valid code or raise. Failed attempts are committed before raising."""
    s = get_settings()
    now = utcnow()
    row = db.scalar(
        select(OtpCode)
        .where(OtpCode.destination == destination, OtpCode.purpose == purpose, OtpCode.consumed_at.is_(None))
        .order_by(OtpCode.created_at.desc())
    )
    bad = HTTPException(status.HTTP_400_BAD_REQUEST, "The code is incorrect or has expired. Request a new one.")
    if row is None or row.expires_at < now:
        raise bad
    row.attempts += 1
    if not hmac.compare_digest(row.code_hash, _otp_hash(purpose, destination, (code or "").strip())):
        if row.attempts >= s.otp_max_attempts:
            row.consumed_at = now
        db.commit()
        raise bad
    row.consumed_at = now
    return row


def otp_response(code: str, channels: list[str]) -> dict:
    out: dict = {"sent": True, "channels": channels}
    if get_settings().show_codes:
        out["dev_code"] = code  # development/demo only: no SMS/WhatsApp provider needed
    return out


# --------------------------------------------------------------------------- 2-step verification (TOTP, RFC 6238)


def _fernet() -> Fernet:
    key = hashlib.sha256(b"greenplot-totp:" + get_settings().secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp(secret: str, at: float | None = None, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int((at if at is not None else time.time()) // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 10**digits:0{digits}d}"


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    code = (code or "").replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return False
    now = time.time()
    return any(hmac.compare_digest(totp(secret, now + i * 30), code) for i in range(-window, window + 1))


def provisioning_uri(user: User, secret: str) -> str:
    label = quote(f"GreenPlot:{user.email}", safe=":@")
    return f"otpauth://totp/{label}?secret={secret}&issuer=GreenPlot&digits=6&period=30"


def new_recovery_codes(user: User) -> list[str]:
    codes = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(10)]
    user.recovery_codes = [hashlib.sha256(c.encode()).hexdigest() for c in codes]
    return codes


def verify_second_factor(user: User, code: str) -> str | None:
    """Returns 'totp' or 'recovery' when the code is valid; recovery codes are single use."""
    secret = decrypt_secret(user.totp_secret_enc)
    if secret and verify_totp(secret, code):
        return "totp"
    h = hashlib.sha256((code or "").strip().lower().encode()).hexdigest()
    if h in (user.recovery_codes or []):
        user.recovery_codes = [x for x in user.recovery_codes if x != h]
        return "recovery"
    return None


def mfa_setup_required(user: User) -> bool:
    return user.role in get_settings().mfa_roles and not user.totp_enabled


# --------------------------------------------------------------------------- invites


def invite_link(token: str | None) -> str | None:
    return f"{get_settings().app_url}/accept-invite?token={token}" if token else None


def deliver_invite(db: Session, user: User, token: str | None) -> list[str]:
    """Send the invite link by email and WhatsApp/SMS. Returns the channels it went out on."""
    if not token:
        return []
    s = get_settings()
    tenant = db.get(Tenant, user.tenant_id) if user.tenant_id else None
    where = f" for {tenant.name}" if tenant else ""
    text = (
        f"Hello {user.full_name}, you have been invited to GreenPlot{where}. "
        f"Set your password here (the link is valid for {s.invite_token_hours} hours): {invite_link(token)}"
    )
    return messaging.send_link(user.phone, user.email, "Your GreenPlot invitation", text)
