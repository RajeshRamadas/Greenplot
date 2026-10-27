"""Push notifications to the Android and iPhone apps through Firebase Cloud Messaging (HTTP v1).

One Firebase project covers both stores: Android talks to FCM directly and iOS through the
APNs key uploaded in the Firebase console. Phones register their FCM token at /devices.

GP_PUSH_PROVIDER=log (the default) only logs; "fcm" sends, using a Google service account
(GP_FCM_SERVICE_ACCOUNT: the JSON key itself, or a path to it).
"""

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.core.config import get_settings
from app.models import DeviceToken, RefreshToken, User
from app.models.base import utcnow

log = logging.getLogger("greenplot.push")

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
# Errors that mean the app was uninstalled or the token rotated: stop sending to it.
GONE_ERRORS = ("UNREGISTERED", "NOT_FOUND", "registration-token-not-registered", "INVALID_ARGUMENT")


class PushError(Exception):
    def __init__(self, message: str, gone: bool = False):
        super().__init__(message)
        self.gone = gone


# --------------------------------------------------------------------------- transport

_transport: Callable[[str, dict], dict] | None = None


def set_transport(fn: Callable[[str, dict], dict] | None) -> None:
    """Override the HTTP call (tests): fn(token, message) returns FCM's reply or raises PushError."""
    global _transport
    _transport = fn


def enabled() -> bool:
    return get_settings().push_provider == "fcm" or _transport is not None


def _service_account() -> dict:
    raw = get_settings().fcm_service_account
    if not raw:
        raise PushError("Push is not configured (GP_FCM_SERVICE_ACCOUNT)")
    if not raw.lstrip().startswith("{") and os.path.exists(raw):
        with open(raw) as f:
            raw = f.read()
    return json.loads(raw)


_token_lock = threading.Lock()
_access_token: tuple[str, float] | None = None  # (token, expires at)


def _google_access_token() -> str:
    """OAuth token for FCM from the service account, cached until shortly before it expires."""
    global _access_token
    with _token_lock:
        if _access_token and _access_token[1] - 60 > time.time():
            return _access_token[0]
        sa = _service_account()
        now = int(time.time())
        assertion = jwt.encode(
            {"iss": sa["client_email"], "scope": FCM_SCOPE, "aud": sa["token_uri"], "iat": now, "exp": now + 3600},
            sa["private_key"],
            algorithm="RS256",
        )
        body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}).encode()
        req = urllib.request.Request(sa["token_uri"], data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - Google's token endpoint from the key file
                data = json.loads(r.read())
        except (urllib.error.URLError, TimeoutError) as e:
            raise PushError(f"Google sign-in failed: {e}") from e
        _access_token = (data["access_token"], time.time() + int(data.get("expires_in", 3600)))
        return _access_token[0]


def _post(token: str, message: dict) -> dict:
    if _transport is not None:
        return _transport(token, message)
    s = get_settings()
    project = s.fcm_project_id or _service_account().get("project_id")
    req = urllib.request.Request(
        f"https://fcm.googleapis.com/v1/projects/{project}/messages:send",
        data=json.dumps({"message": message}).encode(),
        headers={"Authorization": f"Bearer {_google_access_token()}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - fixed FCM endpoint
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        try:
            err = json.loads(detail).get("error", {})
            codes = [err.get("status", "")] + [d.get("errorCode", "") for d in err.get("details", [])]
            detail = f"{'/'.join(c for c in codes if c)} {err.get('message', '')}".strip()
        except (ValueError, AttributeError):
            codes = []
        raise PushError(f"HTTP {e.code}: {detail}", gone=e.code == 404 or any(c in GONE_ERRORS for c in codes)) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise PushError(str(e)) from e


# --------------------------------------------------------------------------- sending


def message(token: str, title: str, body: str | None, data: dict | None) -> dict:
    """An FCM v1 message that shows as a notification on both platforms; data values must be strings."""
    return {
        "token": token,
        "notification": {"title": title[:200], "body": (body or "")[:1000]},
        "data": {k: str(v) for k, v in (data or {}).items()},
        "android": {"priority": "high", "notification": {"channel_id": "updates"}},
        "apns": {"payload": {"aps": {"sound": "default"}}},
    }


def active_devices(db: Session, user_id) -> list[DeviceToken]:
    """Phones still signed in: a device stops getting pushes as soon as its session is signed out or expires."""
    return list(
        db.scalars(
            select(DeviceToken)
            .join(RefreshToken, RefreshToken.id == DeviceToken.session_id)
            .where(
                DeviceToken.user_id == user_id,
                DeviceToken.disabled_at.is_(None),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > utcnow(),
            )
        )
    )


def send_to_user(user: User, title: str, body: str | None, data: dict | None = None) -> tuple[str, str | None]:
    """Channel adapter entry point: every active phone of the user. Returns (result, provider message id)."""
    db = object_session(user)
    devices = active_devices(db, user.id) if db is not None else []
    if not devices:
        return "skipped:no_device", None
    if not enabled():
        log.info("[push:log] -> %s (%d devices): %s", user.email, len(devices), title)
        return "sent", None
    sent_id, errors = None, []
    for d in devices:
        try:
            reply = _post(d.token, message(d.token, title, body, data))
            sent_id = sent_id or reply.get("name") or "sent"
        except PushError as e:
            errors.append(str(e))
            if e.gone:
                d.disabled_at, d.disabled_reason = utcnow(), str(e)[:200]
    if sent_id:
        return "sent", sent_id if sent_id != "sent" else None
    return f"failed:{errors[0] if errors else 'no device accepted the message'}", None
