"""Assets, vendors, staff and attendance (requirements §17, §21)."""

import secrets
import uuid
from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import or_, select

from app.api.v1._util import Limit, Offset, apply, paginate
from app.core.deps import DB, CurrentActor, Perm
from app.models import Asset, Attendance, MaintenanceTask, Property, StaffProfile, User, Vendor
from app.models.base import utcnow
from app.models.enums import Role, TaskStatus
from app.schemas.common import GeoPoint, Page
from app.schemas.core import (
    AssetIn,
    AssetOut,
    AssetUpdate,
    AttendanceOut,
    StaffIn,
    StaffOut,
    StaffUpdate,
    VendorIn,
    VendorOut,
    VendorUpdate,
)
from app.services import audit
from app.services.access import get_scoped, tenant_select

router = APIRouter(tags=["assets", "vendors", "staff"])


# ------------------------------------------------------------------ assets


@router.get("/assets", response_model=Page[AssetOut])
def list_assets(
    db: DB,
    actor: Perm("assets.read"),
    q: str | None = None,
    category: str | None = None,
    property_id: uuid.UUID | None = None,
    service_due: bool | None = None,
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = tenant_select(Asset, actor).order_by(Asset.code)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Asset.name.ilike(like), Asset.code.ilike(like), Asset.location.ilike(like)))
    if category:
        stmt = stmt.where(Asset.category == category)
    if property_id:
        stmt = stmt.where(Asset.property_id == property_id)
    if service_due:
        stmt = stmt.where(Asset.next_service_due <= date.today())
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/assets", response_model=AssetOut, status_code=201)
def create_asset(body: AssetIn, db: DB, actor: Perm("assets.manage")):
    data = body.model_dump()
    data["qr_code"] = data["qr_code"] or f"GP-AST-{secrets.token_hex(6).upper()}"
    if body.property_id:
        get_scoped(db, Property, body.property_id, actor, "Property")
    if body.vendor_id:
        get_scoped(db, Vendor, body.vendor_id, actor, "Vendor")
    dup = db.scalar(tenant_select(Asset, actor).where(or_(Asset.code == data["code"], Asset.qr_code == data["qr_code"])))
    if dup:
        raise HTTPException(409, "Asset code or QR code already in use")
    a = Asset(tenant_id=actor.tenant_id, **data)
    db.add(a)
    db.flush()
    audit.record(db, actor, "asset.created", "asset", a.id, new=audit.snapshot(a))
    db.commit()
    return a


@router.get("/assets/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: uuid.UUID, db: DB, actor: Perm("assets.read")):
    return get_scoped(db, Asset, asset_id, actor, "Asset")


@router.patch("/assets/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: uuid.UUID, body: AssetUpdate, db: DB, actor: Perm("assets.manage")):
    a = get_scoped(db, Asset, asset_id, actor, "Asset")
    before = audit.snapshot(a)
    apply(a, body.model_dump(exclude_unset=True))
    old, new = audit.diff(before, audit.snapshot(a))
    audit.record(db, actor, "asset.updated", "asset", a.id, old=old, new=new)
    db.commit()
    return a


@router.get("/assets/{asset_id}/history")
def asset_history(asset_id: uuid.UUID, db: DB, actor: Perm("assets.read")):
    from app.api.v1.maintenance import summaries

    a = get_scoped(db, Asset, asset_id, actor, "Asset")
    tasks = list(
        db.scalars(
            tenant_select(MaintenanceTask, actor).where(MaintenanceTask.asset_id == a.id).order_by(MaintenanceTask.created_at.desc())
        )
    )
    return {"asset": AssetOut.model_validate(a), "maintenance": summaries(db, tasks)}


@router.get("/assets/{asset_id}/qr.svg")
def asset_qr(asset_id: uuid.UUID, db: DB, actor: Perm("assets.read")):
    """Printable QR label for the asset."""
    from app.services.qr import qr_svg

    a = get_scoped(db, Asset, asset_id, actor, "Asset")
    return Response(qr_svg(a.qr_code, caption=f"{a.code} · {a.name}"), media_type="image/svg+xml")


# ------------------------------------------------------------------ vendors


@router.get("/vendors", response_model=Page[VendorOut])
def list_vendors(
    db: DB,
    actor: Perm("vendors.read"),
    q: str | None = None,
    category: str | None = None,
    active: bool | None = None,
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = tenant_select(Vendor, actor).order_by(Vendor.name)
    if q:
        stmt = stmt.where(or_(Vendor.name.ilike(f"%{q}%"), Vendor.contact_person.ilike(f"%{q}%")))
    if active is not None:
        stmt = stmt.where(Vendor.is_active.is_(active))
    items, total = paginate(db, stmt, limit, offset)
    if category:
        items = [v for v in items if category in (v.service_categories or [])]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/vendors", response_model=VendorOut, status_code=201)
def create_vendor(body: VendorIn, db: DB, actor: Perm("vendors.manage")):
    v = Vendor(tenant_id=actor.tenant_id, **body.model_dump())
    db.add(v)
    db.flush()
    audit.record(db, actor, "vendor.created", "vendor", v.id, new=audit.snapshot(v))
    db.commit()
    return v


@router.get("/vendors/{vendor_id}", response_model=VendorOut)
def get_vendor(vendor_id: uuid.UUID, db: DB, actor: CurrentActor):
    v = get_scoped(db, Vendor, vendor_id, actor, "Vendor")
    if not (actor.can("vendors.read") or (actor.role == Role.VENDOR and actor.user.vendor_id == v.id)):
        raise HTTPException(404, "Vendor not found")
    return v


@router.patch("/vendors/{vendor_id}", response_model=VendorOut)
def update_vendor(vendor_id: uuid.UUID, body: VendorUpdate, db: DB, actor: Perm("vendors.manage")):
    v = get_scoped(db, Vendor, vendor_id, actor, "Vendor")
    before = audit.snapshot(v)
    apply(v, body.model_dump(exclude_unset=True))
    old, new = audit.diff(before, audit.snapshot(v))
    audit.record(db, actor, "vendor.updated", "vendor", v.id, old=old, new=new)
    if body.is_active is False:
        for u in db.scalars(select(User).where(User.vendor_id == v.id)):
            u.is_active = False
            u.token_version += 1
    db.commit()
    return v


@router.get("/vendors/{vendor_id}/performance")
def vendor_performance(vendor_id: uuid.UUID, db: DB, actor: Perm("vendors.read")):
    from app.services.reports import vendor_performance_rows

    v = get_scoped(db, Vendor, vendor_id, actor, "Vendor")
    rows = vendor_performance_rows(db, actor.tenant_id, vendor_id=v.id)
    return rows[0] if rows else {"vendor_id": v.id, "vendor": v.name, "jobs": 0}


# ------------------------------------------------------------------ staff


def _staff_out(p: StaffProfile) -> StaffOut:
    o = StaffOut.model_validate(p)
    if p.user:
        o.full_name, o.role, o.phone = p.user.full_name, p.user.role, p.user.phone
    return o


@router.get("/staff", response_model=list[StaffOut])
def list_staff(db: DB, actor: Perm("staff.read"), role: Role | None = None, active: bool | None = None):
    stmt = select(StaffProfile).join(User, User.id == StaffProfile.user_id).where(StaffProfile.tenant_id == actor.tenant_id)
    if role:
        stmt = stmt.where(User.role == role)
    if active is not None:
        stmt = stmt.where(StaffProfile.is_active.is_(active))
    return [_staff_out(p) for p in db.scalars(stmt.order_by(User.full_name))]


@router.post("/staff", response_model=StaffOut, status_code=201)
def create_staff(body: StaffIn, db: DB, actor: Perm("staff.manage")):
    u = db.get(User, body.user_id)
    if not u or u.tenant_id != actor.tenant_id or u.role not in (Role.STAFF, Role.GUARD, Role.SUPERVISOR):
        raise HTTPException(422, "Staff profiles are for staff, guards and supervisors")
    p = db.scalar(select(StaffProfile).where(StaffProfile.user_id == u.id))
    if p:
        raise HTTPException(409, "Profile already exists")
    p = StaffProfile(tenant_id=actor.tenant_id, **body.model_dump())
    db.add(p)
    db.flush()
    audit.record(db, actor, "staff.created", "staff", p.id, new=body.model_dump())
    db.commit()
    db.refresh(p)
    return _staff_out(p)


@router.patch("/staff/{staff_id}", response_model=StaffOut)
def update_staff(staff_id: uuid.UUID, body: StaffUpdate, db: DB, actor: Perm("staff.manage")):
    p = get_scoped(db, StaffProfile, staff_id, actor, "Staff")
    before = audit.snapshot(p)
    apply(p, body.model_dump(exclude_unset=True))
    old, new = audit.diff(before, audit.snapshot(p))
    audit.record(db, actor, "staff.updated", "staff", p.id, old=old, new=new)
    db.commit()
    return _staff_out(p)


@router.get("/staff/{user_id}/work-history")
def staff_history(user_id: uuid.UUID, db: DB, actor: Perm("staff.read")):
    from app.api.v1.maintenance import summaries

    u = db.get(User, user_id)
    if not u or u.tenant_id != actor.tenant_id:
        raise HTTPException(404, "Staff not found")
    tasks = list(
        db.scalars(
            tenant_select(MaintenanceTask, actor)
            .where(MaintenanceTask.assigned_staff_id == u.id)
            .order_by(MaintenanceTask.created_at.desc())
            .limit(200)
        )
    )
    done = [t for t in tasks if t.status in (TaskStatus.APPROVED, TaskStatus.CLOSED)]
    return {
        "user_id": u.id,
        "name": u.full_name,
        "assigned": len(tasks),
        "completed": len(done),
        "rework": sum(1 for t in tasks if t.rework_count),
        "tasks": summaries(db, tasks),
    }


# ------------------------------------------------------------------ attendance


@router.post("/staff/attendance/check-in", response_model=AttendanceOut)
def check_in(body: GeoPoint, db: DB, actor: Perm("attendance.self")):
    today = date.today()
    row = db.scalar(select(Attendance).where(Attendance.user_id == actor.id, Attendance.work_date == today))
    if row and row.check_in_at:
        return row
    row = row or Attendance(tenant_id=actor.tenant_id, user_id=actor.id, work_date=today)
    row.check_in_at = utcnow()
    row.latitude, row.longitude = body.latitude, body.longitude
    db.add(row)
    audit.record(db, actor, "attendance.check_in", "attendance", None, new={"date": today})
    db.commit()
    return row


@router.post("/staff/attendance/check-out", response_model=AttendanceOut)
def check_out(body: GeoPoint, db: DB, actor: Perm("attendance.self")):
    row = db.scalar(select(Attendance).where(Attendance.user_id == actor.id, Attendance.work_date == date.today()))
    if not row or not row.check_in_at:
        raise HTTPException(409, "Check in first")
    row.check_out_at = utcnow()
    audit.record(db, actor, "attendance.check_out", "attendance", row.id)
    db.commit()
    return row


@router.get("/staff/attendance", response_model=list[AttendanceOut])
def attendance(db: DB, actor: CurrentActor, user_id: uuid.UUID | None = None, date_from: date | None = None, date_to: date | None = None):
    if not actor.can("staff.read"):
        user_id = actor.id
    stmt = select(Attendance).where(Attendance.tenant_id == actor.tenant_id)
    if user_id:
        stmt = stmt.where(Attendance.user_id == user_id)
    if date_from:
        stmt = stmt.where(Attendance.work_date >= date_from)
    if date_to:
        stmt = stmt.where(Attendance.work_date <= date_to)
    return list(db.scalars(stmt.order_by(Attendance.work_date.desc()).limit(500)))


@router.get("/staff/on-duty")
def on_duty(db: DB, actor: Perm("staff.read")):
    rows = db.execute(
        select(User.id, User.full_name, User.role, Attendance.check_in_at)
        .join(Attendance, Attendance.user_id == User.id)
        .where(Attendance.tenant_id == actor.tenant_id, Attendance.work_date == date.today(), Attendance.check_out_at.is_(None))
    ).all()
    return [{"user_id": r.id, "name": r.full_name, "role": r.role, "since": r.check_in_at} for r in rows]
