import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, TypeDecorator, Uuid
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC timestamps on every backend (SQLite has no timezone support)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, datetime):
            value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
            if dialect.name == "sqlite":
                value = value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


class Model(Base):
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)


class TenantModel(Model):
    """Every tenant-owned record carries tenant_id (requirements §25)."""

    __abstract__ = True

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)


class SoftDelete:
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
