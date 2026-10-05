import uuid
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from app.core.deps import DB, CurrentActor, Perm
from app.core.security import verify_signed_value
from app.models import Media
from app.models.enums import EvidenceType, MediaStatus
from app.schemas.common import ReasonIn
from app.schemas.maintenance import CompleteUploadIn, MediaOut, UploadUrlIn, UploadUrlOut
from app.services import media as svc
from app.services.access import check_entity_access, get_scoped
from app.services.storage import get_storage, max_bytes_for, sha256_hex

router = APIRouter(prefix="/media", tags=["media"])


def present(db, m: Media) -> MediaOut:
    out = MediaOut.model_validate(m)
    if m.status == MediaStatus.READY:
        storage = get_storage()
        out.url = storage.download_url(m.storage_key, m.original_filename)
        if m.thumbnail_key:
            out.thumbnail_url = storage.download_url(m.thumbnail_key)
    out.approved = svc.approved_state(db, m)
    return out


@router.post("/upload-url", response_model=UploadUrlOut, status_code=201)
def upload_url(body: UploadUrlIn, db: DB, actor: Perm("media.upload")):
    m, upload = svc.create_upload(db, actor, body)
    db.commit()
    return UploadUrlOut(media_id=m.id, status=m.status, upload=upload)


@router.put("/blob", include_in_schema=False)
async def put_blob(request: Request, key: str, token: str, db: DB):
    """Upload target for the local storage backend (a stand-in for a presigned S3 PUT)."""
    if not verify_signed_value(f"put:{key}", token):
        raise HTTPException(403, "Upload link is invalid or expired")
    m = db.scalar(select(Media).where(Media.storage_key == key))
    if not m or m.status not in (MediaStatus.UPLOADING, MediaStatus.PENDING, MediaStatus.FAILED):
        raise HTTPException(409, "Upload not expected")
    limit = max_bytes_for(m.content_type)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(413, "File too large")
    get_storage().put(key, bytes(body), m.content_type)
    return {"ok": True, "sha256": sha256_hex(bytes(body))}


@router.get("/blob", include_in_schema=False)
def get_blob(key: str, token: str, db: DB):
    if not verify_signed_value(f"get:{key}", token):
        raise HTTPException(403, "Link is invalid or expired")
    storage = get_storage()
    if not storage.exists(key):
        raise HTTPException(404, "Not found")
    m = db.scalar(select(Media).where((Media.storage_key == key) | (Media.thumbnail_key == key)))
    ctype = "image/jpeg" if m is None or key == m.thumbnail_key else m.content_type
    return Response(
        storage.get(key),
        media_type=ctype,
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/complete", response_model=MediaOut)
def complete(body: CompleteUploadIn, db: DB, actor: Perm("media.upload")):
    m = get_scoped(db, Media, body.media_id, actor, "Media")
    svc.finalize(db, actor, m, body.caption)
    db.commit()
    return present(db, m)


@router.post("/direct", response_model=MediaOut, status_code=201)
async def direct_upload(
    db: DB,
    actor: Perm("media.upload"),
    file: UploadFile = File(...),
    entity_type: str = Form(...),
    entity_id: uuid.UUID = Form(...),
    evidence_type: EvidenceType | None = Form(None),
    stage: str | None = Form(None),
    sha256: str | None = Form(None),
    captured_at: datetime | None = Form(None),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    client_ref: str | None = Form(None),
    caption: str | None = Form(None),
    replaces_media_id: uuid.UUID | None = Form(None),
):
    """Single-request upload for small files and the offline sync queue."""
    data = await file.read()
    req = UploadUrlIn(
        entity_type=entity_type,
        entity_id=entity_id,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=max(len(data), 1),
        sha256=sha256,
        filename=file.filename,
        evidence_type=evidence_type,
        stage=stage,
        captured_at=captured_at,
        latitude=latitude,
        longitude=longitude,
        client_ref=client_ref,
        replaces_media_id=replaces_media_id,
    )
    m, _ = svc.create_upload(db, actor, req)
    if m.status != MediaStatus.READY:
        get_storage().put(m.storage_key, data, m.content_type)
        svc.finalize(db, actor, m, caption)
    db.commit()
    return present(db, m)


@router.get("", response_model=list[MediaOut])
def list_media(
    db: DB,
    actor: CurrentActor,
    entity_type: str = Query(...),
    entity_id: uuid.UUID = Query(...),
    include_deleted: bool = False,
):
    check_entity_access(db, actor, entity_type, entity_id)
    stmt = select(Media).where(Media.tenant_id == actor.tenant_id, Media.entity_type == entity_type, Media.entity_id == entity_id)
    if not include_deleted or not actor.is_manager():
        stmt = stmt.where(Media.status != MediaStatus.DELETED)
    return [present(db, m) for m in db.scalars(stmt.order_by(Media.created_at))]


@router.get("/{media_id}", response_model=MediaOut)
def get_media(media_id: uuid.UUID, db: DB, actor: CurrentActor):
    m = get_scoped(db, Media, media_id, actor, "Media", include_deleted=actor.is_manager())
    check_entity_access(db, actor, m.entity_type, m.entity_id)
    if m.entity_type == "maintenance_task":
        from app.api.v1.maintenance import evidence_visible_to
        from app.models import MaintenanceTask

        if not evidence_visible_to(db, actor, db.get(MaintenanceTask, m.entity_id)):
            raise HTTPException(404, "Media not found")
    if m.status == MediaStatus.DELETED and not actor.is_manager():
        raise HTTPException(404, "Media not found")
    return present(db, m)


@router.delete("/{media_id}", response_model=MediaOut)
def delete_media(media_id: uuid.UUID, body: ReasonIn, db: DB, actor: CurrentActor):
    m = get_scoped(db, Media, media_id, actor, "Media")
    check_entity_access(db, actor, m.entity_type, m.entity_id)
    svc.delete(db, actor, m, body.reason)
    db.commit()
    return present(db, m)
