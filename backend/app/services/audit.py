import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import AuditLog
from app.models.base import utcnow


def jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    return value


def snapshot(obj: Any, fields: list[str] | None = None) -> dict:
    """JSON-safe snapshot of an ORM object's columns (or a subset)."""
    cols = fields or [c.key for c in obj.__table__.columns if c.key not in ("password_hash", "invite_token_hash")]
    return {f: jsonable(getattr(obj, f)) for f in cols}


def diff(before: dict, after: dict) -> tuple[dict, dict]:
    keys = {k for k in after if before.get(k) != after.get(k)}
    return {k: before.get(k) for k in keys}, {k: after.get(k) for k in keys}


def record(
    db: Session,
    actor: Actor | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    old: dict | None = None,
    new: dict | None = None,
    tenant_id: uuid.UUID | None = None,
) -> AuditLog:
    """Append an audit entry. Audit rows are never updated or deleted by the API."""
    entry = AuditLog(
        tenant_id=tenant_id if tenant_id is not None else (actor.user.tenant_id if actor else None),
        actor_id=actor.id if actor else None,
        actor_role=actor.role if actor else "system",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        timestamp=utcnow(),
        old_value=jsonable(old) if old else None,
        new_value=jsonable(new) if new else None,
        ip=actor.ip if actor else None,
        user_agent=(actor.user_agent or "")[:300] if actor else None,
    )
    db.add(entry)
    return entry
