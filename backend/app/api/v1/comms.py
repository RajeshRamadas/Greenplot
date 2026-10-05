import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, or_, select

from app.api.v1._util import Limit, Offset, paginate, user_names
from app.core.deps import DB, CurrentActor, Perm
from app.models import AuditLog, Notice, Notification, PushSubscription
from app.models.base import utcnow
from app.models.enums import Role
from app.schemas.common import Message, Page
from app.schemas.operations import AuditOut, NoticeIn, NoticeOut, NotificationOut, PushSubscriptionIn
from app.services import audit, notifications
from app.services.access import get_scoped, tenant_select

router = APIRouter(tags=["communication"])

AUDIENCE_ROLES = {
    "all": [Role.RESIDENT, Role.GUARD, Role.STAFF, Role.SUPERVISOR, Role.VENDOR, Role.LAYOUT_ADMIN],
    "residents": [Role.RESIDENT],
    "staff": [Role.STAFF, Role.SUPERVISOR],
    "guards": [Role.GUARD],
}


def _audiences_for(role: str) -> list[str]:
    return [a for a, roles in AUDIENCE_ROLES.items() if role in roles]


# ------------------------------------------------------------------ notices


@router.get("/notices", response_model=Page[NoticeOut])
def list_notices(
    db: DB, actor: Perm("notices.read"), kind: str | None = None, include_expired: bool = False, limit: int = Limit, offset: int = Offset
):
    now = utcnow()
    stmt = tenant_select(Notice, actor).order_by(Notice.pinned.desc(), Notice.published_at.desc())
    if not actor.can("notices.manage"):
        stmt = stmt.where(Notice.audience.in_(_audiences_for(actor.role)), or_(Notice.starts_at.is_(None), Notice.starts_at <= now))
    if not include_expired:
        stmt = stmt.where(or_(Notice.ends_at.is_(None), Notice.ends_at >= now))
    if kind:
        stmt = stmt.where(Notice.kind == kind)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/notices", response_model=NoticeOut, status_code=201)
def publish_notice(body: NoticeIn, db: DB, actor: Perm("notices.manage")):
    allowed = {"in_app", "push", "sms", "whatsapp", "email"}
    if set(body.channels) - allowed:
        raise HTTPException(422, f"Channels must be among {sorted(allowed)}")
    n = Notice(tenant_id=actor.tenant_id, published_by=actor.id, published_at=utcnow(), **body.model_dump())
    db.add(n)
    db.flush()
    recipients = notifications.users_with_roles(db, actor.tenant_id, AUDIENCE_ROLES[body.audience])
    notifications.notify(
        db,
        actor.tenant_id,
        recipients,
        "announcement",
        f"{body.kind.title()}: {body.title}",
        body.body[:500],
        "notice",
        n.id,
        channels=list(dict.fromkeys(["in_app", *body.channels])),
    )
    audit.record(
        db, actor, "notice.published", "notice", n.id, new={"title": n.title, "audience": n.audience, "recipients": len(recipients)}
    )
    db.commit()
    return n


@router.delete("/notices/{notice_id}", status_code=204)
def withdraw_notice(notice_id: uuid.UUID, db: DB, actor: Perm("notices.manage")):
    n = get_scoped(db, Notice, notice_id, actor, "Notice")
    n.deleted_at = utcnow()
    audit.record(db, actor, "notice.withdrawn", "notice", n.id, old={"title": n.title})
    db.commit()


# ------------------------------------------------------------------ notifications


@router.get("/notifications", response_model=Page[NotificationOut])
def my_notifications(db: DB, actor: CurrentActor, unread: bool = False, limit: int = Limit, offset: int = Offset):
    stmt = select(Notification).where(Notification.user_id == actor.id).order_by(Notification.created_at.desc())
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/notifications/unread-count")
def unread_count(db: DB, actor: CurrentActor):
    return {
        "count": db.scalar(
            select(func.count()).select_from(Notification).where(Notification.user_id == actor.id, Notification.read_at.is_(None))
        )
    }


@router.post("/notifications/read", response_model=Message)
def mark_read(db: DB, actor: CurrentActor, ids: list[uuid.UUID] | None = None):
    stmt = select(Notification).where(Notification.user_id == actor.id, Notification.read_at.is_(None))
    if ids:
        stmt = stmt.where(Notification.id.in_(ids))
    now = utcnow()
    for n in db.scalars(stmt):
        n.read_at = now
    db.commit()
    return Message(message="ok")


@router.post("/notifications/push-subscriptions", response_model=Message, status_code=201)
def subscribe_push(body: PushSubscriptionIn, db: DB, actor: CurrentActor):
    existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if existing:
        existing.user_id, existing.keys, existing.tenant_id = actor.id, body.keys, actor.tenant_id
    else:
        db.add(PushSubscription(tenant_id=actor.tenant_id, user_id=actor.id, endpoint=body.endpoint, keys=body.keys))
    db.commit()
    return Message(message="subscribed")


# ------------------------------------------------------------------ audit


@router.get("/audit", response_model=Page[AuditOut])
def audit_log(
    db: DB,
    actor: Perm("audit.read"),
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = select(AuditLog).where(AuditLog.tenant_id == actor.tenant_id).order_by(AuditLog.timestamp.desc())
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    if date_from:
        stmt = stmt.where(AuditLog.timestamp >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.timestamp <= date_to)
    items, total = paginate(db, stmt, limit, offset)
    names = user_names(db, (r.actor_id for r in items))
    return Page(
        items=[AuditOut.model_validate(r).model_copy(update={"actor_name": names.get(r.actor_id)}) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )
