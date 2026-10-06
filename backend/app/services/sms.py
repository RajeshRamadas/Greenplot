"""SMS through MSG91 (India). Open decision 13: SMS provider.

Indian SMS must use DLT-registered templates, so every message is sent with
MSG91's Flow API (POST {api}/flow) against one of three templates created in the
MSG91 panel and linked to DLT:

  GP_MSG91_OTP_TEMPLATE_ID      variables: ##otp##             e.g. "##otp## is your GreenPlot code. Valid 10 minutes. -GreenPlot"
  GP_MSG91_NOTIFY_TEMPLATE_ID   variables: ##title## ##body##  e.g. "GreenPlot: ##title## ##body##"
  GP_MSG91_LINK_TEMPLATE_ID     variables: ##title## ##link##  e.g. "GreenPlot: ##title## Open: ##link##"

DLT caps each variable (usually 30 characters), so text variables are trimmed to
GP_MSG91_VAR_MAX; links are never trimmed. Delivery reports arrive at
/api/v1/webhooks/msg91?token=GP_MSG91_WEBHOOK_TOKEN and update the delivery log.

With GP_SMS_PROVIDER=log (the default) messages are only logged.
"""

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import NotificationDelivery
from app.models.base import utcnow

log = logging.getLogger("greenplot.sms")


class SmsError(Exception):
    pass


_transport: Callable[[str, dict], dict] | None = None


def set_transport(fn: Callable[[str, dict], dict] | None) -> None:
    """Override the HTTP call (tests). fn(path, payload) -> response JSON."""
    global _transport
    _transport = fn


def enabled() -> bool:
    return get_settings().sms_provider == "msg91" or _transport is not None


def _post(path: str, payload: dict) -> dict:
    if _transport is not None:
        return _transport(path, payload)
    s = get_settings()
    if not s.msg91_authkey:
        raise SmsError("MSG91 is not configured (GP_MSG91_AUTHKEY)")
    req = urllib.request.Request(
        f"{s.msg91_api_url.rstrip('/')}/{path}",
        data=json.dumps(payload).encode(),
        headers={"authkey": s.msg91_authkey, "Content-Type": "application/json", "accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - fixed https endpoint from settings
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise SmsError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise SmsError(str(e)) from e


def _clip(text: str | None) -> str:
    limit = get_settings().msg91_var_max
    t = " ".join((text or "").split()) or "-"
    return t if len(t) <= limit else t[: limit - 1] + "…"


def _flow(template_id: str | None, phone: str, variables: dict[str, str]) -> tuple[str, str | None]:
    """Send one DLT template message. Returns (result, MSG91 request id)."""
    if not template_id:
        return "skipped:no_template", None
    payload = {"template_id": template_id, "short_url": "0", "recipients": [{"mobiles": phone, **variables}]}
    sender = get_settings().msg91_sender
    if sender:
        payload["sender"] = sender
    try:
        resp = _post("flow", payload)
    except SmsError as e:
        log.warning("MSG91 send to %s failed: %s", phone, e)
        return f"failed:{e}", None
    if str(resp.get("type", "")).lower() != "success":
        return f"failed:{resp.get('message') or resp}", None
    return "sent", str(resp.get("message") or resp.get("request_id") or "") or None


def _phone(raw: str | None) -> str | None:
    from app.services.whatsapp import normalize_phone

    return normalize_phone(raw)


# --------------------------------------------------------------------------- outbound


def send_otp(raw_phone: str | None, code: str) -> tuple[str, str | None]:
    phone = _phone(raw_phone)
    if not phone:
        return "skipped:no_phone", None
    if not enabled():
        log.info("[sms:log] -> %s: code %s", phone, code)
        return "sent", None
    return _flow(get_settings().msg91_otp_template_id, phone, {"otp": code})


def send_notification(raw_phone: str | None, title: str, body: str | None) -> tuple[str, str | None]:
    phone = _phone(raw_phone)
    if not phone:
        return "skipped:no_phone", None
    if not enabled():
        log.info("[sms:log] -> %s: %s", phone, title)
        return "sent", None
    return _flow(get_settings().msg91_notify_template_id, phone, {"title": _clip(title), "body": _clip(body)})


def send_link(raw_phone: str | None, title: str, link: str) -> tuple[str, str | None]:
    phone = _phone(raw_phone)
    if not phone:
        return "skipped:no_phone", None
    if not enabled():
        log.info("[sms:log] -> %s: %s %s", phone, title, link)
        return "sent", None
    return _flow(get_settings().msg91_link_template_id, phone, {"title": _clip(title), "link": link})


# --------------------------------------------------------------------------- delivery reports

DELIVERED = {"1", "delivered", "delivrd"}
FAILED_WORDS = ("fail", "reject", "ndnc", "block", "expired", "undeliv", "invalid", "dnd")


def _reports(payload) -> list[tuple[str, str]]:
    """Flatten MSG91 DLR payloads to (request_id, status text). Accepts a list or {"data": [...]}."""
    items = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(items, dict):
        items = [items]
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("requestId") or item.get("request_id") or item.get("requestID") or "")
        reports = item.get("report") or item.get("reports") or [item]
        for rep in reports if isinstance(reports, list) else [reports]:
            status = str(rep.get("desc") or rep.get("status") or rep.get("description") or "")
            if rid and status:
                out.append((rid, status))
    return out


def handle_dlr(db: Session, payload) -> int:
    n = 0
    now = utcnow()
    for rid, raw in _reports(payload):
        status = raw.strip().lower()
        for d in db.scalars(
            select(NotificationDelivery).where(NotificationDelivery.channel == "sms", NotificationDelivery.provider_message_id == rid)
        ):
            failed = any(w in status for w in FAILED_WORDS) or status in {"2", "9", "16", "17", "25", "26"}
            if not failed and (status in DELIVERED or "deliver" in status):
                d.status, d.delivered_at, d.failure_reason = "delivered", d.delivered_at or now, None
            elif failed:
                d.status, d.failure_reason = "failed", raw
            else:
                continue  # submitted / pending: no change
            n += 1
    db.commit()
    return n
