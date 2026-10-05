"""Visitor, vehicle, patrol, incident and SOS operations (§18).

Shared by the REST routers and the offline /sync endpoint so both paths apply the
same validation, audit and notifications.
"""

import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import (
    Incident,
    IncidentUpdate,
    PatrolCheckpoint,
    PatrolRun,
    PatrolScan,
    Property,
    Resident,
    SosAlert,
    Vehicle,
    VehicleLog,
    Visitor,
)
from app.models.base import utcnow
from app.models.enums import IncidentStatus, Role, SosStatus, VisitorStatus
from app.services import audit, notifications
from app.services.access import get_scoped, resident_property_ids
from app.services.numbering import next_number


def norm_plate(number: str) -> str:
    return "".join(ch for ch in number.upper() if ch.isalnum())


def _property_users(db: Session, property_id: uuid.UUID | None) -> list[uuid.UUID]:
    if not property_id:
        return []
    p = db.get(Property, property_id)
    users = [p.owner_user_id] if p else []
    users += list(
        db.scalars(
            select(Resident.user_id).where(
                Resident.property_id == property_id, Resident.user_id.is_not(None), Resident.deleted_at.is_(None)
            )
        )
    )
    return [u for u in users if u]


# ------------------------------------------------------------------ visitors


def register_visitor(db: Session, actor: Actor, data: dict) -> Visitor:
    """Residents pre-approve expected visitors; guards register arrivals at the gate."""
    check_in_now = data.pop("check_in_now", True)
    if data.get("property_id"):
        get_scoped(db, Property, data["property_id"], actor, "Property")
    if data.get("vehicle_number"):
        data["vehicle_number"] = norm_plate(data["vehicle_number"])
    now = utcnow()

    if actor.role == Role.RESIDENT:
        if data.get("property_id") not in resident_property_ids(db, actor):
            raise HTTPException(403, "Pre-approve visitors for your own property only")
        v = Visitor(
            tenant_id=actor.tenant_id,
            created_by=actor.id,
            pre_approved=True,
            status=VisitorStatus.APPROVED,
            approved_by=actor.id,
            approved_at=now,
            **data,
        )
        db.add(v)
        db.flush()
        audit.record(db, actor, "visitor.preapproved", "visitor", v.id, new={"name": v.name, "property_id": v.property_id})
        return v

    pre = None
    if data.get("phone") and data.get("property_id"):
        pre = db.scalar(
            select(Visitor).where(
                Visitor.tenant_id == actor.tenant_id,
                Visitor.pre_approved.is_(True),
                Visitor.status == VisitorStatus.APPROVED,
                Visitor.property_id == data["property_id"],
                Visitor.phone == data["phone"],
                Visitor.entry_at.is_(None),
            )
        )
    if pre:
        v = pre
        v.vehicle_number = v.vehicle_number or data.get("vehicle_number")
        v.photo_media_id = v.photo_media_id or data.get("photo_media_id")
    else:
        v = Visitor(tenant_id=actor.tenant_id, created_by=actor.id, status=VisitorStatus.PENDING_APPROVAL, **data)
        db.add(v)
    v.guard_id = actor.id
    # Visits to common areas (no host property) need no resident approval.
    if not v.property_id and not pre:
        v.status = VisitorStatus.APPROVED
        v.approved_by, v.approved_at = actor.id, now
    db.flush()
    if v.status == VisitorStatus.APPROVED and check_in_now:
        v.status, v.entry_at = VisitorStatus.INSIDE, now
        if v.vehicle_number:
            db.add(
                VehicleLog(
                    tenant_id=actor.tenant_id,
                    vehicle_number=v.vehicle_number,
                    visitor_id=v.id,
                    is_visitor=True,
                    direction="in",
                    at=now,
                    guard_id=actor.id,
                )
            )
    elif v.status == VisitorStatus.PENDING_APPROVAL:
        notifications.notify(
            db, actor.tenant_id, _property_users(db, v.property_id), "visitor", f"Visitor at the gate: {v.name}", v.purpose, "visitor", v.id
        )
    audit.record(
        db,
        actor,
        "visitor.registered",
        "visitor",
        v.id,
        new={"name": v.name, "status": v.status, "property_id": v.property_id, "pre_approved": bool(pre)},
    )
    return v


def decide_visitor(db: Session, actor: Actor, v: Visitor, approve: bool) -> Visitor:
    if v.status != VisitorStatus.PENDING_APPROVAL:
        raise HTTPException(409, f"Visitor is {v.status}")
    if actor.role == Role.RESIDENT and v.property_id not in resident_property_ids(db, actor):
        raise HTTPException(403, "Not your visitor")
    v.status = VisitorStatus.APPROVED if approve else VisitorStatus.DENIED
    v.approved_by, v.approved_at = actor.id, utcnow()
    audit.record(db, actor, "visitor.approved" if approve else "visitor.denied", "visitor", v.id)
    if v.guard_id:
        notifications.notify(
            db, v.tenant_id, [v.guard_id], "visitor", f"{v.name}: {'approved' if approve else 'denied'}", None, "visitor", v.id
        )
    return v


def visitor_entry(db: Session, actor: Actor, v: Visitor, at: datetime | None = None) -> Visitor:
    if v.status not in (VisitorStatus.APPROVED,):
        raise HTTPException(409, f"Visitor is {v.status}; approval is required before entry")
    v.status, v.entry_at, v.guard_id = VisitorStatus.INSIDE, at or utcnow(), actor.id
    audit.record(db, actor, "visitor.entry", "visitor", v.id)
    return v


def visitor_exit(db: Session, actor: Actor, v: Visitor, at: datetime | None = None) -> Visitor:
    if v.status == VisitorStatus.EXITED:
        return v
    if v.status != VisitorStatus.INSIDE:
        raise HTTPException(409, f"Visitor is {v.status}")
    v.status, v.exit_at = VisitorStatus.EXITED, at or utcnow()
    if v.vehicle_number:
        db.add(
            VehicleLog(
                tenant_id=v.tenant_id,
                vehicle_number=v.vehicle_number,
                visitor_id=v.id,
                is_visitor=True,
                direction="out",
                at=v.exit_at,
                guard_id=actor.id,
            )
        )
    audit.record(db, actor, "visitor.exit", "visitor", v.id)
    return v


# ------------------------------------------------------------------ vehicles


def log_vehicle(db: Session, actor: Actor, data: dict) -> VehicleLog:
    plate = norm_plate(data["vehicle_number"])
    vehicle = db.scalar(select(Vehicle).where(Vehicle.tenant_id == actor.tenant_id, Vehicle.number == plate, Vehicle.deleted_at.is_(None)))
    log = VehicleLog(
        tenant_id=actor.tenant_id,
        vehicle_number=plate,
        vehicle_id=vehicle.id if vehicle else None,
        visitor_id=data.get("visitor_id"),
        is_visitor=vehicle is None,
        direction=data["direction"],
        at=data.get("at") or utcnow(),
        guard_id=actor.id,
        photo_media_id=data.get("photo_media_id"),
        notes=data.get("notes"),
    )
    db.add(log)
    db.flush()
    audit.record(db, actor, f"vehicle.{data['direction']}", "vehicle", vehicle.id if vehicle else None, new={"number": plate})
    return log


# ------------------------------------------------------------------ patrol


def start_patrol(db: Session, actor: Actor, route_id: uuid.UUID, at: datetime | None = None) -> PatrolRun:
    from app.models import PatrolRoute

    route = get_scoped(db, PatrolRoute, route_id, actor, "Patrol route")
    if not route.is_active:
        raise HTTPException(409, "Route is inactive")
    run = PatrolRun(tenant_id=actor.tenant_id, route_id=route.id, guard_id=actor.id, started_at=at or utcnow())
    db.add(run)
    db.flush()
    audit.record(db, actor, "patrol.started", "patrol_run", run.id, new={"route": route.name})
    return run


def scan_checkpoint(db: Session, actor: Actor, run: PatrolRun, data: dict) -> PatrolScan:
    if run.guard_id != actor.id:
        raise HTTPException(403, "Not your patrol")
    if run.status != "in_progress":
        raise HTTPException(409, "Patrol already finished")
    code = data["code"]
    cp = db.scalar(
        select(PatrolCheckpoint).where(
            PatrolCheckpoint.route_id == run.route_id,
            (PatrolCheckpoint.qr_code == code) | (PatrolCheckpoint.nfc_id == code) | (PatrolCheckpoint.id == _maybe_uuid(code)),
        )
    )
    if not cp:
        raise HTTPException(422, "Checkpoint not on this route")
    scan = PatrolScan(
        tenant_id=run.tenant_id,
        run_id=run.id,
        checkpoint_id=cp.id,
        scanned_at=data.get("scanned_at") or utcnow(),
        method=data.get("method", "qr"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        photo_media_id=data.get("photo_media_id"),
        exception=data.get("exception"),
    )
    db.add(scan)
    db.flush()
    audit.record(db, actor, "patrol.checkpoint_scanned", "patrol_run", run.id, new={"checkpoint": cp.name, "exception": scan.exception})
    if scan.exception:
        notifications.notify(
            db,
            run.tenant_id,
            notifications.managers(db, run.tenant_id),
            "incident",
            f"Patrol exception at {cp.name}",
            scan.exception,
            "patrol_run",
            run.id,
        )
    return scan


def finish_patrol(db: Session, actor: Actor, run: PatrolRun, notes: str | None) -> PatrolRun:
    if run.guard_id != actor.id and not actor.is_manager():
        raise HTTPException(403, "Not your patrol")
    if run.status != "in_progress":
        return run
    scanned = {s.checkpoint_id for s in db.scalars(select(PatrolScan).where(PatrolScan.run_id == run.id))}
    all_cps = set(db.scalars(select(PatrolCheckpoint.id).where(PatrolCheckpoint.route_id == run.route_id)))
    run.status = "completed" if all_cps <= scanned else "incomplete"
    run.completed_at = utcnow()
    run.notes = notes
    audit.record(db, actor, "patrol.finished", "patrol_run", run.id, new={"status": run.status, "missed": len(all_cps - scanned)})
    return run


def _maybe_uuid(code: str):
    try:
        return uuid.UUID(code)
    except ValueError:
        return None


# ------------------------------------------------------------------ incidents & SOS

_INCIDENT_FLOW = {
    IncidentStatus.OPEN: {IncidentStatus.ACKNOWLEDGED, IncidentStatus.INVESTIGATING, IncidentStatus.RESOLVED},
    IncidentStatus.ACKNOWLEDGED: {IncidentStatus.INVESTIGATING, IncidentStatus.RESOLVED},
    IncidentStatus.INVESTIGATING: {IncidentStatus.RESOLVED},
    IncidentStatus.RESOLVED: {IncidentStatus.CLOSED, IncidentStatus.INVESTIGATING},
    IncidentStatus.CLOSED: set(),
}


def create_incident(db: Session, actor: Actor, data: dict, sos_id: uuid.UUID | None = None) -> Incident:
    data = {k: v for k, v in data.items() if k != "accuracy_m"}
    if data.get("property_id"):
        get_scoped(db, Property, data["property_id"], actor, "Property")
    inc = Incident(
        tenant_id=actor.tenant_id,
        number=next_number(db, actor.tenant_id, "INC"),
        reported_by=actor.id,
        occurred_at=data.pop("occurred_at", None) or utcnow(),
        sos_id=sos_id,
        **data,
    )
    db.add(inc)
    db.flush()
    audit.record(db, actor, "incident.created", "incident", inc.id, new=audit.snapshot(inc))
    recipients = notifications.users_with_roles(db, actor.tenant_id, [Role.GUARD, Role.SUPERVISOR, Role.LAYOUT_ADMIN])
    notifications.notify(
        db,
        actor.tenant_id,
        [r for r in recipients if r != actor.id],
        "incident",
        f"Incident {inc.number}: {inc.title}",
        inc.description,
        "incident",
        inc.id,
    )
    return inc


def change_incident(db: Session, actor: Actor, inc: Incident, target: str, note: str | None, assigned_to=None) -> Incident:
    target = IncidentStatus(target)
    if target not in _INCIDENT_FLOW[IncidentStatus(inc.status)]:
        raise HTTPException(409, f"Cannot move incident from {inc.status} to {target}")
    if target in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED) and not (note or inc.resolution):
        raise HTTPException(422, "A resolution note is required")
    old = inc.status
    inc.status = target
    now = utcnow()
    if target == IncidentStatus.ACKNOWLEDGED:
        inc.acknowledged_at = now
    if target == IncidentStatus.RESOLVED:
        inc.resolved_at, inc.resolution = now, note or inc.resolution
    if target == IncidentStatus.CLOSED:
        inc.closed_at = now
    if assigned_to:
        inc.assigned_to = assigned_to
    db.add(
        IncidentUpdate(
            tenant_id=inc.tenant_id,
            incident_id=inc.id,
            author_id=actor.id,
            body=note or f"Status: {target}",
            status_change=f"{old}->{target}",
        )
    )
    audit.record(db, actor, "incident.status_changed", "incident", inc.id, old={"status": old}, new={"status": target, "note": note})
    notifications.notify(db, inc.tenant_id, [inc.reported_by], "incident", f"{inc.number} is {target}", note, "incident", inc.id)
    return inc


def raise_sos(db: Session, actor: Actor, data: dict) -> SosAlert:
    pid = data.get("property_id")
    if actor.role == Role.RESIDENT and not pid:
        mine = resident_property_ids(db, actor)
        pid = next(iter(mine)) if len(mine) == 1 else None
    sos = SosAlert(
        tenant_id=actor.tenant_id,
        raised_by=actor.id,
        property_id=pid,
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        message=data.get("message"),
    )
    db.add(sos)
    db.flush()
    inc = create_incident(
        db,
        actor,
        dict(
            title=f"SOS raised by {actor.user.full_name}",
            description=data.get("message"),
            category="security",
            severity="critical",
            property_id=pid,
            latitude=sos.latitude,
            longitude=sos.longitude,
        ),
        sos_id=sos.id,
    )
    sos.incident_id = inc.id
    responders = notifications.users_with_roles(db, actor.tenant_id, [Role.GUARD, Role.SUPERVISOR, Role.LAYOUT_ADMIN])
    notifications.notify(
        db,
        actor.tenant_id,
        [r for r in responders if r != actor.id],
        "sos",
        f"SOS: {actor.user.full_name}",
        data.get("message") or "Emergency assistance requested",
        "sos",
        sos.id,
        channels=["in_app", "push", "sms", "whatsapp"],
    )
    audit.record(db, actor, "sos.raised", "sos", sos.id, new={"lat": sos.latitude, "lng": sos.longitude, "incident": inc.number})
    return sos


def act_on_sos(db: Session, actor: Actor, sos: SosAlert, action: str, note: str | None) -> SosAlert:
    now = utcnow()
    if sos.status in (SosStatus.RESOLVED, SosStatus.FALSE_ALARM):
        raise HTTPException(409, f"SOS already {sos.status}")
    if action == "acknowledge":
        if sos.status != SosStatus.ACTIVE:
            raise HTTPException(409, "SOS already acknowledged")
        sos.status, sos.acknowledged_by, sos.acknowledged_at = SosStatus.ACKNOWLEDGED, actor.id, now
        notifications.notify(
            db, sos.tenant_id, [sos.raised_by], "sos", f"Help is on the way — {actor.user.full_name} responded", note, "sos", sos.id
        )
    else:
        sos.status = SosStatus.RESOLVED if action == "resolve" else SosStatus.FALSE_ALARM
        sos.resolved_at = now
        sos.acknowledged_by = sos.acknowledged_by or actor.id
        sos.acknowledged_at = sos.acknowledged_at or now
        if sos.incident_id:
            inc = db.get(Incident, sos.incident_id)
            if inc and inc.status not in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
                change_incident(
                    db, actor, inc, IncidentStatus.RESOLVED, note or ("False alarm" if action == "false_alarm" else "SOS resolved")
                )
    audit.record(db, actor, f"sos.{action}", "sos", sos.id, new={"status": sos.status, "note": note})
    return sos
