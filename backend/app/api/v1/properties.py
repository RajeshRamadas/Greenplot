import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import or_, select

from app.api.v1._util import Limit, Offset, apply, paginate
from app.core.deps import DB, CurrentActor, Perm
from app.models import (
    Asset,
    Complaint,
    Incident,
    Inspection,
    Layout,
    MaintenanceTask,
    Media,
    Property,
    Resident,
    Tenant,
)
from app.models.base import utcnow
from app.models.enums import Role
from app.schemas.common import Page
from app.schemas.core import (
    LayoutIn,
    LayoutOut,
    PropertyIn,
    PropertyOut,
    PropertyUpdate,
    ResidentIn,
    ResidentOut,
    TimelineEntry,
)
from app.services import audit
from app.services.access import get_scoped, not_found, resident_property_ids, tenant_select
from app.services.users import create_user, invite_url

router = APIRouter(tags=["properties"])


# ------------------------------------------------------------------ layouts


@router.get("/layouts", response_model=list[LayoutOut])
def list_layouts(db: DB, actor: CurrentActor):
    return list(db.scalars(tenant_select(Layout, actor).order_by(Layout.name)))


@router.post("/layouts", response_model=LayoutOut, status_code=201)
def create_layout(body: LayoutIn, db: DB, actor: Perm("layouts.manage")):
    layout = Layout(tenant_id=actor.tenant_id, **body.model_dump())
    db.add(layout)
    db.flush()
    audit.record(db, actor, "layout.created", "layout", layout.id, new=body.model_dump())
    db.commit()
    return layout


@router.patch("/layouts/{layout_id}", response_model=LayoutOut)
def update_layout(layout_id: uuid.UUID, body: LayoutIn, db: DB, actor: Perm("layouts.manage")):
    layout = get_scoped(db, Layout, layout_id, actor, "Layout")
    before = audit.snapshot(layout)
    apply(layout, body.model_dump())
    old, new = audit.diff(before, audit.snapshot(layout))
    audit.record(db, actor, "layout.updated", "layout", layout.id, old=old, new=new)
    db.commit()
    return layout


# ------------------------------------------------------------------ properties


def _out(p: Property) -> PropertyOut:
    out = PropertyOut.model_validate(p)
    out.layout_name = p.layout.name if p.layout else None
    return out


@router.get("/properties", response_model=Page[PropertyOut])
def list_properties(
    db: DB,
    actor: Perm("properties.read"),
    q: str | None = None,
    layout_id: uuid.UUID | None = None,
    status: str | None = None,
    condition: str | None = None,
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = tenant_select(Property, actor).order_by(Property.block, Property.plot_number)
    if actor.role == Role.RESIDENT:
        stmt = stmt.where(Property.id.in_(resident_property_ids(db, actor) or {uuid.uuid4()}))
    if layout_id:
        stmt = stmt.where(Property.layout_id == layout_id)
    if status:
        stmt = stmt.where(Property.status == status)
    if condition:
        stmt = stmt.where(Property.condition == condition)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(Property.plot_number.ilike(like), Property.code.ilike(like), Property.owner_name.ilike(like), Property.address.ilike(like))
        )
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=[_out(p) for p in items], total=total, limit=limit, offset=offset)


@router.post("/properties", response_model=PropertyOut, status_code=201)
def create_property(body: PropertyIn, db: DB, actor: Perm("properties.manage")):
    get_scoped(db, Layout, body.layout_id, actor, "Layout")
    tenant = db.get(Tenant, actor.tenant_id)
    if tenant.max_properties:
        from sqlalchemy import func

        count = db.scalar(select(func.count()).select_from(Property).where(Property.tenant_id == tenant.id, Property.deleted_at.is_(None)))
        if count >= tenant.max_properties:
            raise HTTPException(402, "Property limit for your subscription reached")
    if db.scalar(select(Property).where(Property.tenant_id == actor.tenant_id, Property.code == body.code)):
        raise HTTPException(409, "A property with this ID already exists")
    p = Property(tenant_id=actor.tenant_id, **body.model_dump())
    db.add(p)
    db.flush()
    audit.record(db, actor, "property.created", "property", p.id, new=audit.snapshot(p))
    db.commit()
    db.refresh(p)
    return _out(p)


def _get_visible(db, actor, property_id) -> Property:
    p = get_scoped(db, Property, property_id, actor, "Property")
    if actor.role == Role.RESIDENT and p.id not in resident_property_ids(db, actor):
        raise not_found("Property")
    if not actor.can("properties.read"):
        raise not_found("Property")
    return p


@router.get("/properties/{property_id}", response_model=PropertyOut)
def get_property(property_id: uuid.UUID, db: DB, actor: CurrentActor):
    return _out(_get_visible(db, actor, property_id))


@router.patch("/properties/{property_id}", response_model=PropertyOut)
def update_property(property_id: uuid.UUID, body: PropertyUpdate, db: DB, actor: Perm("properties.manage")):
    p = get_scoped(db, Property, property_id, actor, "Property")
    before = audit.snapshot(p)
    apply(p, body.model_dump(exclude_unset=True))
    old, new = audit.diff(before, audit.snapshot(p))
    if new:
        audit.record(db, actor, "property.updated", "property", p.id, old=old, new=new)
    db.commit()
    return _out(p)


@router.delete("/properties/{property_id}", status_code=204)
def delete_property(property_id: uuid.UUID, db: DB, actor: Perm("properties.manage")):
    p = get_scoped(db, Property, property_id, actor, "Property")
    p.deleted_at = utcnow()
    audit.record(db, actor, "property.deleted", "property", p.id, old={"code": p.code})
    db.commit()


@router.get("/properties/{property_id}/history", response_model=list[TimelineEntry])
def property_history(property_id: uuid.UUID, db: DB, actor: CurrentActor, limit: int = Limit):
    """Timeline of inspections, maintenance, complaints, incidents and gardening for a property (§6)."""
    p = _get_visible(db, actor, property_id)
    entries: list[TimelineEntry] = []
    for t in db.scalars(select(MaintenanceTask).where(MaintenanceTask.property_id == p.id, MaintenanceTask.deleted_at.is_(None))):
        entries.append(
            TimelineEntry(
                at=t.closed_at or t.completed_at or t.created_at,
                kind="gardening" if t.category in ("gardening", "landscaping") else "maintenance",
                id=t.id,
                number=t.number,
                title=t.title,
                status=t.status,
            )
        )
    for i in db.scalars(select(Inspection).where(Inspection.property_id == p.id, Inspection.deleted_at.is_(None))):
        entries.append(
            TimelineEntry(
                at=i.completed_at or i.scheduled_for or i.created_at,
                kind="property_watch" if i.is_property_watch else "inspection",
                id=i.id,
                number=i.number,
                title=f"Inspection · {i.overall_condition or i.status}",
                status=i.status,
            )
        )
    for c in db.scalars(select(Complaint).where(Complaint.property_id == p.id, Complaint.deleted_at.is_(None))):
        entries.append(TimelineEntry(at=c.created_at, kind="complaint", id=c.id, number=c.number, title=c.title, status=c.status))
    if actor.role != Role.RESIDENT or actor.can("incidents.read"):
        for inc in db.scalars(select(Incident).where(Incident.property_id == p.id, Incident.deleted_at.is_(None))):
            entries.append(
                TimelineEntry(at=inc.occurred_at, kind="incident", id=inc.id, number=inc.number, title=inc.title, status=inc.status)
            )
    for m in db.scalars(select(Media).where(Media.entity_type == "property", Media.entity_id == p.id, Media.status == "ready")):
        entries.append(
            TimelineEntry(
                at=m.uploaded_at or m.created_at, kind="record", id=m.id, title=m.original_filename or "Document", status=m.status
            )
        )
    entries.sort(key=lambda e: e.at, reverse=True)
    return entries[:limit]


@router.get("/properties/{property_id}/assets")
def property_assets(property_id: uuid.UUID, db: DB, actor: Perm("assets.read")):
    from app.schemas.core import AssetOut

    p = get_scoped(db, Property, property_id, actor, "Property")
    return [AssetOut.model_validate(a) for a in db.scalars(tenant_select(Asset, actor).where(Asset.property_id == p.id))]


# ------------------------------------------------------------------ residents


@router.get("/residents", response_model=Page[ResidentOut])
def list_residents(
    db: DB,
    actor: Perm("residents.read"),
    property_id: uuid.UUID | None = None,
    q: str | None = None,
    directory: bool = False,
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = tenant_select(Resident, actor).order_by(Resident.name)
    if actor.role == Role.RESIDENT:
        # residents see their household, plus the opt-in directory
        mine = resident_property_ids(db, actor) or {uuid.uuid4()}
        stmt = stmt.where(Resident.in_directory.is_(True)) if directory else stmt.where(Resident.property_id.in_(mine))
    elif directory:
        stmt = stmt.where(Resident.in_directory.is_(True))
    if property_id:
        stmt = stmt.where(Resident.property_id == property_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Resident.name.ilike(like), Resident.phone.ilike(like), Resident.email.ilike(like)))
    items, total = paginate(db, stmt, limit, offset)
    if actor.role == Role.RESIDENT and directory:
        mine = resident_property_ids(db, actor)
        items = [ResidentOut.model_validate(r).model_copy(update={"email": None} if r.property_id not in mine else {}) for r in items]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/residents", status_code=201)
def create_resident(body: ResidentIn, db: DB, actor: Perm("residents.manage")):
    get_scoped(db, Property, body.property_id, actor, "Property")
    data = body.model_dump(exclude={"invite"})
    invite = None
    if body.invite and not body.user_id:
        if not body.email:
            raise HTTPException(422, "Email is required to invite a resident")
        user, invite = create_user(db, actor, actor.tenant_id, email=body.email, full_name=body.name, role=Role.RESIDENT, phone=body.phone)
        data["user_id"] = user.id
    r = Resident(tenant_id=actor.tenant_id, **data)
    db.add(r)
    db.flush()
    audit.record(db, actor, "resident.created", "resident", r.id, new=audit.snapshot(r))
    db.commit()
    return {"resident": ResidentOut.model_validate(r), "invite_token": invite, "invite_url": invite_url(invite)}


@router.patch("/residents/{resident_id}", response_model=ResidentOut)
def update_resident(resident_id: uuid.UUID, body: ResidentIn, db: DB, actor: Perm("residents.manage")):
    r = get_scoped(db, Resident, resident_id, actor, "Resident")
    before = audit.snapshot(r)
    apply(r, body.model_dump(exclude={"invite"}, exclude_unset=True))
    old, new = audit.diff(before, audit.snapshot(r))
    audit.record(db, actor, "resident.updated", "resident", r.id, old=old, new=new)
    db.commit()
    return r


@router.delete("/residents/{resident_id}", status_code=204)
def delete_resident(resident_id: uuid.UUID, db: DB, actor: Perm("residents.manage")):
    r = get_scoped(db, Resident, resident_id, actor, "Resident")
    r.deleted_at = utcnow()
    audit.record(db, actor, "resident.removed", "resident", r.id, old={"name": r.name, "property_id": r.property_id})
    db.commit()
