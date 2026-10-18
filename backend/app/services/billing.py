"""Dues, payments and the payment gateway boundary (requirements §19).

Online payments use Razorpay: the API creates an order (POST /v1/orders), the browser
opens Razorpay Checkout for it, and the payment is confirmed twice, by the checkout's
signed response (POST /payments/{id}/verify) and by the signed webhook, whichever
comes first. Card data never touches GreenPlot: the provider's checkout collects it.
Without GP_RAZORPAY_KEY_ID / GP_RAZORPAY_KEY_SECRET orders are local placeholders.

Every maintenance job on a property is billed to its owner (requirements §19 + job
payments): the job's invoice is raised when the job is created and the job closes only
once that invoice is paid or waived.
"""

import base64
import calendar
import hashlib
import hmac
import json
import logging
import secrets
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import Actor
from app.models import AuditLog, BillingPlan, Invoice, MaintenanceTask, Payment, PaymentWebhookEvent, Property, Subscription, User
from app.models.base import utcnow
from app.models.enums import BillingBasis, InvoiceStatus, PaymentStatus, SubscriptionStatus
from app.services import audit, notifications
from app.services.numbering import next_number

log = logging.getLogger("greenplot.payments")

TWO = Decimal("0.01")


# --------------------------------------------------------------------------- Razorpay API


class GatewayError(Exception):
    pass


_transport: Callable[[str, str, dict | None], dict] | None = None


def set_transport(fn: Callable[[str, str, dict | None], dict] | None) -> None:
    """Override the HTTP call (tests). fn(method, path, payload) -> response JSON."""
    global _transport
    _transport = fn


def gateway_live() -> bool:
    s = get_settings()
    return _transport is not None or bool(s.razorpay_key_id and s.razorpay_key_secret)


def _gateway(method: str, path: str, payload: dict | None = None) -> dict:
    if _transport is not None:
        return _transport(method, path, payload)
    s = get_settings()
    auth = base64.b64encode(f"{s.razorpay_key_id}:{s.razorpay_key_secret}".encode()).decode()
    req = urllib.request.Request(
        f"{s.razorpay_api_url.rstrip('/')}/{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 - fixed https endpoint from settings
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise GatewayError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise GatewayError(str(e)) from e


def _locked_invoice(db: Session, invoice_id) -> Invoice:
    """The invoice, row-locked and re-read, so payments and charge changes see each other's writes."""
    return db.get(Invoice, invoice_id, with_for_update=True, populate_existing=True)


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
    subscribed = set(
        db.scalars(
            select(Subscription.property_id).where(Subscription.plan_id == plan.id, Subscription.status == SubscriptionStatus.ACTIVE)
        )
    )
    for prop in db.scalars(stmt.order_by(Property.plot_number)):
        if prop.id in subscribed:
            skipped.append(f"{prop.code}: billed by its subscription")
            continue
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
    inv = _locked_invoice(db, payment.invoice_id)
    # Money that reached the gateway is always recorded; anything beyond the bill is flagged for a refund.
    excess = money(payment.amount) - (Decimal("0") if inv.status == InvoiceStatus.WAIVED else max(outstanding(inv), Decimal("0")))
    inv.amount_paid = money(Decimal(str(inv.amount_paid)) + money(payment.amount))
    if inv.status != InvoiceStatus.WAIVED:
        inv.status = InvoiceStatus.PAID if money(inv.amount_paid) >= money(inv.amount) else InvoiceStatus.PARTIAL
    if excess > 0:
        audit.record(
            db, actor, "payment.overpaid", "payment", payment.id, new={"invoice": inv.number, "excess": excess}, tenant_id=payment.tenant_id
        )
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
    if inv.status == InvoiceStatus.PAID:
        _on_job_invoice_settled(db, inv, actor)


def outstanding(inv: Invoice) -> Decimal:
    return money(Decimal(str(inv.amount)) - Decimal(str(inv.amount_paid)))


def create_online_payment(db: Session, actor: Actor, inv: Invoice, amount: Decimal | None, idem_key: str) -> Payment:
    existing = db.scalar(select(Payment).where(Payment.tenant_id == inv.tenant_id, Payment.idempotency_key == idem_key))
    if existing:
        return existing
    if inv.status in (InvoiceStatus.PAID, InvoiceStatus.WAIVED):
        raise HTTPException(409, f"Invoice is {inv.status}")
    due = outstanding(inv)
    if due <= 0:
        raise HTTPException(409, "Nothing is due on this bill")
    amount = money(amount) if amount else due
    if amount > due:
        raise HTTPException(422, f"Amount exceeds the outstanding ₹{due}")
    if not gateway_live() and get_settings().environment == "production":
        raise HTTPException(503, "Online payments are not set up yet; please pay the association directly")
    if gateway_live():
        try:
            order = _gateway(
                "POST",
                "orders",
                {
                    "amount": int(amount * 100),
                    "currency": "INR",
                    "receipt": inv.number[:40],
                    "notes": {"invoice": inv.number, "tenant": str(inv.tenant_id)},
                },
            )
            if not order.get("id"):
                raise GatewayError(f"order response without an id: {str(order)[:200]}")
        except GatewayError as e:
            log.warning("razorpay order failed for %s: %s", inv.number, e)
            raise HTTPException(502, "The payment provider is unavailable; please try again shortly") from e
        order_id = order["id"]
    else:
        order_id = f"order_{secrets.token_hex(8)}"
    p = Payment(
        tenant_id=inv.tenant_id,
        invoice_id=inv.id,
        property_id=inv.property_id,
        amount=amount,
        method="online",
        provider=get_settings().payment_provider,
        provider_order_id=order_id,
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


def checkout_payload(db: Session, p: Payment) -> dict:
    """Options for Razorpay Checkout. key_id is None when no gateway is configured (demo mode)."""
    s = get_settings()
    inv = db.get(Invoice, p.invoice_id)
    payer = db.get(User, p.recorded_by) if p.recorded_by else None
    return {
        "provider": p.provider,
        "key_id": s.razorpay_key_id if gateway_live() else None,
        "order_id": p.provider_order_id,
        "amount_paise": int(money(p.amount) * 100),
        "currency": "INR",
        "name": s.payment_brand_name,
        "description": inv.description if inv else None,
        "prefill": {
            "name": payer.full_name if payer else None,
            "email": payer.email if payer else None,
            "contact": payer.phone if payer else None,
        },
        "note": "Complete payment in the provider's hosted checkout; card data never reaches GreenPlot.",
    }


def verify_checkout(db: Session, p: Payment, order_id: str, payment_id: str, signature: str) -> str:
    """Confirm a payment from the checkout's signed response, then from the gateway itself.

    The signature is HMAC-SHA256(order_id|payment_id, key secret). It proves the checkout
    finished, but the payment is applied only once the gateway reports it captured for the
    full amount; an authorized payment is captured here.
    """
    if p.status == PaymentStatus.SUCCEEDED:
        return "already_succeeded"
    if order_id != p.provider_order_id:
        raise HTTPException(422, "Order does not match this payment")
    secret = get_settings().razorpay_key_secret or ""
    expected = hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(expected, signature or ""):
        raise HTTPException(401, "Invalid payment signature")
    paise = int(money(p.amount) * 100)
    try:
        remote = _gateway("GET", f"payments/{payment_id}")
        if remote.get("status") == "authorized":
            remote = _gateway("POST", f"payments/{payment_id}/capture", {"amount": paise, "currency": "INR"})
    except GatewayError as e:
        log.warning("razorpay verify failed for %s: %s", payment_id, e)
        raise HTTPException(502, "Could not confirm the payment with the provider; it will update once confirmed") from e
    if remote.get("order_id") != order_id or int(remote.get("amount", -1)) != paise:
        audit.record(
            db,
            None,
            "payment.amount_mismatch",
            "payment",
            p.id,
            new={"payment": payment_id, "amount": remote.get("amount")},
            tenant_id=p.tenant_id,
        )
        return "amount_mismatch"
    if remote.get("status") != "captured":
        return "pending"
    p.provider_payment_id = payment_id
    p.reconciled_at = utcnow()
    _apply_payment(db, p, None)
    return "applied"


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


DEV_WEBHOOK_SECRETS = {"", "whsec-dev", "change-me"}


def verify_signature(raw_body: bytes, signature: str | None) -> bool:
    s = get_settings()
    if not signature:
        return False
    if s.payment_webhook_secret in DEV_WEBHOOK_SECRETS and (s.environment == "production" or (s.razorpay_key_id and s.razorpay_key_secret)):
        # A sample secret is public: refuse webhooks rather than accept forgeable ones.
        log.error("payment webhook rejected: set GP_PAYMENT_WEBHOOK_SECRET to the secret from the Razorpay dashboard")
        return False
    expected = hmac.new(s.payment_webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
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
        # Money taken that the bills don't account for: refund it (or apply it by hand) in the Razorpay dashboard.
        "needs_refund": [
            {"payment_id": a.entity_id, "reason": a.action.removeprefix("payment."), "details": a.new_value, "at": a.timestamp}
            for a in db.scalars(
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id, AuditLog.action.in_(["payment.overpaid", "payment.amount_mismatch"]))
                .order_by(AuditLog.timestamp.desc())
            )
        ],
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


# --------------------------------------------------------------------------- job payments


def job_payment_required(db: Session, tenant_id: uuid.UUID) -> bool:
    from app.services.maintenance import tenant_setting

    return bool(tenant_setting(db, tenant_id, "job_payment_required", True))


def job_invoice(db: Session, task: MaintenanceTask) -> Invoice | None:
    return db.scalar(select(Invoice).where(Invoice.maintenance_task_id == task.id, Invoice.deleted_at.is_(None)))


def raise_job_invoice(db: Session, actor: Actor | None, task: MaintenanceTask, charge) -> Invoice | None:
    """Bill a new job to its property's owner. Jobs with no property are the association's own cost."""
    if not task.property_id or not job_payment_required(db, task.tenant_id):
        return None
    inv = Invoice(
        tenant_id=task.tenant_id,
        number=next_number(db, task.tenant_id, "INV"),
        property_id=task.property_id,
        maintenance_task_id=task.id,
        description=f"Job {task.number} · {task.title}"[:300],
        amount=money(charge),
        amount_paid=Decimal("0"),
        due_date=date.today() + timedelta(days=get_settings().job_payment_due_days),
        status=InvoiceStatus.UNPAID,
    )
    db.add(inv)
    db.flush()
    audit.record(
        db,
        actor,
        "billing.job_invoice_created",
        "invoice",
        inv.id,
        new={"job": task.number, "amount": inv.amount},
        tenant_id=task.tenant_id,
    )
    if inv.amount > 0:
        prop = db.get(Property, task.property_id)
        notifications.notify(
            db, task.tenant_id, [prop.owner_user_id], "payment_due", f"Job charge: ₹{inv.amount}", inv.description, "invoice", inv.id
        )
    return inv


def set_job_charge(db: Session, actor: Actor, task: MaintenanceTask, charge) -> Invoice | None:
    """Change what a job costs the owner, until it is settled."""
    inv = job_invoice(db, task)
    if inv is None:
        return raise_job_invoice(db, actor, task, charge)
    inv = _locked_invoice(db, inv.id)
    charge = money(charge)
    if inv.status in (InvoiceStatus.PAID, InvoiceStatus.WAIVED):
        if charge == money(inv.amount):
            return inv
        raise HTTPException(409, f"The job's bill is already {inv.status}")
    if charge < money(inv.amount_paid):
        raise HTTPException(422, f"₹{money(inv.amount_paid)} is already paid; the charge cannot be lower")
    _void_open_checkouts(db, inv)
    old = money(inv.amount)
    inv.amount = charge
    if money(inv.amount_paid) > 0:
        inv.status = InvoiceStatus.PAID if money(inv.amount_paid) >= charge else InvoiceStatus.PARTIAL
    audit.record(
        db, actor, "billing.job_charge_changed", "invoice", inv.id, old={"amount": old}, new={"amount": charge, "job": task.number}
    )
    if charge != old and outstanding(inv) > 0:
        prop = db.get(Property, inv.property_id)
        notifications.notify(
            db,
            inv.tenant_id,
            [prop.owner_user_id],
            "payment_due",
            f"Job charge: ₹{charge}",
            f"{inv.description} · ₹{outstanding(inv)} due by {inv.due_date:%d %b %Y}",
            "invoice",
            inv.id,
        )
    if inv.status == InvoiceStatus.PAID:
        _on_job_invoice_settled(db, inv, actor)
    return inv


def job_payment_block(db: Session, task: MaintenanceTask) -> str | None:
    """Why the job cannot close yet, or None when its payment is settled (or not needed)."""
    inv = job_invoice(db, task)
    if inv is None:
        if task.property_id and job_payment_required(db, task.tenant_id):
            return "This job has no bill yet; set its charge first"
        return None
    if inv.status in (InvoiceStatus.PAID, InvoiceStatus.WAIVED):
        return None
    if money(inv.amount) <= 0:
        return "Set the job's charge, or waive it if the job is free"
    return f"Waiting for payment of ₹{outstanding(inv)} ({inv.number})"


def job_payment_summary(db: Session, task: MaintenanceTask) -> dict | None:
    inv = job_invoice(db, task)
    if inv is None:
        return None
    return {
        "invoice_id": inv.id,
        "invoice_number": inv.number,
        "amount": float(inv.amount),
        "amount_paid": float(inv.amount_paid),
        "status": inv.status,
        "due_date": inv.due_date,
        "blocking": job_payment_block(db, task),
    }


def _on_job_invoice_settled(db: Session, inv: Invoice, actor: Actor | None) -> None:
    """A paid or waived job bill closes an approved job (when approval normally auto-closes)."""
    if not inv.maintenance_task_id:
        return
    from app.models.enums import TaskStatus
    from app.services import maintenance as msvc

    task = db.get(MaintenanceTask, inv.maintenance_task_id)
    if task and task.status == TaskStatus.APPROVED and msvc.tenant_setting(db, task.tenant_id, "auto_close_on_approval", True):
        msvc.close(db, actor, task)


def on_job_cancelled(db: Session, actor: Actor | None, task: MaintenanceTask) -> None:
    """A cancelled job owes nothing that is still unpaid."""
    inv = job_invoice(db, task)
    if inv and inv.status in (InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL):
        _void_open_checkouts(db, inv)
        inv.status = InvoiceStatus.WAIVED
        audit.record(
            db,
            actor,
            "billing.invoice_waived",
            "invoice",
            inv.id,
            old={"status": "unpaid"},
            new={"status": inv.status, "reason": "job cancelled"},
        )


def waive_invoice(db: Session, actor: Actor, inv: Invoice) -> None:
    inv = _locked_invoice(db, inv.id)
    if inv.status == InvoiceStatus.PAID:
        raise HTTPException(409, "Invoice is already paid")
    old = inv.status
    _void_open_checkouts(db, inv)
    inv.status = InvoiceStatus.WAIVED
    audit.record(db, actor, "billing.invoice_waived", "invoice", inv.id, old={"status": old}, new={"status": inv.status})
    _on_job_invoice_settled(db, inv, actor)


def _void_open_checkouts(db: Session, inv: Invoice) -> None:
    """Checkouts opened before the bill changed are dropped; money they still collect is flagged for a refund."""
    for p in db.scalars(select(Payment).where(Payment.invoice_id == inv.id, Payment.status == PaymentStatus.CREATED)):
        p.status = PaymentStatus.FAILED
