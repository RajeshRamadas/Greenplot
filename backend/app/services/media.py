"""Media lifecycle: PENDING → UPLOADING → PROCESSING → READY / FAILED → DELETED (§12-13)."""

import uuid
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import Actor
from app.models import MaintenanceEvidence, MaintenanceTask, Media
from app.models.base import utcnow
from app.models.enums import EvidenceType, MediaStatus, TaskStatus
from app.services import audit
from app.services import maintenance as msvc
from app.services.access import check_entity_access, is_task_worker
from app.services.storage import (
    ALLOWED_TYPES,
    content_matches,
    get_storage,
    make_thumbnail,
    max_bytes_for,
    scan_for_malware,
    sha256_hex,
)


def _retention(db: Session, tenant_id: uuid.UUID, entity_type: str) -> tuple[date, bool]:
    s = get_settings()
    if entity_type == "incident":
        days = msvc.tenant_setting(db, tenant_id, "incident_media_retention_days", s.incident_media_retention_days)
        return date.today() + timedelta(days=days), True
    days = msvc.tenant_setting(db, tenant_id, "routine_media_retention_days", s.routine_media_retention_days)
    return date.today() + timedelta(days=days), False


def _check_evidence_allowed(db: Session, actor: Actor, task: MaintenanceTask, evidence_type: str | None):
    if evidence_type is None:
        raise HTTPException(422, "evidence_type is required for maintenance media")
    if evidence_type == EvidenceType.SUPERVISOR:
        if not actor.can("maintenance.review"):
            raise HTTPException(403, "Supervisor evidence is added by the reviewer")
        return
    if is_task_worker(actor, task):
        if task.status not in msvc.EVIDENCE_STATES:
            raise HTTPException(409, f"Evidence can only be captured on an accepted or started task (task is {task.status})")
    elif not actor.is_manager():
        raise HTTPException(403, "Only the assigned worker or a supervisor can add evidence")


def create_upload(db: Session, actor: Actor, data) -> tuple[Media, dict | None]:
    if data.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"Unsupported file type {data.content_type}. Allowed: {', '.join(sorted(ALLOWED_TYPES))}")
    if data.size_bytes > max_bytes_for(data.content_type):
        raise HTTPException(413, f"File exceeds the {max_bytes_for(data.content_type) // (1024 * 1024)} MB limit")
    entity = check_entity_access(db, actor, data.entity_type, data.entity_id, write=True)
    if data.entity_type == "maintenance_task":
        _check_evidence_allowed(db, actor, entity, data.evidence_type)
    if data.client_ref:
        existing = db.scalar(select(Media).where(Media.uploaded_by == actor.id, Media.client_ref == data.client_ref))
        if existing:  # idempotent retry from the offline queue
            upload = None
            if existing.status in (MediaStatus.PENDING, MediaStatus.UPLOADING):
                upload = get_storage().upload_url(existing.storage_key, existing.content_type, existing.expected_sha256)
            return existing, upload
    replaces = None
    if data.replaces_media_id:
        replaces = db.get(Media, data.replaces_media_id)
        if not replaces or replaces.tenant_id != actor.tenant_id or replaces.entity_id != data.entity_id:
            raise HTTPException(422, "Media to replace not found on this record")
        _ensure_mutable(db, actor, replaces)
    media_id = uuid.uuid4()
    ext = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/heic": "heic",
        "video/mp4": "mp4",
        "video/quicktime": "mov",
        "video/webm": "webm",
        "application/pdf": "pdf",
    }[data.content_type]
    key = f"{actor.tenant_id}/{data.entity_type}/{data.entity_id}/{media_id}.{ext}"
    retention, hold = _retention(db, actor.tenant_id, data.entity_type)
    m = Media(
        id=media_id,
        tenant_id=actor.tenant_id,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        evidence_type=data.evidence_type,
        stage=data.stage,
        uploaded_by=actor.id,
        client_ref=data.client_ref,
        captured_at=data.captured_at,
        latitude=data.latitude,
        longitude=data.longitude,
        storage_key=key,
        content_type=data.content_type,
        original_filename=data.filename,
        size_bytes=data.size_bytes,
        expected_sha256=data.sha256,
        status=MediaStatus.UPLOADING,
        replaces_id=replaces.id if replaces else None,
        retention_until=retention,
        legal_hold=hold,
    )
    db.add(m)
    db.flush()
    return m, get_storage().upload_url(key, data.content_type, data.sha256)


def _fail(db: Session, m: Media, reason: str, code: int = 422):
    m.status = MediaStatus.FAILED
    m.error = reason
    audit.record(db, None, "media.processing_failed", "media", m.id, new={"error": reason}, tenant_id=m.tenant_id)
    db.commit()
    raise HTTPException(code, reason)


def finalize(db: Session, actor: Actor, m: Media, caption: str | None = None) -> Media:
    """Verify the uploaded object, hash it, scan it, thumbnail it and mark it READY."""
    if m.uploaded_by != actor.id and not actor.is_manager():
        raise HTTPException(403, "Only the uploader can complete this upload")
    if m.status == MediaStatus.READY:
        return m
    if m.status not in (MediaStatus.UPLOADING, MediaStatus.PENDING, MediaStatus.FAILED):
        raise HTTPException(409, f"Media is {m.status}")
    storage = get_storage()
    if not storage.exists(m.storage_key):
        raise HTTPException(409, "Upload not received yet")
    m.status = MediaStatus.PROCESSING
    data = storage.get(m.storage_key)
    if len(data) > max_bytes_for(m.content_type):
        _fail(db, m, "File too large")
    if not content_matches(m.content_type, data):
        _fail(db, m, "File content does not match its declared type", 415)
    digest = sha256_hex(data)
    if m.expected_sha256 and digest != m.expected_sha256:
        _fail(db, m, "Checksum mismatch: the file was altered or corrupted in transit")
    m.scan_status = scan_for_malware(data)
    if m.scan_status == "infected":
        storage.delete(m.storage_key)
        _fail(db, m, "File rejected by malware scan")
    m.sha256 = digest
    m.size_bytes = len(data)
    if ALLOWED_TYPES[m.content_type] == "image":
        thumb = make_thumbnail(data)
        if thumb:
            m.thumbnail_key = m.storage_key.rsplit(".", 1)[0] + "_thumb.jpg"
            storage.put(m.thumbnail_key, thumb, "image/jpeg")
    m.uploaded_at = utcnow()
    m.status = MediaStatus.READY
    m.error = None
    if m.replaces_id:
        old = db.get(Media, m.replaces_id)
        old.replaced_by_id = m.id
        audit.record(
            db,
            actor,
            "media.replaced",
            m.entity_type,
            m.entity_id,
            old={"media_id": old.id, "sha256": old.sha256},
            new={"media_id": m.id, "sha256": digest},
        )
    audit.record(
        db,
        actor,
        "media.uploaded",
        m.entity_type,
        m.entity_id,
        new={
            "media_id": m.id,
            "sha256": digest,
            "content_type": m.content_type,
            "size": m.size_bytes,
            "evidence_type": m.evidence_type,
            "captured_at": m.captured_at,
        },
    )
    if m.entity_type == "maintenance_task" and m.evidence_type:
        task = db.get(MaintenanceTask, m.entity_id)
        msvc.link_evidence(db, actor, task, m, m.evidence_type, caption)
    if m.entity_type == "ticket":
        from app.models import Ticket
        from app.services import tickets as tsvc

        tsvc.attach(db, actor, db.get(Ticket, m.entity_id), m, None, caption)
    db.flush()
    return m


def _ensure_mutable(db: Session, actor: Actor, m: Media):
    if m.entity_type == "maintenance_task":
        task = db.get(MaintenanceTask, m.entity_id)
        if task and task.status in (TaskStatus.COMPLETED, TaskStatus.APPROVED, TaskStatus.CLOSED):
            raise HTTPException(409, "Evidence on submitted or approved work is preserved and cannot be changed")
        if task and not (actor.is_manager() or (is_task_worker(actor, task) and task.status in msvc.EVIDENCE_STATES)):
            raise HTTPException(403, "You cannot change this evidence")
    elif m.uploaded_by != actor.id and not actor.can("settings.manage"):
        raise HTTPException(403, "Only the uploader or an administrator can change this file")
    if m.legal_hold and not actor.can("settings.manage"):
        raise HTTPException(409, "This file is under retention hold")


def delete(db: Session, actor: Actor, m: Media, reason: str):
    if m.status == MediaStatus.DELETED:
        return
    _ensure_mutable(db, actor, m)
    m.status = MediaStatus.DELETED
    m.deleted_at = utcnow()
    m.deleted_by = actor.id
    m.delete_reason = reason
    ev = db.scalar(select(MaintenanceEvidence).where(MaintenanceEvidence.media_id == m.id))
    if ev:
        ev.status = "deleted"
    # The original object is kept until retention expiry so deletions remain reviewable.
    audit.record(db, actor, "media.deleted", m.entity_type, m.entity_id, old={"media_id": m.id, "sha256": m.sha256}, new={"reason": reason})


def approved_state(db: Session, m: Media) -> bool | None:
    if m.entity_type != "maintenance_task":
        return None
    task = db.get(MaintenanceTask, m.entity_id)
    return bool(task and task.status in (TaskStatus.APPROVED, TaskStatus.CLOSED))
