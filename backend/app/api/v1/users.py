import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import or_, select

from app.api.v1._util import Limit, Offset, paginate
from app.core.deps import DB, Perm
from app.models import Property, Resident, User
from app.models.base import utcnow
from app.models.enums import Role
from app.schemas.common import Page
from app.schemas.core import InviteOut, UserCreate, UserOut, UserUpdate
from app.services import audit
from app.services.access import get_scoped
from app.services.users import create_user, invite_url

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserOut])
def list_users(
    db: DB,
    actor: Perm("users.read"),
    role: Role | None = None,
    q: str | None = None,
    active: bool | None = None,
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = select(User).where(User.tenant_id == actor.tenant_id).order_by(User.full_name)
    if role:
        stmt = stmt.where(User.role == role)
    if active is not None:
        stmt = stmt.where(User.is_active.is_(active))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like), User.phone.ilike(like)))
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=InviteOut, status_code=201)
def create(body: UserCreate, db: DB, actor: Perm("users.manage")):
    if body.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "Cannot create platform administrators")
    user, token = create_user(
        db,
        actor,
        actor.tenant_id,
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        phone=body.phone,
        vendor_id=body.vendor_id,
        password=body.password,
    )
    if body.property_id:
        if body.role != Role.RESIDENT:
            raise HTTPException(422, "Only residents can be linked to a property")
        prop = get_scoped(db, Property, body.property_id, actor, "Property")
        db.add(
            Resident(
                tenant_id=actor.tenant_id,
                property_id=prop.id,
                user_id=user.id,
                name=user.full_name,
                phone=user.phone,
                email=user.email,
                relation="owner",
            )
        )
    db.commit()
    return InviteOut(user=UserOut.model_validate(user), invite_token=token, invite_url=invite_url(token))


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, db: DB, actor: Perm("users.read")):
    u = db.get(User, user_id)
    if not u or u.tenant_id != actor.tenant_id:
        raise HTTPException(404, "User not found")
    return u


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate, db: DB, actor: Perm("users.manage")):
    u = db.get(User, user_id)
    if not u or u.tenant_id != actor.tenant_id:
        raise HTTPException(404, "User not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("role") == Role.SUPER_ADMIN:
        raise HTTPException(403, "Cannot grant platform administration")
    if u.id == actor.id and ("role" in data or data.get("is_active") is False):
        raise HTTPException(422, "You cannot change your own role or deactivate yourself")
    before = audit.snapshot(u)
    for k, v in data.items():
        setattr(u, k, v)
    if "role" in data or data.get("is_active") is False:
        u.token_version += 1  # force re-login with the new permissions
    old, new = audit.diff(before, audit.snapshot(u))
    action = "user.role_changed" if "role" in new else "user.updated"
    audit.record(db, actor, action, "user", u.id, old=old, new=new)
    db.commit()
    return u


@router.post("/{user_id}/reinvite", response_model=InviteOut)
def reinvite(user_id: uuid.UUID, db: DB, actor: Perm("users.manage")):
    from datetime import timedelta

    from app.core.config import get_settings
    from app.core.security import hash_token, new_opaque_token

    u = db.get(User, user_id)
    if not u or u.tenant_id != actor.tenant_id:
        raise HTTPException(404, "User not found")
    token = new_opaque_token()
    u.invite_token_hash = hash_token(token)
    u.invite_expires_at = utcnow() + timedelta(hours=get_settings().invite_token_hours)
    audit.record(db, actor, "user.reinvited", "user", u.id)
    db.commit()
    return InviteOut(user=UserOut.model_validate(u), invite_token=token, invite_url=invite_url(token))
