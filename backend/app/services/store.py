"""The online plant store: catalogue, orders, bills and payments.

Anyone can order without an account. Prices and stock always come from the catalogue here,
never from the browser. Every order gets a bill number when it is placed; the bill shows
whether it is paid. Customers pay online through Razorpay (the same keys and webhook as
layout dues, see app.services.billing) or in cash on delivery. Without Razorpay keys,
online payment runs in demo mode outside production and is switched off in production.

The customer reaches their order and bill with a secret link (number + token); only a
hash of the token is stored.
"""

import hashlib
import hmac
import logging
import secrets
import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import Actor
from app.models import StoreCounter, StoreOrder, StoreOrderItem, StoreProduct
from app.models.base import utcnow
from app.services import audit, messaging
from app.services.billing import GatewayError, _gateway, gateway_live, money

log = logging.getLogger("greenplot.store")

CATEGORIES = {
    "indoor": "Indoor plants",
    "outdoor": "Outdoor plants",
    "flowering": "Flowering plants",
    "herbs": "Herbs & kitchen garden",
    "succulents": "Succulents & cacti",
}

# Order flow. pending_payment is an online order whose payment has not arrived yet.
NEXT_STATUS = {
    "pending_payment": {"placed", "cancelled"},
    "placed": {"confirmed", "out_for_delivery", "delivered", "cancelled"},
    "confirmed": {"out_for_delivery", "delivered", "cancelled"},
    "out_for_delivery": {"delivered", "cancelled"},
    "delivered": set(),
    "cancelled": set(),
}

MAX_QTY = 20


# --------------------------------------------------------------------------- numbers & tokens


def _next(db: Session, kind: str, prefix: str) -> str:
    year = utcnow().year
    stmt = select(StoreCounter).where(StoreCounter.kind == kind, StoreCounter.year == year)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    counter = db.scalar(stmt)
    if counter is None:
        counter = StoreCounter(kind=kind, year=year, value=0)
        db.add(counter)
    counter.value += 1
    db.flush()
    return f"{prefix}-{year}-{counter.value:05d}"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def order_for_customer(db: Session, number: str, token: str | None) -> StoreOrder:
    """The order the secret link points at. A wrong token looks the same as a missing order."""
    o = db.scalar(select(StoreOrder).where(StoreOrder.number == number))
    if o is None or not token or not hmac.compare_digest(o.token_hash, _hash(token)):
        raise HTTPException(404, "Order not found")
    return o


def order_link(o: StoreOrder, token: str) -> str:
    return f"{get_settings().app_url}/store/order/{o.number}?t={token}"


# --------------------------------------------------------------------------- pricing


def delivery_fee(subtotal: Decimal) -> Decimal:
    s = get_settings()
    return Decimal("0") if subtotal >= s.store_free_delivery_over else money(s.store_delivery_fee)


def delivers_to(pincode: str) -> bool:
    prefixes = [p.strip() for p in get_settings().store_pincode_prefixes.split(",") if p.strip()]
    return any(pincode.startswith(p) for p in prefixes)


def online_payment_mode() -> str | None:
    """'live' with Razorpay keys, 'demo' without them outside production, None when online payment is off."""
    if gateway_live():
        return "live"
    return None if get_settings().environment == "production" else "demo"


def config() -> dict:
    s = get_settings()
    return {
        "delivery_fee": s.store_delivery_fee,
        "free_delivery_over": s.store_free_delivery_over,
        "cod": s.store_cod_enabled,
        "cod_limit": s.store_cod_limit,
        "online": online_payment_mode(),
        "pincode_prefixes": [p.strip() for p in s.store_pincode_prefixes.split(",") if p.strip()],
        "max_quantity": MAX_QTY,
        "categories": CATEGORIES,
    }


# --------------------------------------------------------------------------- orders


def place_order(db: Session, data: dict, idem_key: str, ip: str | None) -> tuple[StoreOrder, str | None]:
    """Create the order and its bill. Returns the order and its secret token (None for a repeated request)."""
    existing = db.scalar(select(StoreOrder).where(StoreOrder.idempotency_key == idem_key))
    if existing:
        return existing, None
    s = get_settings()
    if not delivers_to(data["pincode"]):
        raise HTTPException(422, "We deliver only within Bangalore for now. Please check the PIN code.")
    wanted: dict[str, int] = {}
    for line in data["items"]:
        wanted[line["slug"]] = wanted.get(line["slug"], 0) + line["quantity"]
    if not wanted:
        raise HTTPException(422, "Your cart is empty")
    stmt = select(StoreProduct).where(StoreProduct.slug.in_(wanted))
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    products = {p.slug: p for p in db.scalars(stmt)}
    lines, subtotal = [], Decimal("0")
    for slug, qty in wanted.items():
        p = products.get(slug)
        if p is None or not p.active:
            raise HTTPException(409, f"{p.name if p else slug} is no longer available; please remove it from your cart")
        if qty > MAX_QTY:
            raise HTTPException(422, f"You can order up to {MAX_QTY} of {p.name}; WhatsApp us for bulk orders")
        if p.stock is not None and qty > p.stock:
            raise HTTPException(409, f"Only {p.stock} of {p.name} left" if p.stock else f"{p.name} is out of stock")
        line_total = money(Decimal(str(p.price)) * qty)
        subtotal += line_total
        lines.append((p, qty, line_total))
    subtotal = money(subtotal)
    fee = delivery_fee(subtotal)
    total = money(subtotal + fee)
    method = data["payment_method"]
    if method == "cod":
        if not s.store_cod_enabled:
            raise HTTPException(422, "Cash on delivery is not available right now; please pay online")
        if total > s.store_cod_limit:
            raise HTTPException(422, f"Cash on delivery is available for orders up to ₹{s.store_cod_limit}; please pay online")
    elif online_payment_mode() is None:
        raise HTTPException(503, "Online payment is not set up yet; please choose cash on delivery")

    token = secrets.token_urlsafe(24)
    o = StoreOrder(
        number=_next(db, "ORD", "GP-ORD"),
        bill_number=_next(db, "BILL", "GP-BILL"),
        token_hash=_hash(token),
        idempotency_key=idem_key,
        status="placed" if method == "cod" else "pending_payment",
        payment_method=method,
        payment_status="unpaid",
        customer_name=data["name"].strip(),
        phone=data["phone"].strip(),
        email=data.get("email") or None,
        address=data["address"].strip(),
        area=data["area"].strip(),
        pincode=data["pincode"],
        landmark=data.get("landmark") or None,
        notes=data.get("notes") or None,
        subtotal=subtotal,
        delivery_fee=fee,
        total=total,
        ip=ip,
    )
    db.add(o)
    db.flush()
    for p, qty, line_total in lines:
        db.add(
            StoreOrderItem(
                order_id=o.id, product_id=p.id, slug=p.slug, name=p.name, unit_price=money(p.price), quantity=qty, line_total=line_total
            )
        )
        if p.stock is not None:
            p.stock -= qty
    db.flush()
    audit.record(db, None, "store.order_placed", "store_order", o.id, new={"number": o.number, "total": total, "method": method})
    if method == "cod":
        _announce(o, token)
    return o, token


def _announce(o: StoreOrder, token: str | None) -> None:
    """Tell the customer the order is in (with the link to it), and tell the office."""
    s = get_settings()
    what = f"Order {o.number} for ₹{o.total}" + (" (cash on delivery)" if o.payment_method == "cod" else " (paid online)")
    if token:
        link = order_link(o, token)
        messaging.send_link(
            o.phone,
            o.email,
            f"GreenPlot order {o.number} received",
            f"Thank you, {o.customer_name}. {what} is received. Track it and see your bill: {link}",
            link,
        )
    if s.store_orders_email:
        messaging.send_email(
            s.store_orders_email,
            f"New plant order {o.number}",
            f"{what}\n{o.customer_name}, {o.phone}\n{o.address}, {o.area} {o.pincode}\nOpen the store orders page in the app to confirm it.",
        )


def items(db: Session, o: StoreOrder) -> list[StoreOrderItem]:
    return items_for(db, [o])[o.id]


def items_for(db: Session, orders: list[StoreOrder]) -> dict[uuid.UUID, list[StoreOrderItem]]:
    """The lines of several orders in one query."""
    out: dict[uuid.UUID, list[StoreOrderItem]] = {o.id: [] for o in orders}
    if out:
        stmt = select(StoreOrderItem).where(StoreOrderItem.order_id.in_(out)).order_by(StoreOrderItem.created_at, StoreOrderItem.name)
        for i in db.scalars(stmt):
            out[i.order_id].append(i)
    return out


def _restock(db: Session, o: StoreOrder) -> None:
    for it in items(db, o):
        p = db.get(StoreProduct, it.product_id) if it.product_id else None
        if p is not None and p.stock is not None:
            p.stock += it.quantity


def update_order(
    db: Session, actor: Actor, o: StoreOrder, status: str | None, paid: bool | None, note: str | None, reason: str | None
) -> StoreOrder:
    old = {"status": o.status, "payment_status": o.payment_status}
    if status and status != o.status:
        if status not in NEXT_STATUS.get(o.status, set()):
            raise HTTPException(409, f"An order that is {o.status.replace('_', ' ')} cannot become {status.replace('_', ' ')}")
        if status == "placed" and o.payment_status != "paid":
            raise HTTPException(409, "An online order is placed once it is paid; mark it paid or switch it to cash on delivery")
        o.status = status
        if status == "delivered":
            o.delivered_at = utcnow()
            if o.payment_method == "cod" and o.payment_status == "unpaid":
                paid = True  # the cash was collected at the door
        if status == "cancelled":
            o.cancelled_reason = reason or None
            _restock(db, o)
    if paid is not None and paid != (o.payment_status == "paid"):
        if paid:
            o.payment_status, o.paid_at = "paid", o.paid_at or utcnow()
            if o.status == "pending_payment":
                o.status = "placed"
        else:
            if o.payment_method == "online":
                raise HTTPException(409, "Online payments are refunded from the Razorpay dashboard")
            o.payment_status, o.paid_at = "unpaid", None
    if note is not None:
        o.admin_note = note or None
    audit.record(
        db, actor, "store.order_updated", "store_order", o.id, old=old, new={"status": o.status, "payment_status": o.payment_status}
    )
    return o


# --------------------------------------------------------------------------- online payment


def start_payment(db: Session, o: StoreOrder) -> dict:
    """Razorpay Checkout options for the order (a gateway order is made once and reused)."""
    if o.payment_method != "online" or o.payment_status == "paid" or o.status == "cancelled":
        raise HTTPException(409, "This order has nothing to pay online")
    mode = online_payment_mode()
    if mode is None:
        raise HTTPException(503, "Online payment is not set up yet; please WhatsApp us to pay")
    if not o.provider_order_id:
        if mode == "live":
            try:
                order = _gateway(
                    "POST",
                    "orders",
                    {"amount": int(money(o.total) * 100), "currency": "INR", "receipt": o.number, "notes": {"store_order": o.number}},
                )
                if not order.get("id"):
                    raise GatewayError(f"order response without an id: {str(order)[:200]}")
            except GatewayError as e:
                log.warning("razorpay order failed for %s: %s", o.number, e)
                raise HTTPException(502, "The payment provider is unavailable; please try again shortly") from e
            o.provider_order_id = order["id"]
        else:
            o.provider_order_id = f"order_{secrets.token_hex(8)}"
        db.flush()
    s = get_settings()
    return {
        "key_id": s.razorpay_key_id if mode == "live" else None,
        "order_id": o.provider_order_id,
        "amount_paise": int(money(o.total) * 100),
        "currency": "INR",
        "name": s.payment_brand_name,
        "description": f"Plant order {o.number}",
        "prefill": {"name": o.customer_name, "email": o.email, "contact": o.phone},
    }


def _mark_paid(db: Session, o: StoreOrder, payment_id: str) -> None:
    if o.payment_status == "paid":
        return
    o.provider_payment_id = payment_id
    o.payment_status, o.paid_at = "paid", utcnow()
    if o.status == "pending_payment":
        o.status = "placed"
    elif o.status == "cancelled":
        # Paid after it was cancelled: the money has to go back.
        audit.record(db, None, "store.paid_after_cancel", "store_order", o.id, new={"number": o.number, "payment": payment_id})
    audit.record(db, None, "store.order_paid", "store_order", o.id, new={"number": o.number, "payment": payment_id, "amount": o.total})
    _announce(o, None)


def verify_checkout(db: Session, o: StoreOrder, order_id: str, payment_id: str, signature: str) -> None:
    """Confirm the checkout's signed response with Razorpay itself, as for layout dues."""
    if o.payment_status == "paid":
        return
    if not o.provider_order_id or order_id != o.provider_order_id:
        raise HTTPException(422, "Payment does not match this order")
    secret = get_settings().razorpay_key_secret or ""
    expected = hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(expected, signature or ""):
        raise HTTPException(401, "Invalid payment signature")
    paise = int(money(o.total) * 100)
    try:
        remote = _gateway("GET", f"payments/{payment_id}")
        if remote.get("status") == "authorized":
            remote = _gateway("POST", f"payments/{payment_id}/capture", {"amount": paise, "currency": "INR"})
    except GatewayError as e:
        log.warning("razorpay verify failed for %s: %s", payment_id, e)
        raise HTTPException(502, "Could not confirm the payment yet; it will show as paid once confirmed") from e
    if remote.get("order_id") != order_id or int(remote.get("amount", -1)) != paise:
        audit.record(db, None, "store.amount_mismatch", "store_order", o.id, new={"payment": payment_id, "amount": remote.get("amount")})
        raise HTTPException(409, "The payment amount does not match the order; we will contact you")
    if remote.get("status") == "captured":
        _mark_paid(db, o, payment_id)


def apply_gateway_event(db: Session, event_type: str, entity: dict) -> str | None:
    """A verified Razorpay webhook for a store order (billing.handle_webhook calls this). None if not ours."""
    order_id = entity.get("order_id")
    o = db.scalar(select(StoreOrder).where(StoreOrder.provider_order_id == order_id)) if order_id else None
    if o is None:
        return None
    if event_type == "payment.captured":
        if o.payment_status == "paid":
            return "already_succeeded"
        if int(entity.get("amount", -1)) != int(money(o.total) * 100):
            audit.record(
                db, None, "store.amount_mismatch", "store_order", o.id, new={"payment": entity.get("id"), "amount": entity.get("amount")}
            )
            return "amount_mismatch"
        _mark_paid(db, o, entity.get("id") or "")
        return "applied"
    if event_type == "payment.failed":
        return "failed"
    return "ignored"
