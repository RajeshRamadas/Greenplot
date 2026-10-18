"""Before/after photo proof sent to the plot owner when a job closes.

The message carries a public link (signed, expires with routine media retention) to
a page with the before and after photos. Owners who wrote to us on WhatsApp in the
last 24 hours also get the photos themselves in the chat.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import Actor
from app.models import MaintenanceEvidence, MaintenanceTask, Property, User
from app.models.enums import EvidenceType, MediaStatus
from app.services import audit, owner_contact, whatsapp
from app.services.reports import IST
from app.services.storage import get_storage

log = logging.getLogger("greenplot.proof")

TOKEN_KIND = "job-proof"
STAGES = {"before": EvidenceType.BEFORE_PHOTO, "after": EvidenceType.AFTER_PHOTO}


def _setting(db: Session, tenant_id: uuid.UUID, key: str, default):
    from app.services.maintenance import tenant_setting

    return tenant_setting(db, tenant_id, key, default)


def proof_photos(db: Session, task: MaintenanceTask) -> dict[str, list[MaintenanceEvidence]]:
    """Current (not replaced) before and after photos, latest rework round last."""
    rows = db.scalars(
        select(MaintenanceEvidence)
        .where(
            MaintenanceEvidence.maintenance_id == task.id,
            MaintenanceEvidence.status == "active",
            MaintenanceEvidence.evidence_type.in_(list(STAGES.values())),
        )
        .order_by(MaintenanceEvidence.rework_round, MaintenanceEvidence.uploaded_at)
    )
    out: dict[str, list[MaintenanceEvidence]] = {k: [] for k in STAGES}
    for e in rows:
        m = e.media
        if m and m.status == MediaStatus.READY and m.content_type.startswith("image/"):
            out["before" if e.evidence_type == EvidenceType.BEFORE_PHOTO else "after"].append(e)
    return out


def proof_url(db: Session, task: MaintenanceTask) -> str:
    days = _setting(db, task.tenant_id, "routine_media_retention_days", get_settings().routine_media_retention_days)
    return owner_contact.app_link(f"/proof/{owner_contact.link_token(TOKEN_KIND, task.id, days)}")


def send_job_proof(db: Session, actor: Actor | None, task: MaintenanceTask) -> list[str] | None:
    """Send the proof to the owner. Returns the channels used, or None when there is nothing to send."""
    if not task.property_id or not _setting(db, task.tenant_id, "job_proof_enabled", True):
        return None
    if _setting(db, task.tenant_id, "resident_evidence_visibility", "after_approval") == "none":
        return None
    photos = proof_photos(db, task)
    if not photos["after"]:
        return None
    prop = db.get(Property, task.property_id)
    if prop is None or not owner_contact.has_owner_contact(db, prop):
        return None
    url = proof_url(db, task)
    when = task.closed_at or task.approved_at or task.completed_at
    shots = "before and after photos" if photos["before"] else "photos"
    title = f"Plot {prop.code}: {task.title} is done"
    body = f"Finished{f' on {when.astimezone(IST):%d %b}' if when else ''}. See the {shots}: {url}"
    channels = owner_contact.send(db, prop, "job_proof", title, body, "maintenance_task", task.id, url)
    if "whatsapp" in channels:
        _send_photos_in_chat(db, prop, photos)
    audit.record(db, actor, "maintenance.proof_sent", "maintenance_task", task.id, new={"channels": channels}, tenant_id=task.tenant_id)
    return channels


def _send_photos_in_chat(db: Session, prop: Property, photos: dict[str, list[MaintenanceEvidence]]) -> None:
    """Inside the 24-hour window WhatsApp allows media messages; outside it the link has to do."""
    if not whatsapp.enabled():
        return
    picks = [("Before", photos["before"][-1])] if photos["before"] else []
    picks.append(("After", photos["after"][-1]))
    storage = get_storage()
    for uid in owner_contact.owner_user_ids(db, prop):
        user = db.get(User, uid)
        phone = whatsapp.normalize_phone(user.phone) if user else None
        if not (user and user.whatsapp_opt_in and phone and whatsapp.in_session(user)):
            continue
        for label, e in picks:
            r = whatsapp.send_image(phone, storage.download_url(e.media.storage_key), f"{label} · plot {prop.code}")
            if not r.startswith("sent"):
                log.warning("proof photo to %s: %s", uid, r)


def public_view(db: Session, task: MaintenanceTask) -> dict:
    prop = db.get(Property, task.property_id) if task.property_id else None
    storage = get_storage()

    def photo(e: MaintenanceEvidence) -> dict:
        m = e.media
        return {
            "url": storage.download_url(m.storage_key),
            "thumbnail_url": storage.download_url(m.thumbnail_key) if m.thumbnail_key else None,
            "taken_at": e.captured_at or e.uploaded_at,
        }

    photos = proof_photos(db, task)
    return {
        "number": task.number,
        "title": task.title,
        "category": task.category,
        "plot": prop.code if prop else None,
        "layout": prop.layout.name if prop and prop.layout else None,
        "completed_at": task.completed_at,
        "closed_at": task.closed_at or task.approved_at,
        "before": [photo(e) for e in photos["before"]],
        "after": [photo(e) for e in photos["after"]],
    }
