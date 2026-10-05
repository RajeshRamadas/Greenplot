import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.v1._util import Limit, Offset, apply, paginate
from app.core.deps import DB, Perm
from app.models import Layout, MaintenanceTask, Media, Property, Tenant, User
from app.models.enums import Role
from app.schemas.common import Page
from app.schemas.core import InviteOut, TenantCreate, TenantOut, TenantSettingsIn, TenantUpdate, UserOut
from app.services import audit
from app.services.maintenance import ensure_default_policies
from app.services.users import create_user, invite_url

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("", response_model=Page[TenantOut])
def list_tenants(db: DB, actor: Perm("tenants.manage"), limit: int = Limit, offset: int = Offset):
    items, total = paginate(db, select(Tenant).order_by(Tenant.created_at.desc()), limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=InviteOut, status_code=201)
def create_tenant(body: TenantCreate, db: DB, actor: Perm("tenants.manage")):
    if db.scalar(select(Tenant).where(Tenant.slug == body.slug)):
        raise HTTPException(409, "Slug already in use")
    data = body.model_dump(exclude={"admin_email", "admin_name", "admin_password", "layout_name"}, exclude_none=True)
    tenant = Tenant(**data)
    db.add(tenant)
    db.flush()
    db.add(Layout(tenant_id=tenant.id, name=body.layout_name or body.name, city=body.city))
    ensure_default_policies(db, tenant.id)
    admin, token = create_user(
        db,
        actor,
        tenant.id,
        email=body.admin_email,
        full_name=body.admin_name,
        role=Role.LAYOUT_ADMIN,
        password=body.admin_password,
    )
    audit.record(db, actor, "tenant.created", "tenant", tenant.id, new=audit.snapshot(tenant), tenant_id=tenant.id)
    db.commit()
    return InviteOut(user=UserOut.model_validate(admin), invite_token=token, invite_url=invite_url(token))


@router.get("/stats")
def platform_stats(db: DB, actor: Perm("tenants.manage")):
    rows = []
    for t in db.scalars(select(Tenant).order_by(Tenant.name)):
        rows.append(
            {
                "tenant_id": t.id,
                "name": t.name,
                "status": t.status,
                "plan": t.plan,
                "properties": db.scalar(
                    select(func.count()).select_from(Property).where(Property.tenant_id == t.id, Property.deleted_at.is_(None))
                ),
                "users": db.scalar(select(func.count()).select_from(User).where(User.tenant_id == t.id)),
                "tasks": db.scalar(select(func.count()).select_from(MaintenanceTask).where(MaintenanceTask.tenant_id == t.id)),
                "storage_bytes": db.scalar(
                    select(func.coalesce(func.sum(Media.size_bytes), 0)).where(Media.tenant_id == t.id, Media.status == "ready")
                ),
            }
        )
    return rows


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(tenant_id: uuid.UUID, db: DB, actor: Perm("tenants.manage")):
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    return t


@router.patch("/{tenant_id}", response_model=TenantOut)
def update_tenant(tenant_id: uuid.UUID, body: TenantUpdate, db: DB, actor: Perm("tenants.manage")):
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    before = audit.snapshot(t)
    apply(t, body.model_dump(exclude_unset=True))
    old, new = audit.diff(before, audit.snapshot(t))
    audit.record(db, actor, "tenant.updated", "tenant", t.id, old=old, new=new, tenant_id=t.id)
    db.commit()
    return t


# ------------------------------------------------------------- tenant-level settings (layout admin)

settings_router = APIRouter(prefix="/settings", tags=["settings"])


@settings_router.get("", response_model=TenantOut)
def get_settings_(db: DB, actor: Perm("settings.manage")):
    return db.get(Tenant, actor.tenant_id)


@settings_router.patch("", response_model=TenantOut)
def update_settings(body: TenantSettingsIn, db: DB, actor: Perm("settings.manage")):
    t = db.get(Tenant, actor.tenant_id)
    old = dict(t.settings or {})
    new = {**old, **body.model_dump(exclude_none=True)}
    t.settings = new
    o, n = audit.diff(old, new)
    audit.record(db, actor, "settings.updated", "tenant", t.id, old=o, new=n)
    db.commit()
    return t
