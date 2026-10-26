import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Stamped
from app.schemas.maintenance import MediaOut

InteractionKind = Literal["note", "phone_call", "whatsapp_call", "whatsapp_chat", "sms", "email", "site_visit", "meeting"]


class InteractionIn(BaseModel):
    kind: InteractionKind = "note"
    direction: Literal["in", "out"] | None = None
    occurred_at: datetime | None = None  # defaults to now
    summary: str = Field(min_length=1, max_length=10000)
    outcome: str | None = Field(None, max_length=300)
    property_id: uuid.UUID | None = None
    ticket_id: uuid.UUID | None = None


class InteractionUpdate(BaseModel):
    kind: InteractionKind | None = None
    direction: Literal["in", "out"] | None = None
    occurred_at: datetime | None = None
    summary: str | None = Field(None, min_length=1, max_length=10000)
    outcome: str | None = Field(None, max_length=300)


class InteractionOut(Stamped):
    customer_id: uuid.UUID | None
    property_id: uuid.UUID | None
    ticket_id: uuid.UUID | None
    maintenance_task_id: uuid.UUID | None
    kind: str
    direction: str | None
    occurred_at: datetime
    summary: str
    outcome: str | None
    author_id: uuid.UUID | None
    author_name: str | None = None


class CustomerPlot(BaseModel):
    id: uuid.UUID
    code: str
    plot_number: str
    layout_name: str | None
    relation: str  # owner, tenant, family
    area_sqft: float | None
    status: str


class CustomerStats(BaseModel):
    tickets: int = 0
    open_tickets: int = 0
    jobs_done: int = 0
    photos: int = 0
    conversations: int = 0
    billed: float = 0
    paid: float = 0
    outstanding: float = 0
    avg_rating: float | None = None
    active_subscriptions: int = 0
    last_contact_at: datetime | None = None


class CustomerSummary(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    phone: str | None
    whatsapp_phone: str | None
    is_active: bool
    plots: list[str]
    open_tickets: int
    last_contact_at: datetime | None


class CustomerOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    phone: str | None
    whatsapp_phone: str | None  # None: same as phone
    is_active: bool
    whatsapp_opt_in: bool
    phone_verified: bool
    joined_at: datetime
    last_login_at: datetime | None
    plots: list[CustomerPlot]
    stats: CustomerStats


class CustomerEvent(BaseModel):
    """One line on the customer's history: a conversation, a job, a payment, a message..."""

    at: datetime
    kind: str
    title: str
    body: str | None = None
    status: str | None = None
    number: str | None = None
    by: str | None = None
    direction: str | None = None
    internal: bool = False  # never shown to the customer (internal notes, office-only comments)
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None


class CustomerMediaOut(MediaOut):
    source: str  # where it was taken: "Ticket GP-TKT-2026-00001", "Plot 117", "Customer file"
