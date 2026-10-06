"""Direct messages to a person: one-time codes, invite links and security alerts.

Unlike notifications (in-app first, per-event channel settings), these must reach
someone who may not be able to sign in yet, so they go straight to email,
WhatsApp and/or SMS. Email uses SMTP when GP_SMTP_HOST is set; otherwise every
channel only logs, and outside production the API returns one-time codes so the
flows can be tried without providers.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger("greenplot.messaging")


def _sent(r: str) -> bool:
    return r.split(":", 1)[0] == "sent"


# --------------------------------------------------------------------------- email


_smtp_sender = None


def set_smtp_sender(fn) -> None:
    """Override SMTP delivery (tests)."""
    global _smtp_sender
    _smtp_sender = fn


def send_email(to: str | None, subject: str, text: str) -> str:
    if not to:
        return "skipped:no_email"
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(text)
    if _smtp_sender is not None:
        _smtp_sender(msg)
        return "sent"
    if not s.smtp_host:
        log.info("[email:log] -> %s: %s", to, subject)
        return "sent"
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            if s.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(msg)
        return "sent"
    except (OSError, smtplib.SMTPException) as e:
        log.warning("email to %s failed: %s", to, e)
        return f"failed:{e}"


# --------------------------------------------------------------------------- phone


def send_sms(phone: str | None, text: str) -> str:
    """SMS provider hook (MSG91, Twilio, …). Logs until a provider is plugged in."""
    if not phone:
        return "skipped:no_phone"
    log.info("[sms:log] -> %s: %s", phone, text)
    return "sent"


def send_otp(phone: str | None = None, email: str | None = None, code: str = "", purpose: str = "sign-in") -> list[str]:
    """Send a one-time code by WhatsApp (authentication template), else SMS, and by email if given."""
    from app.services import whatsapp

    channels: list[str] = []
    text = f"{code} is your GreenPlot {purpose} code. It expires in {get_settings().otp_minutes} minutes. Never share it."
    phone_n = whatsapp.normalize_phone(phone) if phone else None
    if phone_n:
        r = whatsapp.send_otp(phone_n, code) if whatsapp.enabled() else "skipped:whatsapp_off"
        if _sent(r):
            channels.append("whatsapp")
        elif _sent(send_sms(phone_n, text)):
            channels.append("sms")
    if email and _sent(send_email(email, f"Your GreenPlot {purpose} code", text)):
        channels.append("email")
    return channels


def send_link(phone: str | None, email: str | None, subject: str, text: str) -> list[str]:
    """A message with a link (invites, approvals) by email, WhatsApp and/or SMS."""
    from app.services import whatsapp

    channels: list[str] = []
    if email and _sent(send_email(email, subject, text)):
        channels.append("email")
    phone_n = whatsapp.normalize_phone(phone) if phone else None
    if phone_n:
        if whatsapp.enabled() and _sent(whatsapp.send_template(phone_n, subject, text)):
            channels.append("whatsapp")
        elif _sent(send_sms(phone_n, f"{subject}: {text}")):
            channels.append("sms")
    return channels
