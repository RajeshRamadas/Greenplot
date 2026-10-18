import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.v1._util import property_labels
from app.core.deps import DB, Perm
from app.models import BillingPlan, Property, Subscription
from app.models.enums import Role, SubscriptionStatus
from app.schemas.operations import SubscriptionIn, SubscriptionOut
from app.services import subscriptions as svc
from app.services.access import get_scoped, not_found, resident_property_ids, tenant_select

router = APIRouter(tags=["billing"])


def _out(db, subs: list[Subscription]) -> list[SubscriptionOut]:
    labels = property_labels(db, (s.property_id for s in subs))
    plans = {p.id: p for p in db.scalars(select(BillingPlan).where(BillingPlan.id.in_({s.plan_id for s in subs})))} if subs else {}
    out = []
    for s in subs:
        plan, prop = plans.get(s.plan_id), db.get(Property, s.property_id)
        price = svc.period_amount(plan, prop, s.frequency_months, s.discount_pct) if plan and prop else None
        out.append(
            SubscriptionOut.model_validate(s).model_copy(
                update={
                    "plan_name": plan.name if plan else None,
                    "property_label": labels.get(s.property_id),
                    "price": float(price) if price is not None else None,
                }
            )
        )
    return out


def _own_property(db, actor, property_id: uuid.UUID) -> Property:
    prop = get_scoped(db, Property, property_id, actor, "Property")
    if actor.role == Role.RESIDENT and prop.id not in resident_property_ids(db, actor):
        raise not_found("Property")
    return prop


def _get(db, actor, subscription_id) -> Subscription:
    sub = get_scoped(db, Subscription, subscription_id, actor, "Subscription")
    if actor.role == Role.RESIDENT and sub.property_id not in resident_property_ids(db, actor):
        raise not_found("Subscription")
    return sub


@router.get("/subscriptions/options")
def subscription_options(db: DB, actor: Perm("subscriptions.manage"), property_id: uuid.UUID | None = None):
    """Monthly and quarterly prices, with the discount, for the caller's plots (or one plot)."""
    if property_id:
        props = [_own_property(db, actor, property_id)]
    elif actor.role == Role.RESIDENT:
        ids = resident_property_ids(db, actor)
        props = list(db.scalars(select(Property).where(Property.id.in_(ids)).order_by(Property.plot_number))) if ids else []
    else:
        props = []
    labels = property_labels(db, (p.id for p in props))
    return [{**o, "property_label": labels.get(o["property_id"])} for o in svc.options(db, actor.tenant_id, props)]


@router.get("/subscriptions", response_model=list[SubscriptionOut])
def list_subscriptions(db: DB, actor: Perm("subscriptions.manage"), status: SubscriptionStatus | None = None):
    stmt = tenant_select(Subscription, actor).order_by(Subscription.created_at.desc())
    if actor.role == Role.RESIDENT:
        stmt = stmt.where(Subscription.property_id.in_(resident_property_ids(db, actor) or {uuid.uuid4()}))
    if status:
        stmt = stmt.where(Subscription.status == status)
    return _out(db, list(db.scalars(stmt)))


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=201)
def create_subscription(body: SubscriptionIn, db: DB, actor: Perm("subscriptions.manage")):
    """Put a plot on a plan, billed monthly or quarterly at a discount. The first invoice is raised at once."""
    prop = _own_property(db, actor, body.property_id)
    plan = get_scoped(db, BillingPlan, body.plan_id, actor, "Plan")
    if body.discount_pct is not None and actor.role != Role.LAYOUT_ADMIN:
        raise HTTPException(403, "Only the office can set a custom discount")
    sub = svc.subscribe(db, actor, prop, plan, body.frequency_months, body.start_date, body.discount_pct)
    db.commit()
    return _out(db, [sub])[0]


@router.post("/subscriptions/{subscription_id}/cancel", response_model=SubscriptionOut)
def cancel_subscription(subscription_id: uuid.UUID, db: DB, actor: Perm("subscriptions.manage")):
    sub = svc.cancel(db, actor, _get(db, actor, subscription_id))
    db.commit()
    return _out(db, [sub])[0]
