"""The online plant store: public catalogue and checkout, and the office's orders and products pages."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select

from app.api.v1._util import Limit, Offset, apply, paginate
from app.core.deps import DB, Perm, client_ip
from app.core.ratelimit import limiter
from app.models import StoreOrder, StoreOrderItem, StoreProduct
from app.schemas.common import ORM, Page, Stamped
from app.services import audit
from app.services import store as svc

router = APIRouter(tags=["store"])

Slug = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
Phone = Field(min_length=10, max_length=20, pattern=r"^[0-9+\-\s()]+$")


class ProductOut(Stamped):
    slug: str
    name: str
    botanical_name: str | None
    category: str
    summary: str
    description: str
    care: dict
    price: float
    mrp: float | None
    stock: int | None
    image: str
    active: bool
    sort_order: int


class ProductIn(BaseModel):
    slug: str = Slug
    name: str = Field(min_length=2, max_length=120)
    botanical_name: str | None = Field(None, max_length=120)
    category: Literal["indoor", "outdoor", "flowering", "herbs", "succulents"]
    summary: str = Field(min_length=2, max_length=300)
    description: str = Field(min_length=2, max_length=5000)
    care: dict[str, str | bool] = {}
    price: float = Field(gt=0, le=1_000_000)
    mrp: float | None = Field(None, gt=0, le=1_000_000)
    stock: int | None = Field(None, ge=0)
    image: str = Field(min_length=1, max_length=300)
    active: bool = True
    sort_order: int = 0


class ProductPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    botanical_name: str | None = Field(None, max_length=120)
    category: Literal["indoor", "outdoor", "flowering", "herbs", "succulents"] | None = None
    summary: str | None = Field(None, min_length=2, max_length=300)
    description: str | None = Field(None, min_length=2, max_length=5000)
    care: dict[str, str | bool] | None = None
    price: float | None = Field(None, gt=0, le=1_000_000)
    mrp: float | None = Field(None, gt=0, le=1_000_000)
    stock: int | None = Field(None, ge=0)
    image: str | None = Field(None, min_length=1, max_length=300)
    active: bool | None = None
    sort_order: int | None = None


class LineIn(BaseModel):
    slug: str = Slug
    quantity: int = Field(ge=1, le=svc.MAX_QTY)


class OrderIn(BaseModel):
    items: list[LineIn] = Field(min_length=1, max_length=50)
    name: str = Field(min_length=2, max_length=200)
    phone: str = Phone
    email: EmailStr | None = None
    address: str = Field(min_length=8, max_length=500)
    area: str = Field(min_length=2, max_length=120)
    pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")
    landmark: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=1000)
    payment_method: Literal["cod", "online"]
    website: str | None = Field(None, description="Honeypot; must stay empty")


class ItemOut(ORM):
    slug: str
    name: str
    unit_price: float
    quantity: int
    line_total: float


class OrderOut(Stamped):
    number: str
    bill_number: str
    status: str
    payment_method: str
    payment_status: str
    customer_name: str
    phone: str
    email: str | None
    address: str
    area: str
    pincode: str
    landmark: str | None
    notes: str | None
    subtotal: float
    delivery_fee: float
    total: float
    provider_payment_id: str | None
    paid_at: datetime | None
    delivered_at: datetime | None
    cancelled_reason: str | None
    items: list[ItemOut] = []


class AdminOrderOut(OrderOut):
    admin_note: str | None


class PlacedOut(BaseModel):
    order: OrderOut
    token: str | None  # the secret for the order link; only on the first response


class VerifyIn(BaseModel):
    razorpay_order_id: str = Field(max_length=100)
    razorpay_payment_id: str = Field(max_length=100)
    razorpay_signature: str = Field(max_length=200)


class OrderPatch(BaseModel):
    status: Literal["placed", "confirmed", "out_for_delivery", "delivered", "cancelled"] | None = None
    paid: bool | None = None
    admin_note: str | None = Field(None, max_length=2000)
    reason: str | None = Field(None, max_length=300)


def _out(db, o: StoreOrder, model=OrderOut, items: list[StoreOrderItem] | None = None):
    out = model.model_validate(o)
    out.items = [ItemOut.model_validate(i) for i in (svc.items(db, o) if items is None else items)]
    return out


def _pdf(content: bytes, name: str) -> Response:
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


# --------------------------------------------------------------------------- public


@router.get("/public/store/config")
def store_config():
    return svc.config()


@router.get("/public/store/products", response_model=list[ProductOut])
def public_products(db: DB, category: str | None = None):
    stmt = select(StoreProduct).where(StoreProduct.active.is_(True))
    if category:
        stmt = stmt.where(StoreProduct.category == category)
    return list(db.scalars(stmt.order_by(StoreProduct.sort_order, StoreProduct.name)))


@router.get("/public/store/products/{slug}", response_model=ProductOut)
def public_product(slug: str, db: DB):
    p = db.scalar(select(StoreProduct).where(StoreProduct.slug == slug, StoreProduct.active.is_(True)))
    if p is None:
        raise HTTPException(404, "Plant not found")
    return p


@router.post("/public/store/orders", response_model=PlacedOut, status_code=201)
def place_order(body: OrderIn, request: Request, db: DB, idempotency_key: str = Header(..., min_length=8, max_length=80)):
    ip = client_ip(request) or "unknown"
    if body.website:  # bots fill hidden fields
        raise HTTPException(422, "Could not place the order")
    if not limiter.allow(f"store-order:{ip}", 10, 3600):
        raise HTTPException(429, "Too many orders from this connection. Please WhatsApp us.")
    o, token = svc.place_order(db, body.model_dump(exclude={"website"}), idempotency_key, ip)
    db.commit()
    return PlacedOut(order=_out(db, o), token=token)


@router.get("/public/store/orders/{number}", response_model=OrderOut)
def customer_order(number: str, db: DB, t: str = ""):
    return _out(db, svc.order_for_customer(db, number, t))


@router.get("/public/store/orders/{number}/bill.pdf")
def customer_bill(number: str, db: DB, t: str = ""):
    from app.services.reports import store_bill_pdf

    o = svc.order_for_customer(db, number, t)
    return _pdf(store_bill_pdf(db, o), o.bill_number)


@router.post("/public/store/orders/{number}/pay")
def start_payment(number: str, db: DB, t: str = ""):
    o = svc.order_for_customer(db, number, t)
    checkout = svc.start_payment(db, o)
    db.commit()
    return checkout


@router.post("/public/store/orders/{number}/verify", response_model=OrderOut)
def verify_payment(number: str, body: VerifyIn, db: DB, t: str = ""):
    o = svc.order_for_customer(db, number, t)
    svc.verify_checkout(db, o, body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature)
    db.commit()
    return _out(db, o)


@router.post("/public/store/orders/{number}/simulate", response_model=OrderOut)
def simulate_payment(number: str, db: DB, t: str = ""):
    """Demo mode only (no Razorpay keys, not production): behave as if the payment was captured."""
    from app.services import billing

    if svc.online_payment_mode() != "demo":
        raise HTTPException(404, "Not found")
    o = svc.order_for_customer(db, number, t)
    if not o.provider_order_id:
        raise HTTPException(409, "Start the payment first")
    event = {
        "id": f"evt_{uuid.uuid4().hex[:14]}",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{uuid.uuid4().hex[:14]}",
                    "order_id": o.provider_order_id,
                    "amount": int(billing.money(o.total) * 100),
                }
            }
        },
    }
    billing.handle_webhook(db, event)
    db.commit()
    return _out(db, o)


# --------------------------------------------------------------------------- office


@router.get("/store/orders", response_model=Page[AdminOrderOut])
def list_orders(
    db: DB, actor: Perm("store.manage"), status: str | None = None, q: str | None = None, limit: int = Limit, offset: int = Offset
):
    stmt = select(StoreOrder).order_by(StoreOrder.created_at.desc())
    if status == "open":
        stmt = stmt.where(StoreOrder.status.in_(["placed", "confirmed", "out_for_delivery"]))
    elif status:
        stmt = stmt.where(StoreOrder.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(StoreOrder.number.ilike(like), StoreOrder.customer_name.ilike(like), StoreOrder.phone.ilike(like)))
    rows, total = paginate(db, stmt, limit, offset)
    items = svc.items_for(db, rows)
    return Page(items=[_out(db, o, AdminOrderOut, items[o.id]) for o in rows], total=total, limit=limit, offset=offset)


def _order(db, order_id: uuid.UUID) -> StoreOrder:
    o = db.get(StoreOrder, order_id)
    if o is None:
        raise HTTPException(404, "Order not found")
    return o


@router.patch("/store/orders/{order_id}", response_model=AdminOrderOut)
def update_order(order_id: uuid.UUID, body: OrderPatch, db: DB, actor: Perm("store.manage")):
    o = svc.update_order(db, actor, _order(db, order_id), body.status, body.paid, body.admin_note, body.reason)
    db.commit()
    return _out(db, o, AdminOrderOut)


@router.get("/store/orders/{order_id}/bill.pdf")
def order_bill(order_id: uuid.UUID, db: DB, actor: Perm("store.manage")):
    from app.services.reports import store_bill_pdf

    o = _order(db, order_id)
    return _pdf(store_bill_pdf(db, o), o.bill_number)


@router.get("/store/products", response_model=list[ProductOut])
def list_products(db: DB, actor: Perm("store.manage")):
    return list(db.scalars(select(StoreProduct).order_by(StoreProduct.sort_order, StoreProduct.name)))


@router.post("/store/products", response_model=ProductOut, status_code=201)
def create_product(body: ProductIn, db: DB, actor: Perm("store.manage")):
    if db.scalar(select(StoreProduct.id).where(StoreProduct.slug == body.slug)):
        raise HTTPException(409, "Another plant already uses this web address")
    p = StoreProduct(**body.model_dump())
    db.add(p)
    db.flush()
    audit.record(db, actor, "store.product_created", "store_product", p.id, new={"slug": p.slug, "price": p.price})
    db.commit()
    return p


@router.patch("/store/products/{product_id}", response_model=ProductOut)
def update_product(product_id: uuid.UUID, body: ProductPatch, db: DB, actor: Perm("store.manage")):
    p = db.get(StoreProduct, product_id)
    if p is None:
        raise HTTPException(404, "Plant not found")
    # Only the botanical name, MRP and stock can be cleared (null stock means it is not tracked).
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k in ("botanical_name", "mrp", "stock")}
    before = audit.snapshot(p, list(data))
    apply(p, data)
    audit.record(db, actor, "store.product_updated", "store_product", p.id, old=before, new=audit.jsonable(data))
    db.commit()
    return p
