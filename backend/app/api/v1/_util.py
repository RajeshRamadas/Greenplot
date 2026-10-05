import uuid
from collections.abc import Iterable

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Property, User, Vendor

Limit = Query(50, ge=1, le=500)
Offset = Query(0, ge=0)


def paginate(db: Session, stmt: Select, limit: int, offset: int) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    items = list(db.scalars(stmt.limit(limit).offset(offset)).unique())
    return items, total or 0


def apply(obj, data: dict) -> None:
    for k, v in data.items():
        setattr(obj, k, v)


def user_names(db: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(wanted))).all())


def property_labels(db: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    rows = db.execute(select(Property.id, Property.plot_number, Property.code).where(Property.id.in_(wanted))).all()
    return {r.id: f"Plot {r.plot_number}" for r in rows}


def vendor_names(db: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict(db.execute(select(Vendor.id, Vendor.name).where(Vendor.id.in_(wanted))).all())
