"""The office's own record of talking to a customer: calls, WhatsApp chats, visits, notes."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SoftDelete, TenantModel, UTCDateTime


class CustomerInteraction(TenantModel, SoftDelete):
    """One conversation or note about a customer.

    Kept against the customer's account and/or a plot, so owners recorded only by phone on a
    property still get a history. WhatsApp calls started from a ticket or job are logged here
    automatically; everything else is written by the office.
    """

    __tablename__ = "customer_interactions"

    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), index=True, nullable=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id"), index=True, nullable=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True)
    maintenance_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("maintenance_tasks.id", ondelete="SET NULL"), nullable=True
    )
    # note, phone_call, whatsapp_call, whatsapp_chat, sms, email, site_visit, meeting
    kind: Mapped[str] = mapped_column(String(20), default="note")
    direction: Mapped[str | None] = mapped_column(String(3), nullable=True)  # in, out
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    summary: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(String(300), nullable=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)


__all__ = ["CustomerInteraction"]
