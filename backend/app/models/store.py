"""The online plant store on the public website (not tenant data: the store is GreenPlot's own)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Model, UTCDateTime


class StoreProduct(Model):
    """A plant (or pot) for sale. Prices are in rupees and include any tax."""

    __tablename__ = "store_products"

    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    botanical_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category: Mapped[str] = mapped_column(String(30), index=True)  # indoor, outdoor, flowering, herbs, succulents
    summary: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    # light, water, size, pot, pet_safe, care_level: shown as the care card on the plant's page
    care: Mapped[dict] = mapped_column(JSON, default=dict)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    mrp: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)  # struck-through price, when higher
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL: stock is not tracked
    image: Mapped[str] = mapped_column(String(300))  # path under the website's public folder, or a full URL
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class StoreOrder(Model):
    """A customer's order, with the bill raised for it when it is placed."""

    __tablename__ = "store_orders"

    number: Mapped[str] = mapped_column(String(30), unique=True)
    bill_number: Mapped[str] = mapped_column(String(30), unique=True)
    # The customer opens the order and its bill with a secret link; only its hash is kept.
    token_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    # pending_payment (online, not paid yet), placed, confirmed, out_for_delivery, delivered, cancelled
    status: Mapped[str] = mapped_column(String(20), index=True)
    payment_method: Mapped[str] = mapped_column(String(10))  # cod, online
    payment_status: Mapped[str] = mapped_column(String(10), default="unpaid")  # unpaid, paid, refunded
    customer_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str] = mapped_column(Text)
    area: Mapped[str] = mapped_column(String(120))
    pincode: Mapped[str] = mapped_column(String(6))
    landmark: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    provider_order_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class StoreOrderItem(Model):
    """One line of an order. Name and price are copied so the bill never changes when the catalogue does."""

    __tablename__ = "store_order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("store_orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("store_products.id", ondelete="SET NULL"), nullable=True)
    slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    quantity: Mapped[int] = mapped_column(Integer)
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2))


class StoreCounter(Model):
    """Yearly sequence for order and bill numbers (GP-ORD-2026-00001)."""

    __tablename__ = "store_counters"
    __table_args__ = (UniqueConstraint("kind", "year"),)

    kind: Mapped[str] = mapped_column(String(10))
    year: Mapped[int] = mapped_column(Integer)
    value: Mapped[int] = mapped_column(Integer, default=0)


__all__ = ["StoreCounter", "StoreOrder", "StoreOrderItem", "StoreProduct"]
