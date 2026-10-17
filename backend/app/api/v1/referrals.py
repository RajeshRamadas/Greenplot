import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.v1._util import property_labels
from app.core.deps import DB, Perm
from app.models import Property, Referral, User
from app.models.enums import ReferralStatus, Role
from app.schemas.operations import ReferralConvertIn, ReferralIn, ReferralOut
from app.services import referrals as svc
from app.services.access import get_scoped, not_found, resident_property_ids, tenant_select

router = APIRouter(tags=["referrals"])


def _out(db, refs: list[Referral]) -> list[ReferralOut]:
    labels = property_labels(db, (r.referrer_property_id for r in refs))
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_({r.referrer_user_id for r in refs}))).all()) if refs else {}
    return [
        ReferralOut.model_validate(r).model_copy(
            update={"property_label": labels.get(r.referrer_property_id), "referrer_name": names.get(r.referrer_user_id)}
        )
        for r in refs
    ]


@router.get("/referrals")
def list_referrals(db: DB, actor: Perm("referrals.read"), status: ReferralStatus | None = None):
    """Referrals with the reward per referral; owners see their own and their unused credit."""
    stmt = tenant_select(Referral, actor).order_by(Referral.created_at.desc())
    if actor.role == Role.RESIDENT:
        stmt = stmt.where(Referral.referrer_user_id == actor.id)
    if status:
        stmt = stmt.where(Referral.status == status)
    refs = list(db.scalars(stmt))
    return {
        "items": _out(db, refs),
        "reward_amount": float(svc.reward_amount(db, actor.tenant_id)),
        "credit_remaining": float(sum((r.reward_remaining for r in refs if r.status == ReferralStatus.CONVERTED), 0)),
    }


@router.post("/referrals", response_model=ReferralOut, status_code=201)
def create_referral(body: ReferralIn, db: DB, actor: Perm("referrals.create")):
    """Refer a neighbour. When they become a customer the referrer gets one free cleaning."""
    own = resident_property_ids(db, actor)
    if body.property_id:
        if body.property_id not in own:
            raise not_found("Property")
        prop_id = body.property_id
    elif len(own) == 1:
        prop_id = next(iter(own))
    else:
        raise HTTPException(422, "Choose which of your plots should get the reward" if own else "You have no plot to credit")
    prop = get_scoped(db, Property, prop_id, actor, "Property")
    ref = svc.create(db, actor, prop, body.neighbour_name, body.neighbour_phone, body.note)
    db.commit()
    return _out(db, [ref])[0]


@router.post("/referrals/{referral_id}/convert", response_model=ReferralOut)
def convert_referral(referral_id: uuid.UUID, body: ReferralConvertIn, db: DB, actor: Perm("billing.manage")):
    """The neighbour joined: link their plot and give the referrer a free cleaning."""
    ref = get_scoped(db, Referral, referral_id, actor, "Referral")
    prop = get_scoped(db, Property, body.property_id, actor, "Property")
    svc.convert(db, actor, ref, prop)
    db.commit()
    return _out(db, [ref])[0]


@router.post("/referrals/{referral_id}/decline", response_model=ReferralOut)
def decline_referral(referral_id: uuid.UUID, db: DB, actor: Perm("billing.manage")):
    ref = get_scoped(db, Referral, referral_id, actor, "Referral")
    svc.decline(db, actor, ref)
    db.commit()
    return _out(db, [ref])[0]
