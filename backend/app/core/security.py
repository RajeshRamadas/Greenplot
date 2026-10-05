import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algo, n, r, p, salt_b64, digest_b64 = encoded.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    expected = base64.b64decode(digest_b64)
    actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    return hmac.compare_digest(actual, expected)


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if password.isdigit() or password.isalpha():
        raise ValueError("Password must mix letters and numbers or symbols")


def create_access_token(user_id: uuid.UUID, tenant_id: uuid.UUID | None, role: str, token_version: int) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id) if tenant_id else None,
        "role": role,
        "ver": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_minutes),
        "typ": "access",
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sign_value(value: str, expires_in: int) -> str:
    """Short-lived HMAC signature for local-storage signed URLs."""
    exp = int((datetime.now(UTC) + timedelta(seconds=expires_in)).timestamp())
    msg = f"{value}:{exp}".encode()
    sig = hmac.new(get_settings().secret_key.encode(), msg, hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def verify_signed_value(value: str, token: str) -> bool:
    try:
        exp_s, sig = token.split(".", 1)
        exp = int(exp_s)
    except ValueError:
        return False
    if exp < int(datetime.now(UTC).timestamp()):
        return False
    msg = f"{value}:{exp}".encode()
    expected = hmac.new(get_settings().secret_key.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)
