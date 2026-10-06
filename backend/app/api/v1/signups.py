"""Self-registration: residents and vendors ask to join a layout; the layout office approves."""

import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select

from app.api.v1._util import Limit, Offset, paginate
from app.core.config import get_settings
from app.core.deps import DB, Perm, client_ip
from app.core.ratelimit import limiter
from app.models import Property, Resident, SignupRequest, Tenant, User, Vendor
from app.models.base import utcnow
from app.models.enums import Role
from app.schemas.common import Page
from app.schemas.core import UserOut
from app.services import accounts, audit, messaging, notifications
from app.services.access import get_scoped
from app.services.users import create_user, invite_url
from app.services.whatsapp import normalize_phone

router = APIRouter(tags=["signups"])


def _throttle(request: Request, key: str) -> None:
    if not limiter.allow(f"signup:{client_ip(request)}:{key}", get_settings().login_rate_per_minute):
        raise HTTPException(429, "Too many attempts. Try again in a minute.")


# --------------------------------------------------------------------------- public


@router.get("/public/layouts")
def find_layouts(request: Request, db: DB, q: str = Query(min_length=2, max_length=100)):
    """Find a layout to register with (name and city only)."""
    _throttle(request, "layouts")
    like = f"%{q}%"
    rows = db.scalars(
        select(Tenant)
        .where(Tenant.status == "active", or_(Tenant.name.ilike(like), Tenant.slug.ilike(like)))
        .order_by(Tenant.name)
        .limit(10)
    )
    return [{"slug": t.slug, "name": t.name, "city": t.city} for t in rows]


class SignupCodeIn(BaseModel):
    phone: str = Field(min_length=6, max_length=30)


@router.post("/public/signup/code")
def signup_code(body: SignupCodeIn, request: Request, db: DB):
    """Verify the applicant's mobile number before the request reaches the office."""
    phone = normalize_phone(body.phone)
    if not phone:
        raise HTTPException(422, "Enter a valid mobile number")
    _throttle(request, phone)
    code = accounts.issue_otp(db, "signup", phone, None, client_ip(request))
    channels = messaging.send_otp(phone=phone, code=code, purpose="registration")
    db.commit()
    return accounts.otp_response(code, channels)


class SignupIn(BaseModel):
    layout: str = Field(min_length=3, max_length=80, description="Layout slug from /public/layouts")
    kind: str = Field(pattern="^(resident|vendor)$")
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone: str = Field(min_length=6, max_length=30)
    code: str = Field(min_length=4, max_length=10)
    plot_number: str | None = Field(None, max_length=40)
    relation: str | None = Field(None, pattern="^(owner|tenant|family)$")
    company_name: str | None = Field(None, max_length=200)
    service_categories: list[str] = []
    message: str | None = Field(None, max_length=2000)


@router.post("/public/signup", status_code=201)
def signup(body: SignupIn, request: Request, db: DB):
    phone = normalize_phone(body.phone)
    if not phone:
        raise HTTPException(422, "Enter a valid mobile number")
    _throttle(request, f"submit:{phone}")
    tenant = db.scalar(select(Tenant).where(Tenant.slug == body.layout, Tenant.status == "active"))
    if tenant is None:
        raise HTTPException(404, "Layout not found")
    if body.kind == "resident" and not body.plot_number:
        raise HTTPException(422, "Enter your plot number")
    if body.kind == "vendor" and not body.company_name:
        raise HTTPException(422, "Enter your company name")
    accounts.check_otp(db, "signup", phone, body.code)
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        db.commit()
        raise HTTPException(409, "An account with this email already exists. Sign in, or use 'Forgot password'.")
    if db.scalar(
        select(SignupRequest.id).where(
            SignupRequest.tenant_id == tenant.id, SignupRequest.email == email, SignupRequest.status == "pending"
        )
    ):
        db.commit()
        raise HTTPException(409, "A request with this email is already waiting for approval")
    req = SignupRequest(
        tenant_id=tenant.id,
        kind=body.kind,
        full_name=body.full_name.strip(),
        email=email,
        phone=body.phone.strip(),
        plot_number=(body.plot_number or "").strip() or None,
        relation=body.relation or ("owner" if body.kind == "resident" else None),
        company_name=body.company_name,
        service_categories=body.service_categories[:20],
        message=body.message,
        ip=client_ip(request),
    )
    db.add(req)
    db.flush()
    audit.record(db, None, "signup.requested", "signup_request", req.id, new={"kind": req.kind, "email": email}, tenant_id=tenant.id)
    notifications.notify(
        db,
        tenant.id,
        notifications.users_with_roles(db, tenant.id, [Role.LAYOUT_ADMIN]),
        "signup_request",
        f"New {req.kind} registration: {req.full_name}",
        f"Plot {req.plot_number}" if req.plot_number else req.company_name,
        "signup_request",
        req.id,
    )
    db.commit()
    return {"id": req.id, "status": req.status, "layout": tenant.name}


# --------------------------------------------------------------------------- layout office


class SignupOut(BaseModel):
    id: uuid.UUID
    kind: str
    full_name: str
    email: str
    phone: str
    plot_number: str | None
    relation: str | None
    company_name: str | None
    service_categories: list[str]
    message: str | None
    status: str
    review_note: str | None
    reviewed_at: object | None
    created_at: object
    suggested_property_id: uuid.UUID | None = None
    suggested_vendor_id: uuid.UUID | None = None


def _out(db, actor, r: SignupRequest) -> SignupOut:
    o = SignupOut.model_validate(r, from_attributes=True)
    if r.kind == "resident" and r.plot_number:
        prop = db.scalar(
            select(Property).where(
                Property.tenant_id == actor.tenant_id,
                Property.deleted_at.is_(None),
                or_(Property.plot_number.ilike(r.plot_number), Property.code.ilike(r.plot_number)),
            )
        )
        o.suggested_property_id = prop.id if prop else None
    if r.kind == "vendor" and r.company_name:
        v = db.scalar(
            select(Vendor).where(Vendor.tenant_id == actor.tenant_id, Vendor.deleted_at.is_(None), Vendor.name.ilike(r.company_name))
        )
        o.suggested_vendor_id = v.id if v else None
    return o


@router.get("/signups", response_model=Page[SignupOut])
def list_signups(db: DB, actor: Perm("users.manage"), status: str | None = "pending", limit: int = Limit, offset: int = Offset):
    stmt = select(SignupRequest).where(SignupRequest.tenant_id == actor.tenant_id).order_by(SignupRequest.created_at.desc())
    if status:
        stmt = stmt.where(SignupRequest.status == status)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=[_out(db, actor, r) for r in items], total=total, limit=limit, offset=offset)


class ApproveIn(BaseModel):
    property_id: uuid.UUID | None = None  # residents
    vendor_id: uuid.UUID | None = None  # vendors: an existing vendor, or a new one is created from the request
    relation: str | None = Field(None, pattern="^(owner|tenant|family)$")
    note: str | None = Field(None, max_length=1000)


class ApproveOut(BaseModel):
    user: UserOut
    invite_url: str | None
    sent_via: list[str]


def _pending(db, actor, signup_id) -> SignupRequest:
    r = db.get(SignupRequest, signup_id)
    if r is None or r.tenant_id != actor.tenant_id:
        raise HTTPException(404, "Request not found")
    if r.status != "pending":
        raise HTTPException(409, f"Request is already {r.status}")
    return r


@router.post("/signups/{signup_id}/approve", response_model=ApproveOut)
def approve(signup_id: uuid.UUID, body: ApproveIn, db: DB, actor: Perm("users.manage")):
    """Create the account (and resident link or vendor) and send the invite to set a password."""
    r = _pending(db, actor, signup_id)
    vendor_id = None
    prop = None
    if r.kind == "resident":
        if not body.property_id:
            raise HTTPException(422, "Choose the resident's property")
        prop = get_scoped(db, Property, body.property_id, actor, "Property")
    else:
        if body.vendor_id:
            vendor_id = get_scoped(db, Vendor, body.vendor_id, actor, "Vendor").id
        else:
            v = Vendor(
                tenant_id=actor.tenant_id,
                name=r.company_name or r.full_name,
                contact_person=r.full_name,
                phone=r.phone,
                email=r.email,
                service_categories=r.service_categories or [],
            )
            db.add(v)
            db.flush()
            audit.record(db, actor, "vendor.created", "vendor", v.id, new={"name": v.name, "via": "signup"})
            vendor_id = v.id
    user, token = create_user(
        db,
        actor,
        actor.tenant_id,
        email=r.email,
        full_name=r.full_name,
        role=Role.RESIDENT if r.kind == "resident" else Role.VENDOR,
        phone=r.phone,
        vendor_id=vendor_id,
    )
    user.phone_verified_at = r.created_at  # proven with a code when the request was made
    if prop is not None:
        db.add(
            Resident(
                tenant_id=actor.tenant_id,
                property_id=prop.id,
                user_id=user.id,
                name=user.full_name,
                phone=user.phone,
                email=user.email,
                relation=body.relation or r.relation or "owner",
            )
        )
    r.status, r.reviewed_by, r.reviewed_at, r.review_note, r.user_id = "approved", actor.id, utcnow(), body.note, user.id
    audit.record(db, actor, "signup.approved", "signup_request", r.id, new={"user_id": user.id, "property_id": body.property_id})
    sent = accounts.deliver_invite(db, user, token)
    db.commit()
    return ApproveOut(user=UserOut.model_validate(user), invite_url=invite_url(token), sent_via=sent)


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/signups/{signup_id}/reject", response_model=SignupOut)
def reject(signup_id: uuid.UUID, body: RejectIn, db: DB, actor: Perm("users.manage")):
    r = _pending(db, actor, signup_id)
    r.status, r.reviewed_by, r.reviewed_at, r.review_note = "rejected", actor.id, utcnow(), body.reason
    audit.record(db, actor, "signup.rejected", "signup_request", r.id, new={"reason": body.reason})
    tenant = db.get(Tenant, actor.tenant_id)
    messaging.send_link(
        r.phone,
        r.email,
        "Your GreenPlot registration",
        f"Hello {r.full_name}, your request to join {tenant.name} on GreenPlot was not approved: {body.reason}",
    )
    db.commit()
    return _out(db, actor, r)
