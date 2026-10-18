"""Referral reward: an owner who brings a neighbour gets one free cleaning.

The reward is held as a credit on the referrer's plot (tenant setting
``referral_reward_amount``, the price of one cleaning). Credits settle the plot's
open dues as ``referral_credit`` payments, so receipts and reconciliation keep working.
"""

import re
import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import Invoice, Payment, Property, Referral
from app.models.base import utcnow
from app.models.enums import InvoiceStatus, PaymentStatus, ReferralStatus
from app.services import audit, notifications
from app.services.billing import _apply_payment, money, outstanding
from app.services.maintenance import tenant_setting

DEFAULT_REWARD = 500  # ₹, one plot cleaning


def reward_amount(db: Session, tenant_id: uuid.UUID) -> Decimal:
    return money(tenant_setting(db, tenant_id, "referral_reward_amount", DEFAULT_REWARD))


def normalise_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 10:
        raise HTTPException(422, "Enter the neighbour's 10-digit mobile number")
    return digits[-10:]


def create(db: Session, actor: Actor, prop: Property, name: str, phone: str, note: str | None) -> Referral:
    phone = normalise_phone(phone)
    if (prop.owner_phone and re.sub(r"\D", "", prop.owner_phone)[-10:] == phone) or (
        actor.user.phone and re.sub(r"\D", "", actor.user.phone)[-10:] == phone
    ):
        raise HTTPException(422, "Refer a neighbour, not yourself")
    taken = db.scalar(
        select(Referral.id).where(
            Referral.tenant_id == prop.tenant_id,
            Referral.neighbour_phone == phone,
            Referral.status.in_([ReferralStatus.PENDING, ReferralStatus.CONVERTED]),
        )
    )
    if taken:
        raise HTTPException(409, "This neighbour has already been referred")
    ref = Referral(
        tenant_id=prop.tenant_id,
        referrer_user_id=actor.id,
        referrer_property_id=prop.id,
        neighbour_name=name.strip(),
        neighbour_phone=phone,
        note=note,
        status=ReferralStatus.PENDING,
        reward_amount=Decimal("0"),
        reward_remaining=Decimal("0"),
    )
    db.add(ref)
    db.flush()
    audit.record(db, actor, "referral.created", "referral", ref.id, new={"neighbour": ref.neighbour_name, "property": prop.code})
    notifications.notify(
        db,
        prop.tenant_id,
        notifications.managers(db, prop.tenant_id),
        "referral",
        f"New referral: {ref.neighbour_name}",
        f"{actor.user.full_name} ({prop.code}) referred {ref.neighbour_name}, {phone}",
        "referral",
        ref.id,
    )
    return ref


def convert(db: Session, actor: Actor, ref: Referral, neighbour_prop: Property) -> Referral:
    """The neighbour became a customer: reward the referrer with one free cleaning."""
    if ref.status != ReferralStatus.PENDING:
        raise HTTPException(409, f"Referral is {ref.status}")
    if neighbour_prop.id == ref.referrer_property_id:
        raise HTTPException(422, "The neighbour's plot must be a different plot")
    if db.scalar(select(Referral.id).where(Referral.converted_property_id == neighbour_prop.id)):
        raise HTTPException(409, "A referral reward was already given for this plot")
    reward = reward_amount(db, ref.tenant_id)
    ref.status = ReferralStatus.CONVERTED
    ref.converted_property_id = neighbour_prop.id
    ref.reward_amount = reward
    ref.reward_remaining = reward
    ref.decided_at = utcnow()
    ref.decided_by = actor.id
    audit.record(db, actor, "referral.converted", "referral", ref.id, new={"neighbour_property": neighbour_prop.code, "reward": reward})
    notifications.notify(
        db,
        ref.tenant_id,
        [ref.referrer_user_id],
        "referral",
        "You've earned a free cleaning",
        f"Thanks for referring {ref.neighbour_name}. ₹{reward} will come off your next dues.",
        "referral",
        ref.id,
    )
    db.flush()
    apply_credits(db, ref.referrer_property_id)
    return ref


def decline(db: Session, actor: Actor, ref: Referral) -> Referral:
    if ref.status != ReferralStatus.PENDING:
        raise HTTPException(409, f"Referral is {ref.status}")
    ref.status = ReferralStatus.DECLINED
    ref.decided_at = utcnow()
    ref.decided_by = actor.id
    audit.record(db, actor, "referral.declined", "referral", ref.id, old={"status": "pending"}, new={"status": ref.status})
    return ref


def apply_credits(db: Session, property_id: uuid.UUID) -> int:
    """Settle the plot's open dues, oldest first, from its unused referral rewards."""
    credits = list(
        db.scalars(
            select(Referral)
            .where(Referral.referrer_property_id == property_id, Referral.status == ReferralStatus.CONVERTED, Referral.reward_remaining > 0)
            .order_by(Referral.decided_at)
        )
    )
    if not credits:
        return 0
    invoices = db.scalars(
        select(Invoice)
        .where(
            Invoice.property_id == property_id,
            Invoice.status.in_([InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL]),
            Invoice.deleted_at.is_(None),
        )
        .order_by(Invoice.due_date, Invoice.number)
    )
    applied = 0
    for inv in invoices:
        for ref in credits:
            due = outstanding(inv)
            left = money(ref.reward_remaining)
            if due <= 0:
                break
            if left <= 0:
                continue
            amount = min(due, left)
            p = Payment(
                tenant_id=inv.tenant_id,
                invoice_id=inv.id,
                property_id=inv.property_id,
                amount=amount,
                method="referral_credit",
                reference=f"Referral · {ref.neighbour_name}"[:100],
                status=PaymentStatus.CREATED,
                idempotency_key=f"referral-{ref.id}-{inv.id}",
                paid_at=utcnow(),
                reconciled_at=utcnow(),
            )
            db.add(p)
            db.flush()
            _apply_payment(db, p, None)
            ref.reward_remaining = money(left - amount)
            applied += 1
    db.flush()
    return applied


def apply_all_credits(db: Session) -> int:
    """Worker pass: settle any dues raised since a reward was earned."""
    props = set(
        db.scalars(select(Referral.referrer_property_id).where(Referral.status == ReferralStatus.CONVERTED, Referral.reward_remaining > 0))
    )
    return sum(apply_credits(db, pid) for pid in props)
