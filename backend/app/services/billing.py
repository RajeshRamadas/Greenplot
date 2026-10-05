"""Dues, payments and the payment gateway boundary (requirements §19).

The gateway adapter follows Razorpay's order + webhook model (HMAC-SHA256 over the
raw body). Card data never touches GreenPlot: the provider's checkout collects it.
"""

import calendar
import hashlib
import hmac
import secrets
import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import Actor
from app.models import AuditLog, BillingPlan, Invoice, Payment, PaymentWebhookEvent, Property
from app.models.base import utcnow
from app.models.enums import BillingBasis, InvoiceStatus, PaymentStatus
from app.services import audit, notifications
from app.services.numbering import next_number

TWO = Decimal("0.01")


def money(x) -> Decimal:
    return Decimal(str(x or 0)).quantize(TWO, rounding=ROUND_HALF_UP)


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def amount_for(plan: BillingPlan, prop: Property) -> Decimal | None:
    rate = money(plan.rate)
    basis = BillingBasis(plan.basis)
    if basis in (BillingBasis.PER_PLOT, BillingBasis.FIXED):
        return rate
    if basis == BillingBasis.PER_UNIT:
        return money(rate * (prop.units or 1))
    if basis == BillingBasis.PER_SQFT:
        return money(rate * Decimal(str(prop.area_sqft))) if prop.area_sqft else None
    if basis == BillingBasis.CUSTOM:
        v = (plan.custom_amounts or {}).get(str(prop.id))
        return money(v) if v is not None else None
    return None


def generate_invoices(
    db: Session, actor: Actor, plan: BillingPlan, period_start: date, property_ids=None
) -> tuple[list[Invoice], list[str]]:
    period_end = add_months(period_start, plan.frequency_months) - timedelta(days=1)
    stmt = select(Property).where(Property.tenant_id == plan.tenant_id, Property.deleted_at.is_(None))
    if property_ids:
        stmt = stmt.where(Property.id.in_(property_ids))
    created, skipped = [], []
    for prop in db.scalars(stmt.order_by(Property.plot_number)):
        exists = db.scalar(
            select(Invoice.id).where(Invoice.plan_id == plan.id, Invoice.property_id == prop.id, Invoice.period_start == period_start)
        )
        if exists:
            skipped.append(f"{prop.code}: already billed")
            continue
        amount = amount_for(plan, prop)
        if amount is None or amount <= 0:
            skipped.append(f"{prop.code}: no amount for {plan.basis}")
            continue
        inv = Invoice(
            tenant_id=plan.tenant_id,
            number=next_number(db, plan.tenant_id, "INV"),
            property_id=prop.id,
            plan_id=plan.id,
            description=f"{plan.name} · {period_start:%b %Y}" + (f" – {period_end:%b %Y}" if plan.frequency_months > 1 else ""),
            period_start=period_start,
            period_end=period_end,
            amount=amount,
            amount_paid=Decimal("0"),
            due_date=period_start + timedelta(days=plan.due_days),
            status=InvoiceStatus.UNPAID,
        )
        db.add(inv)
        created.append(inv)
        notifications.notify(
            db, plan.tenant_id, [prop.owner_user_id], "payment_due", f"Dues raised: ₹{amount}", inv.description, "invoice", None
        )
    db.flush()
    audit.record(
        db,
        actor,
        "billing.invoices_generated",
        "billing_plan",
        plan.id,
        new={"period_start": period_start, "created": len(created), "skipped": len(skipped)},
    )
    return created, skipped


def _apply_payment(db: Session, payment: Payment, actor: Actor | None):
    inv = db.get(Invoice, payment.invoice_id)
    inv.amount_paid = money(Decimal(str(inv.amount_paid)) + money(payment.amount))
    inv.status = InvoiceStatus.PAID if money(inv.amount_paid) >= money(inv.amount) else InvoiceStatus.PARTIAL
    payment.status = PaymentStatus.SUCCEEDED
    payment.paid_at = payment.paid_at or utcnow()
    payment.receipt_number = payment.receipt_number or next_number(db, payment.tenant_id, "RCT")
    audit.record(
        db,
        actor,
        "payment.succeeded",
        "payment",
        payment.id,
        new={"invoice": inv.number, "amount": payment.amount, "receipt": payment.receipt_number, "invoice_status": inv.status},
        tenant_id=payment.tenant_id,
    )
    prop = db.get(Property, inv.property_id)
    notifications.notify(
        db,
        payment.tenant_id,
        [prop.owner_user_id, payment.recorded_by],
        "payment_success",
        f"Payment received · {payment.receipt_number}",
        f"₹{payment.amount} for {inv.description}",
        "payment",
        payment.id,
    )


def outstanding(inv: Invoice) -> Decimal:
    return money(Decimal(str(inv.amount)) - Decimal(str(inv.amount_paid)))


def create_online_payment(db: Session, actor: Actor, inv: Invoice, amount: Decimal | None, idem_key: str) -> Payment:
    existing = db.scalar(select(Payment).where(Payment.tenant_id == inv.tenant_id, Payment.idempotency_key == idem_key))
    if existing:
        return existing
    if inv.status in (InvoiceStatus.PAID, InvoiceStatus.WAIVED):
        raise HTTPException(409, f"Invoice is {inv.status}")
    due = outstanding(inv)
    amount = money(amount) if amount else due
    if amount > due:
        raise HTTPException(422, f"Amount exceeds the outstanding ₹{due}")
    p = Payment(
        tenant_id=inv.tenant_id,
        invoice_id=inv.id,
        property_id=inv.property_id,
        amount=amount,
        method="online",
        provider=get_settings().payment_provider,
        provider_order_id=f"order_{secrets.token_hex(8)}",
        status=PaymentStatus.CREATED,
        idempotency_key=idem_key,
        recorded_by=actor.id,
    )
    db.add(p)
    db.flush()
    audit.record(
        db, actor, "payment.order_created", "payment", p.id, new={"invoice": inv.number, "amount": amount, "order": p.provider_order_id}
    )
    return p


def checkout_payload(p: Payment) -> dict:
    return {
        "provider": p.provider,
        "order_id": p.provider_order_id,
        "amount_paise": int(money(p.amount) * 100),
        "currency": "INR",
        "note": "Complete payment in the provider's hosted checkout; card data never reaches GreenPlot.",
    }


def record_offline_payment(db: Session, actor: Actor, inv: Invoice, amount, method, reference, paid_at, idem_key: str) -> Payment:
    existing = db.scalar(select(Payment).where(Payment.tenant_id == inv.tenant_id, Payment.idempotency_key == idem_key))
    if existing:
        return existing
    if inv.status in (InvoiceStatus.PAID, InvoiceStatus.WAIVED):
        raise HTTPException(409, f"Invoice is {inv.status}")
    if money(amount) > outstanding(inv):
        raise HTTPException(422, f"Amount exceeds the outstanding ₹{outstanding(inv)}")
    p = Payment(
        tenant_id=inv.tenant_id,
        invoice_id=inv.id,
        property_id=inv.property_id,
        amount=money(amount),
        method=method,
        reference=reference,
        status=PaymentStatus.CREATED,
        idempotency_key=idem_key,
        recorded_by=actor.id,
        paid_at=paid_at,
        reconciled_at=utcnow(),
    )
    db.add(p)
    db.flush()
    _apply_payment(db, p, actor)
    return p


def verify_signature(raw_body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    expected = hmac.new(get_settings().payment_webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def sign_payload(raw_body: bytes) -> str:
    return hmac.new(get_settings().payment_webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()


def handle_webhook(db: Session, event: dict) -> str:
    """Process a verified gateway event exactly once."""
    event_id = event.get("id") or event.get("event_id")
    if not event_id:
        raise HTTPException(400, "Event id missing")
    if db.scalar(select(PaymentWebhookEvent).where(PaymentWebhookEvent.event_id == event_id)):
        return "duplicate"
    row = PaymentWebhookEvent(provider=get_settings().payment_provider, event_id=event_id, event_type=event.get("event", ""), payload=event)
    db.add(row)
    entity = (((event.get("payload") or {}).get("payment") or {}).get("entity")) or {}
    order_id, pay_id = entity.get("order_id"), entity.get("id")
    p = db.scalar(select(Payment).where(Payment.provider_order_id == order_id)) if order_id else None
    if p is None:
        row.result = "unknown_order"
    elif event.get("event") == "payment.captured":
        if p.status == PaymentStatus.SUCCEEDED:
            row.result = "already_succeeded"
        elif int(entity.get("amount", -1)) != int(money(p.amount) * 100):
            row.result = "amount_mismatch"
            audit.record(
                db,
                None,
                "payment.amount_mismatch",
                "payment",
                p.id,
                new={"event": event_id, "amount": entity.get("amount")},
                tenant_id=p.tenant_id,
            )
        else:
            p.provider_payment_id = pay_id
            p.reconciled_at = utcnow()
            _apply_payment(db, p, None)
            row.result = "applied"
    elif event.get("event") == "payment.failed":
        if p.status != PaymentStatus.SUCCEEDED:
            p.status = PaymentStatus.FAILED
            audit.record(db, None, "payment.failed", "payment", p.id, new={"event": event_id}, tenant_id=p.tenant_id)
        row.result = "failed"
    else:
        row.result = "ignored"
    row.processed_at = utcnow()
    return row.result


def reconciliation(db: Session, tenant_id: uuid.UUID) -> dict:
    """Payments whose state needs attention: stale orders and invoices whose totals disagree."""
    stale_cutoff = utcnow() - timedelta(hours=24)
    stale = list(
        db.scalars(
            select(Payment).where(
                Payment.tenant_id == tenant_id, Payment.status == PaymentStatus.CREATED, Payment.created_at < stale_cutoff
            )
        )
    )
    mismatched = []
    for inv in db.scalars(select(Invoice).where(Invoice.tenant_id == tenant_id, Invoice.deleted_at.is_(None))):
        paid = sum(
            (
                money(p.amount)
                for p in db.scalars(select(Payment).where(Payment.invoice_id == inv.id, Payment.status == PaymentStatus.SUCCEEDED))
            ),
            Decimal("0"),
        )
        if paid != money(inv.amount_paid):
            mismatched.append({"invoice": inv.number, "recorded_paid": float(inv.amount_paid), "payments_total": float(paid)})
    return {
        "stale_orders": [
            {"payment_id": p.id, "order_id": p.provider_order_id, "amount": float(p.amount), "created_at": p.created_at} for p in stale
        ],
        "invoice_mismatches": mismatched,
    }


def refresh_overdue(db: Session, tenant_id: uuid.UUID | None = None) -> int:
    """Notify owners of dues that passed their due date (once per invoice)."""
    stmt = select(Invoice).where(
        Invoice.status.in_([InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL]), Invoice.due_date < date.today(), Invoice.deleted_at.is_(None)
    )
    if tenant_id:
        stmt = stmt.where(Invoice.tenant_id == tenant_id)
    count = 0
    for inv in db.scalars(stmt):
        prop = db.get(Property, inv.property_id)
        already = db.scalar(
            select(AuditLog.id).where(
                AuditLog.entity_type == "invoice", AuditLog.entity_id == inv.id, AuditLog.action == "billing.overdue_reminder"
            )
        )
        if already:
            continue
        notifications.notify(
            db,
            inv.tenant_id,
            [prop.owner_user_id],
            "payment_due",
            f"Overdue: {inv.number}",
            f"₹{outstanding(inv)} was due on {inv.due_date:%d %b %Y}",
            "invoice",
            inv.id,
        )
        audit.record(db, None, "billing.overdue_reminder", "invoice", inv.id, tenant_id=inv.tenant_id)
        count += 1
    return count
