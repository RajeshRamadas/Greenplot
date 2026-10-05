import json
import uuid
from datetime import date

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func, select

from app.api.v1._util import Limit, Offset, apply, paginate, property_labels
from app.core.config import get_settings
from app.core.deps import DB, CurrentActor, Perm
from app.models import BillingPlan, Expense, Invoice, Payment, Property
from app.models.base import utcnow
from app.models.enums import InvoiceStatus, PaymentStatus, Role
from app.schemas.common import Page
from app.schemas.operations import (
    ExpenseIn,
    ExpenseOut,
    GenerateIn,
    InvoiceIn,
    InvoiceOut,
    PaymentCreateIn,
    PaymentOut,
    PaymentRecordIn,
    PlanIn,
    PlanOut,
)
from app.services import audit
from app.services import billing as svc
from app.services.access import get_scoped, not_found, resident_property_ids, tenant_select
from app.services.numbering import next_number

router = APIRouter(tags=["billing"])


def _inv_out(db, invs: list[Invoice]) -> list[InvoiceOut]:
    labels = property_labels(db, (i.property_id for i in invs))
    today = date.today()
    return [
        InvoiceOut.model_validate(i).model_copy(
            update={"property_label": labels.get(i.property_id), "overdue": i.status in ("unpaid", "partial") and i.due_date < today}
        )
        for i in invs
    ]


def _get_invoice(db, actor, invoice_id) -> Invoice:
    inv = get_scoped(db, Invoice, invoice_id, actor, "Invoice")
    if actor.role == Role.RESIDENT and inv.property_id not in resident_property_ids(db, actor):
        raise not_found("Invoice")
    return inv


# ------------------------------------------------------------------ plans


@router.get("/billing/plans", response_model=list[PlanOut])
def list_plans(db: DB, actor: Perm("billing.manage")):
    return list(db.scalars(tenant_select(BillingPlan, actor).order_by(BillingPlan.name)))


@router.post("/billing/plans", response_model=PlanOut, status_code=201)
def create_plan(body: PlanIn, db: DB, actor: Perm("billing.manage")):
    p = BillingPlan(tenant_id=actor.tenant_id, **body.model_dump())
    db.add(p)
    db.flush()
    audit.record(db, actor, "billing.plan_created", "billing_plan", p.id, new=body.model_dump())
    db.commit()
    return p


@router.patch("/billing/plans/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: uuid.UUID, body: PlanIn, db: DB, actor: Perm("billing.manage")):
    p = get_scoped(db, BillingPlan, plan_id, actor, "Plan")
    before = audit.snapshot(p)
    apply(p, body.model_dump())
    old, new = audit.diff(before, audit.snapshot(p))
    audit.record(db, actor, "billing.plan_changed", "billing_plan", p.id, old=old, new=new)
    db.commit()
    return p


@router.post("/billing/generate")
def generate(body: GenerateIn, db: DB, actor: Perm("billing.manage")):
    plan = get_scoped(db, BillingPlan, body.plan_id, actor, "Plan")
    created, skipped = svc.generate_invoices(db, actor, plan, body.period_start, body.property_ids)
    db.commit()
    return {"created": len(created), "skipped": skipped, "invoices": _inv_out(db, created)}


# ------------------------------------------------------------------ invoices / dues


@router.get("/billing/invoices", response_model=Page[InvoiceOut])
def list_invoices(
    db: DB,
    actor: Perm("billing.read"),
    status: InvoiceStatus | None = None,
    property_id: uuid.UUID | None = None,
    overdue: bool | None = None,
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = tenant_select(Invoice, actor).order_by(Invoice.due_date.desc(), Invoice.number.desc())
    if actor.role == Role.RESIDENT:
        stmt = stmt.where(Invoice.property_id.in_(resident_property_ids(db, actor) or {uuid.uuid4()}))
    if status:
        stmt = stmt.where(Invoice.status == status)
    if property_id:
        stmt = stmt.where(Invoice.property_id == property_id)
    if overdue:
        stmt = stmt.where(Invoice.status.in_(["unpaid", "partial"]), Invoice.due_date < date.today())
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=_inv_out(db, items), total=total, limit=limit, offset=offset)


@router.post("/billing/invoices", response_model=InvoiceOut, status_code=201)
def create_invoice(body: InvoiceIn, db: DB, actor: Perm("billing.manage")):
    get_scoped(db, Property, body.property_id, actor, "Property")
    inv = Invoice(tenant_id=actor.tenant_id, number=next_number(db, actor.tenant_id, "INV"), amount_paid=0, **body.model_dump())
    db.add(inv)
    db.flush()
    audit.record(db, actor, "billing.invoice_created", "invoice", inv.id, new=audit.snapshot(inv))
    db.commit()
    return _inv_out(db, [inv])[0]


@router.post("/billing/invoices/{invoice_id}/waive", response_model=InvoiceOut)
def waive(invoice_id: uuid.UUID, db: DB, actor: Perm("billing.manage")):
    inv = _get_invoice(db, actor, invoice_id)
    if inv.status == InvoiceStatus.PAID:
        raise HTTPException(409, "Invoice is already paid")
    old = inv.status
    inv.status = InvoiceStatus.WAIVED
    audit.record(db, actor, "billing.invoice_waived", "invoice", inv.id, old={"status": old}, new={"status": inv.status})
    db.commit()
    return _inv_out(db, [inv])[0]


@router.get("/billing/defaulters")
def defaulters(db: DB, actor: Perm("billing.manage")):
    rows = db.execute(
        select(Invoice.property_id, func.count(Invoice.id), func.sum(Invoice.amount - Invoice.amount_paid), func.min(Invoice.due_date))
        .where(
            Invoice.tenant_id == actor.tenant_id,
            Invoice.deleted_at.is_(None),
            Invoice.status.in_(["unpaid", "partial"]),
            Invoice.due_date < date.today(),
        )
        .group_by(Invoice.property_id)
    ).all()
    labels = property_labels(db, (r[0] for r in rows))
    props = {p.id: p for p in db.scalars(select(Property).where(Property.id.in_([r[0] for r in rows])))} if rows else {}
    out = [
        {
            "property_id": pid,
            "property": labels.get(pid),
            "owner": props[pid].owner_name if pid in props else None,
            "phone": props[pid].owner_phone if pid in props else None,
            "invoices": n,
            "outstanding": float(amt or 0),
            "oldest_due": oldest,
        }
        for pid, n, amt, oldest in rows
    ]
    return sorted(out, key=lambda r: -r["outstanding"])


@router.get("/billing/summary")
def billing_summary(db: DB, actor: Perm("billing.manage")):
    base = select(Invoice).where(Invoice.tenant_id == actor.tenant_id, Invoice.deleted_at.is_(None))
    billed = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount), 0)).where(Invoice.tenant_id == actor.tenant_id, Invoice.deleted_at.is_(None))
    )
    collected = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.tenant_id == actor.tenant_id, Payment.status == PaymentStatus.SUCCEEDED
        )
    )
    expenses = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.tenant_id == actor.tenant_id, Expense.deleted_at.is_(None))
    )
    overdue = db.scalar(
        select(func.count()).select_from(base.where(Invoice.status.in_(["unpaid", "partial"]), Invoice.due_date < date.today()).subquery())
    )
    return {
        "billed": float(billed),
        "collected": float(collected),
        "outstanding": float(billed) - float(collected),
        "overdue_invoices": overdue,
        "expenses": float(expenses),
    }


# ------------------------------------------------------------------ payments


def _pay_out(p: Payment, checkout=False) -> PaymentOut:
    o = PaymentOut.model_validate(p)
    if checkout and p.status == PaymentStatus.CREATED and p.method == "online":
        o.checkout = svc.checkout_payload(p)
    return o


@router.post("/payments", response_model=PaymentOut, status_code=201)
def create_payment(
    body: PaymentCreateIn,
    db: DB,
    actor: Perm("payments.create"),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=100),
):
    """Start an online payment. The client completes it in the provider's checkout."""
    inv = _get_invoice(db, actor, body.invoice_id)
    p = svc.create_online_payment(db, actor, inv, body.amount, idempotency_key)
    db.commit()
    return _pay_out(p, checkout=True)


@router.post("/payments/record", response_model=PaymentOut, status_code=201)
def record_payment(
    body: PaymentRecordIn,
    db: DB,
    actor: Perm("payments.record"),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=100),
):
    """Record a cash / UPI / cheque / bank-transfer payment collected by the association."""
    inv = _get_invoice(db, actor, body.invoice_id)
    p = svc.record_offline_payment(db, actor, inv, body.amount, body.method, body.reference, body.paid_at, idempotency_key)
    db.commit()
    return _pay_out(p)


@router.get("/payments", response_model=Page[PaymentOut])
def list_payments(
    db: DB,
    actor: Perm("billing.read"),
    invoice_id: uuid.UUID | None = None,
    status: PaymentStatus | None = None,
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = select(Payment).where(Payment.tenant_id == actor.tenant_id).order_by(Payment.created_at.desc())
    if actor.role == Role.RESIDENT:
        stmt = stmt.where(Payment.property_id.in_(resident_property_ids(db, actor) or {uuid.uuid4()}))
    if invoice_id:
        stmt = stmt.where(Payment.invoice_id == invoice_id)
    if status:
        stmt = stmt.where(Payment.status == status)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=[_pay_out(p) for p in items], total=total, limit=limit, offset=offset)


@router.post("/payments/webhook", include_in_schema=True)
async def payment_webhook(request: Request, db: DB, x_razorpay_signature: str | None = Header(None)):
    """Gateway webhook. Verified with HMAC-SHA256 and processed idempotently by event id."""
    raw = await request.body()
    if not svc.verify_signature(raw, x_razorpay_signature):
        raise HTTPException(401, "Invalid signature")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    result = svc.handle_webhook(db, event)
    db.commit()
    return {"status": result}


@router.post("/payments/{payment_id}/simulate", response_model=PaymentOut)
def simulate_capture(payment_id: uuid.UUID, db: DB, actor: CurrentActor):
    """Development only: behave as if the gateway captured this payment (sends a signed webhook)."""
    if get_settings().environment == "production":
        raise HTTPException(404, "Not found")
    p = get_scoped(db, Payment, payment_id, actor, "Payment")
    if actor.role == Role.RESIDENT and p.property_id not in resident_property_ids(db, actor):
        raise not_found("Payment")
    event = {
        "id": f"evt_{uuid.uuid4().hex[:14]}",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {"id": f"pay_{uuid.uuid4().hex[:14]}", "order_id": p.provider_order_id, "amount": int(svc.money(p.amount) * 100)}
            }
        },
    }
    svc.handle_webhook(db, event)
    db.commit()
    return _pay_out(p)


@router.get("/payments/reconciliation")
def reconciliation(db: DB, actor: Perm("billing.manage")):
    return svc.reconciliation(db, actor.tenant_id)


@router.get("/payments/{payment_id}/receipt.pdf")
def receipt(payment_id: uuid.UUID, db: DB, actor: Perm("billing.read")):
    from app.services.reports import receipt_pdf

    p = get_scoped(db, Payment, payment_id, actor, "Payment")
    if actor.role == Role.RESIDENT and p.property_id not in resident_property_ids(db, actor):
        raise not_found("Payment")
    if p.status != PaymentStatus.SUCCEEDED:
        raise HTTPException(409, "Receipts are issued for successful payments")
    return Response(
        receipt_pdf(db, p), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{p.receipt_number}.pdf"'}
    )


# ------------------------------------------------------------------ expenses


@router.get("/billing/expenses", response_model=Page[ExpenseOut])
def list_expenses(
    db: DB,
    actor: Perm("billing.manage"),
    category: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = tenant_select(Expense, actor).order_by(Expense.spent_on.desc())
    if category:
        stmt = stmt.where(Expense.category == category)
    if date_from:
        stmt = stmt.where(Expense.spent_on >= date_from)
    if date_to:
        stmt = stmt.where(Expense.spent_on <= date_to)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/billing/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(body: ExpenseIn, db: DB, actor: Perm("billing.manage")):
    e = Expense(tenant_id=actor.tenant_id, recorded_by=actor.id, **body.model_dump())
    db.add(e)
    db.flush()
    audit.record(db, actor, "billing.expense_recorded", "expense", e.id, new=body.model_dump())
    db.commit()
    return e


@router.delete("/billing/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: uuid.UUID, db: DB, actor: Perm("billing.manage")):
    e = get_scoped(db, Expense, expense_id, actor, "Expense")
    e.deleted_at = utcnow()
    audit.record(db, actor, "billing.expense_deleted", "expense", e.id, old={"amount": e.amount, "category": e.category})
    db.commit()
