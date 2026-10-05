"""Tenant isolation and row-level visibility (requirements §24-25)."""

import uuid
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy import Select, false, or_, select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import (
    Asset,
    Complaint,
    Incident,
    Inspection,
    MaintenanceTask,
    PatrolRun,
    Property,
    Resident,
    Vehicle,
    Vendor,
    Visitor,
)
from app.models.enums import Role

T = TypeVar("T")


def not_found(what: str = "Record") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def get_scoped(db: Session, model: type[T], obj_id: uuid.UUID, actor: Actor, what: str | None = None, include_deleted: bool = False) -> T:
    """Fetch a tenant-owned row; rows from other tenants are indistinguishable from missing ones."""
    obj = db.get(model, obj_id)
    deleted = getattr(obj, "deleted_at", None) and not include_deleted
    if obj is None or getattr(obj, "tenant_id", None) != actor.tenant_id or deleted:
        raise not_found(what or model.__name__)
    return obj


def tenant_select(model, actor: Actor) -> Select:
    stmt = select(model).where(model.tenant_id == actor.tenant_id)
    if hasattr(model, "deleted_at"):
        stmt = stmt.where(model.deleted_at.is_(None))
    return stmt


def resident_property_ids(db: Session, actor: Actor) -> set[uuid.UUID]:
    if actor.role != Role.RESIDENT:
        return set()
    ids = set(
        db.scalars(
            select(Resident.property_id).where(
                Resident.tenant_id == actor.tenant_id, Resident.user_id == actor.id, Resident.deleted_at.is_(None)
            )
        )
    )
    ids |= set(
        db.scalars(
            select(Property.id).where(
                Property.tenant_id == actor.tenant_id, Property.owner_user_id == actor.id, Property.deleted_at.is_(None)
            )
        )
    )
    return ids


# --------------------------------------------------------------------------- maintenance


def scope_tasks(stmt: Select, db: Session, actor: Actor) -> Select:
    if actor.is_manager():
        return stmt
    if actor.role == Role.STAFF:
        return stmt.where(MaintenanceTask.assigned_staff_id == actor.id)
    if actor.role == Role.VENDOR:
        if actor.user.vendor_id is None:
            return stmt.where(false())
        return stmt.where(MaintenanceTask.vendor_id == actor.user.vendor_id)
    if actor.role == Role.RESIDENT:
        return stmt.where(MaintenanceTask.property_id.in_(resident_property_ids(db, actor) or {uuid.uuid4()}))
    return stmt.where(false())


def can_view_task(db: Session, actor: Actor, task: MaintenanceTask) -> bool:
    if task.tenant_id != actor.tenant_id:
        return False
    if actor.is_manager():
        return True
    if actor.role == Role.STAFF:
        return task.assigned_staff_id == actor.id
    if actor.role == Role.VENDOR:
        return actor.user.vendor_id is not None and task.vendor_id == actor.user.vendor_id
    if actor.role == Role.RESIDENT:
        return task.property_id in resident_property_ids(db, actor)
    return False


def is_task_worker(actor: Actor, task: MaintenanceTask) -> bool:
    if actor.role == Role.VENDOR:
        return actor.user.vendor_id is not None and task.vendor_id == actor.user.vendor_id
    return task.assigned_staff_id == actor.id


def get_task(db: Session, actor: Actor, task_id: uuid.UUID) -> MaintenanceTask:
    task = get_scoped(db, MaintenanceTask, task_id, actor, "Maintenance task")
    if not can_view_task(db, actor, task):
        raise not_found("Maintenance task")
    return task


# --------------------------------------------------------------------------- complaints & inspections


def scope_complaints(stmt: Select, db: Session, actor: Actor) -> Select:
    if actor.is_manager():
        return stmt
    if actor.role == Role.RESIDENT:
        props = resident_property_ids(db, actor) or {uuid.uuid4()}
        return stmt.where(or_(Complaint.raised_by == actor.id, Complaint.property_id.in_(props)))
    if actor.role == Role.STAFF:
        return stmt.where(or_(Complaint.assigned_staff_id == actor.id, Complaint.raised_by == actor.id))
    if actor.role == Role.VENDOR and actor.user.vendor_id:
        return stmt.where(Complaint.vendor_id == actor.user.vendor_id)
    return stmt.where(Complaint.raised_by == actor.id)


def can_view_complaint(db: Session, actor: Actor, c: Complaint) -> bool:
    if actor.is_manager():
        return True
    if c.raised_by == actor.id:
        return True
    if actor.role == Role.RESIDENT:
        return c.property_id in resident_property_ids(db, actor)
    if actor.role == Role.STAFF:
        return c.assigned_staff_id == actor.id
    if actor.role == Role.VENDOR:
        return actor.user.vendor_id is not None and c.vendor_id == actor.user.vendor_id
    return False


def scope_inspections(stmt: Select, db: Session, actor: Actor) -> Select:
    if actor.is_manager():
        return stmt
    if actor.role == Role.RESIDENT:
        return stmt.where(Inspection.property_id.in_(resident_property_ids(db, actor) or {uuid.uuid4()}))
    if actor.role == Role.STAFF:
        return stmt.where(Inspection.inspector_id == actor.id)
    return stmt.where(false())


def can_view_inspection(db: Session, actor: Actor, i: Inspection) -> bool:
    if actor.is_manager():
        return True
    if actor.role == Role.RESIDENT:
        return i.property_id in resident_property_ids(db, actor)
    if actor.role == Role.STAFF:
        return i.inspector_id == actor.id
    return False


def can_view_property(db: Session, actor: Actor, property_id: uuid.UUID | None) -> bool:
    if actor.role == Role.RESIDENT:
        return property_id in resident_property_ids(db, actor)
    return actor.can("properties.read")


# --------------------------------------------------------------------------- generic entity access (media)

MEDIA_ENTITY_TYPES = {
    "maintenance_task",
    "complaint",
    "inspection",
    "incident",
    "property",
    "asset",
    "visitor",
    "vehicle",
    "patrol_run",
    "vendor",
}


def check_entity_access(db: Session, actor: Actor, entity_type: str, entity_id: uuid.UUID, write: bool = False):
    """Return the entity if the actor may view (or attach media to) it, else raise 404/403."""
    if entity_type not in MEDIA_ENTITY_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unsupported entity type: {entity_type}")

    if entity_type == "maintenance_task":
        task = get_task(db, actor, entity_id)
        if write and not (actor.is_manager() or is_task_worker(actor, task)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the assigned worker or a supervisor can add evidence")
        return task
    if entity_type == "complaint":
        c = get_scoped(db, Complaint, entity_id, actor, "Complaint")
        if not can_view_complaint(db, actor, c):
            raise not_found("Complaint")
        return c
    if entity_type == "inspection":
        i = get_scoped(db, Inspection, entity_id, actor, "Inspection")
        if not can_view_inspection(db, actor, i):
            raise not_found("Inspection")
        return i
    if entity_type == "incident":
        inc = get_scoped(db, Incident, entity_id, actor, "Incident")
        if actor.role == Role.RESIDENT and inc.reported_by != actor.id:
            raise not_found("Incident")
        if not (actor.can("incidents.read") or actor.can("incidents.create")):
            raise not_found("Incident")
        return inc
    if entity_type == "property":
        p = get_scoped(db, Property, entity_id, actor, "Property")
        if not can_view_property(db, actor, p.id):
            raise not_found("Property")
        if write and not actor.can("properties.manage") and actor.role != Role.RESIDENT:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot attach media to this property")
        return p
    if entity_type == "asset":
        a = get_scoped(db, Asset, entity_id, actor, "Asset")
        if not actor.can("assets.read"):
            raise not_found("Asset")
        return a
    if entity_type == "visitor":
        v = get_scoped(db, Visitor, entity_id, actor, "Visitor")
        if actor.role == Role.RESIDENT and v.property_id not in resident_property_ids(db, actor):
            raise not_found("Visitor")
        if not actor.can("visitors.read"):
            raise not_found("Visitor")
        return v
    if entity_type == "vehicle":
        v = get_scoped(db, Vehicle, entity_id, actor, "Vehicle")
        if not actor.can("vehicles.read"):
            raise not_found("Vehicle")
        return v
    if entity_type == "patrol_run":
        r = get_scoped(db, PatrolRun, entity_id, actor, "Patrol run")
        if not actor.can("patrol.read"):
            raise not_found("Patrol run")
        return r
    if entity_type == "vendor":
        v = get_scoped(db, Vendor, entity_id, actor, "Vendor")
        if not (actor.can("vendors.read") or (actor.role == Role.VENDOR and actor.user.vendor_id == v.id)):
            raise not_found("Vendor")
        return v
    raise not_found()
