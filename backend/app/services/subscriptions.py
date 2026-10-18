"""Subscription plans: an owner keeps a plot on a plan, billed monthly or quarterly at a discount.

A subscription prices itself from its billing plan (the plan's amount per month times the
subscription's months, less the discount) and raises its own invoices on schedule through
the worker, so the owner pays once per period and nobody has to chase them.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import BillingPlan, Invoice, Property, Subscription
from app.models.base import utcnow
from app.models.enums import InvoiceStatus, SubscriptionStatus
from app.services import audit, notifications
from app.services.billing import add_months, amount_for, money
from app.services.maintenance import tenant_setting
from app.services.numbering import next_number

FREQUENCIES = {1: "Monthly", 3: "Quarterly"}
DEFAULT_DISCOUNTS = {"1": 5, "3": 10}  # percent off the plan's price, per frequency in months


def default_discount(db: Session, tenant_id: uuid.UUID, frequency_months: int) -> Decimal:
    discounts = {**DEFAULT_DISCOUNTS, **(tenant_setting(db, tenant_id, "subscription_discounts", {}) or {})}
    return money(discounts.get(str(frequency_months), 0))


def period_amount(plan: BillingPlan, prop: Property, frequency_months: int, discount_pct) -> Decimal | None:
    base = amount_for(plan, prop)
    if base is None:
        return None
    full = Decimal(str(base)) / plan.frequency_months * frequency_months
    return money(full * (Decimal("100") - money(discount_pct)) / 100)


def options(db: Session, tenant_id: uuid.UUID, props: list[Property]) -> list[dict]:
    """What each property would pay on each subscribable plan, monthly and quarterly."""
    plans = db.scalars(
        select(BillingPlan)
        .where(
            BillingPlan.tenant_id == tenant_id,
            BillingPlan.subscribable.is_(True),
            BillingPlan.is_active.is_(True),
            BillingPlan.deleted_at.is_(None),
        )
        .order_by(BillingPlan.name)
    )
    out = []
    for plan in plans:
        for prop in props:
            for months, name in FREQUENCIES.items():
                discount = default_discount(db, tenant_id, months)
                price = period_amount(plan, prop, months, discount)
                full = period_amount(plan, prop, months, 0)
                if price is None or price <= 0:
                    continue
                out.append(
                    {
                        "plan_id": plan.id,
                        "plan_name": plan.name,
                        "property_id": prop.id,
                        "frequency_months": months,
                        "frequency": name,
                        "discount_pct": float(discount),
                        "full_price": float(full),
                        "price": float(price),
                        "saving": float(full - price),
                    }
                )
    return out


def subscribe(
    db: Session,
    actor: Actor,
    prop: Property,
    plan: BillingPlan,
    frequency_months: int,
    start: date | None = None,
    discount_pct: float | None = None,
) -> Subscription:
    if frequency_months not in FREQUENCIES:
        raise HTTPException(422, "Choose monthly (1) or quarterly (3)")
    if not (plan.subscribable and plan.is_active) or plan.deleted_at:
        raise HTTPException(422, "This plan is not offered as a subscription")
    active = db.scalar(
        select(Subscription.id).where(
            Subscription.property_id == prop.id, Subscription.plan_id == plan.id, Subscription.status == SubscriptionStatus.ACTIVE
        )
    )
    if active:
        raise HTTPException(409, "This plot already has an active subscription to this plan")
    discount = money(discount_pct) if discount_pct is not None else default_discount(db, prop.tenant_id, frequency_months)
    if period_amount(plan, prop, frequency_months, discount) in (None, Decimal("0.00")):
        raise HTTPException(422, f"No price for this plot on {plan.name}")
    start = start or date.today()
    sub = Subscription(
        tenant_id=prop.tenant_id,
        property_id=prop.id,
        plan_id=plan.id,
        frequency_months=frequency_months,
        discount_pct=discount,
        status=SubscriptionStatus.ACTIVE,
        started_on=start,
        next_billing_date=start,
        created_by=actor.id,
    )
    db.add(sub)
    db.flush()
    audit.record(
        db,
        actor,
        "subscription.created",
        "subscription",
        sub.id,
        new={"plan": plan.name, "property": prop.code, "frequency_months": frequency_months, "discount_pct": discount},
    )
    bill_due(db, today=date.today(), subscription_id=sub.id)
    return sub


def cancel(db: Session, actor: Actor, sub: Subscription) -> Subscription:
    if sub.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(409, f"Subscription is {sub.status}")
    sub.status = SubscriptionStatus.CANCELLED
    sub.cancelled_at = utcnow()
    audit.record(db, actor, "subscription.cancelled", "subscription", sub.id, old={"status": "active"}, new={"status": sub.status})
    return sub


def _raise_invoice(db: Session, sub: Subscription, plan: BillingPlan, prop: Property, period_start: date) -> Invoice | None:
    period_end = add_months(period_start, sub.frequency_months) - timedelta(days=1)
    exists = db.scalar(
        select(Invoice.id).where(Invoice.plan_id == plan.id, Invoice.property_id == prop.id, Invoice.period_start == period_start)
    )
    amount = period_amount(plan, prop, sub.frequency_months, sub.discount_pct)
    if exists or not amount or amount <= 0:
        return None
    label = FREQUENCIES.get(sub.frequency_months, f"{sub.frequency_months}-month")
    span = f"{period_start:%b %Y}" + (f" – {period_end:%b %Y}" if sub.frequency_months > 1 else "")
    inv = Invoice(
        tenant_id=sub.tenant_id,
        number=next_number(db, sub.tenant_id, "INV"),
        property_id=prop.id,
        plan_id=plan.id,
        subscription_id=sub.id,
        description=f"{plan.name} · {label} subscription · {span}",
        period_start=period_start,
        period_end=period_end,
        amount=amount,
        amount_paid=Decimal("0"),
        due_date=period_start + timedelta(days=plan.due_days),
        status=InvoiceStatus.UNPAID,
    )
    db.add(inv)
    db.flush()
    notifications.notify(
        db, sub.tenant_id, [prop.owner_user_id], "payment_due", f"Subscription due: ₹{amount}", inv.description, "invoice", inv.id
    )
    audit.record(
        db, None, "subscription.invoiced", "subscription", sub.id, new={"invoice": inv.number, "amount": amount}, tenant_id=sub.tenant_id
    )
    return inv


def bill_due(db: Session, today: date | None = None, subscription_id: uuid.UUID | None = None) -> list[Invoice]:
    """Raise every subscription invoice whose period has started, catching up missed periods."""
    from app.services import referrals  # referral credits settle new dues; imported here to avoid a cycle

    today = today or date.today()
    stmt = select(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.next_billing_date <= today)
    if subscription_id:
        stmt = stmt.where(Subscription.id == subscription_id)
    created = []
    for sub in db.scalars(stmt).all():
        plan, prop = db.get(BillingPlan, sub.plan_id), db.get(Property, sub.property_id)
        if plan is None or prop is None or prop.deleted_at:
            continue
        while sub.next_billing_date <= today:
            inv = _raise_invoice(db, sub, plan, prop, sub.next_billing_date)
            if inv:
                created.append(inv)
            sub.next_billing_date = add_months(sub.next_billing_date, sub.frequency_months)
        referrals.apply_credits(db, prop.id)
    db.flush()
    return created
