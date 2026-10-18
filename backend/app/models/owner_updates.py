import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantModel, UTCDateTime


class PlotReport(TenantModel):
    """Monthly plot health report sent to the owner: visits, photos and issues spotted."""

    __tablename__ = "plot_reports"
    __table_args__ = (UniqueConstraint("property_id", "period_start"),)

    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    storage_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    channels: Mapped[list] = mapped_column(JSON, default=list)


__all__ = ["PlotReport"]
