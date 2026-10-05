import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import or_, select

from app.api.v1._util import Limit, Offset, paginate, property_labels, user_names
from app.core.deps import DB, CurrentActor, Perm
from app.models import (
    Incident,
    IncidentUpdate,
    PatrolCheckpoint,
    PatrolRoute,
    PatrolRun,
    PatrolScan,
    Property,
    SosAlert,
    Vehicle,
    VehicleLog,
    Visitor,
)
from app.models.base import utcnow
from app.models.enums import IncidentStatus, Role, SosStatus, VisitorStatus
from app.schemas.common import Page
from app.schemas.operations import (
    CheckpointIn,
    CheckpointOut,
    IncidentIn,
    IncidentOut,
    IncidentStatusIn,
    IncidentUpdateOut,
    PatrolFinishIn,
    PatrolRunOut,
    PatrolScanIn,
    PatrolScanOut,
    RouteIn,
    RouteOut,
    SosActionIn,
    SosIn,
    SosOut,
    VehicleIn,
    VehicleLogIn,
    VehicleLogOut,
    VehicleOut,
    VisitorDecisionIn,
    VisitorIn,
    VisitorOut,
)
from app.services import audit
from app.services import security_ops as ops
from app.services.access import get_scoped, not_found, resident_property_ids, tenant_select

router = APIRouter(tags=["security"])


# ------------------------------------------------------------------ visitors


def _visitors_out(db, vs: list[Visitor]) -> list[VisitorOut]:
    props = property_labels(db, (v.property_id for v in vs))
    return [VisitorOut.model_validate(v).model_copy(update={"property_label": props.get(v.property_id)}) for v in vs]


def _get_visitor(db, actor, visitor_id) -> Visitor:
    v = get_scoped(db, Visitor, visitor_id, actor, "Visitor")
    if actor.role == Role.RESIDENT and v.property_id not in resident_property_ids(db, actor):
        raise not_found("Visitor")
    return v


@router.get("/visitors", response_model=Page[VisitorOut])
def list_visitors(
    db: DB,
    actor: Perm("visitors.read"),
    status: VisitorStatus | None = None,
    property_id: uuid.UUID | None = None,
    inside: bool | None = None,
    q: str | None = None,
    date_from: datetime | None = None,
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = select(Visitor).where(Visitor.tenant_id == actor.tenant_id).order_by(Visitor.created_at.desc())
    if actor.role == Role.RESIDENT:
        stmt = stmt.where(Visitor.property_id.in_(resident_property_ids(db, actor) or {uuid.uuid4()}))
    if status:
        stmt = stmt.where(Visitor.status == status)
    if inside:
        stmt = stmt.where(Visitor.status == VisitorStatus.INSIDE)
    if property_id:
        stmt = stmt.where(Visitor.property_id == property_id)
    if q:
        stmt = stmt.where(or_(Visitor.name.ilike(f"%{q}%"), Visitor.phone.ilike(f"%{q}%"), Visitor.vehicle_number.ilike(f"%{q}%")))
    if date_from:
        stmt = stmt.where(Visitor.created_at >= date_from)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=_visitors_out(db, items), total=total, limit=limit, offset=offset)


@router.post("/visitors", response_model=VisitorOut, status_code=201)
def create_visitor(body: VisitorIn, db: DB, actor: CurrentActor):
    if not (actor.can("visitors.manage") or actor.can("visitors.preapprove")):
        raise HTTPException(403, "Missing permission: visitors.manage")
    v = ops.register_visitor(db, actor, body.model_dump())
    db.commit()
    return _visitors_out(db, [v])[0]


@router.post("/visitors/{visitor_id}/decision", response_model=VisitorOut)
def decide(visitor_id: uuid.UUID, body: VisitorDecisionIn, db: DB, actor: CurrentActor):
    if actor.role not in (Role.RESIDENT, Role.LAYOUT_ADMIN, Role.GUARD):
        raise HTTPException(403, "Not allowed")
    v = ops.decide_visitor(db, actor, _get_visitor(db, actor, visitor_id), body.approve)
    db.commit()
    return _visitors_out(db, [v])[0]


@router.post("/visitors/{visitor_id}/entry", response_model=VisitorOut)
def entry(visitor_id: uuid.UUID, db: DB, actor: Perm("visitors.manage")):
    v = ops.visitor_entry(db, actor, _get_visitor(db, actor, visitor_id))
    db.commit()
    return _visitors_out(db, [v])[0]


@router.post("/visitors/{visitor_id}/exit", response_model=VisitorOut)
def exit_(visitor_id: uuid.UUID, db: DB, actor: Perm("visitors.manage")):
    v = ops.visitor_exit(db, actor, _get_visitor(db, actor, visitor_id))
    db.commit()
    return _visitors_out(db, [v])[0]


# ------------------------------------------------------------------ vehicles


@router.get("/vehicles", response_model=Page[VehicleOut])
def list_vehicles(
    db: DB,
    actor: Perm("vehicles.read"),
    q: str | None = None,
    property_id: uuid.UUID | None = None,
    limit: int = Limit,
    offset: int = Offset,
):
    stmt = tenant_select(Vehicle, actor).order_by(Vehicle.number)
    if actor.role == Role.RESIDENT:
        stmt = stmt.where(Vehicle.property_id.in_(resident_property_ids(db, actor) or {uuid.uuid4()}))
    if q:
        stmt = stmt.where(Vehicle.number.ilike(f"%{ops.norm_plate(q)}%"))
    if property_id:
        stmt = stmt.where(Vehicle.property_id == property_id)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/vehicles", response_model=VehicleOut, status_code=201)
def register_vehicle(body: VehicleIn, db: DB, actor: Perm("vehicles.manage")):
    data = body.model_dump()
    data["number"] = ops.norm_plate(data["number"])
    if actor.role == Role.RESIDENT and data.get("property_id") not in resident_property_ids(db, actor):
        raise HTTPException(403, "Register vehicles for your own property")
    if data.get("property_id"):
        get_scoped(db, Property, data["property_id"], actor, "Property")
    if db.scalar(tenant_select(Vehicle, actor).where(Vehicle.number == data["number"])):
        raise HTTPException(409, "Vehicle already registered")
    v = Vehicle(tenant_id=actor.tenant_id, **data)
    db.add(v)
    db.flush()
    audit.record(db, actor, "vehicle.registered", "vehicle", v.id, new=data)
    db.commit()
    return v


@router.delete("/vehicles/{vehicle_id}", status_code=204)
def remove_vehicle(vehicle_id: uuid.UUID, db: DB, actor: Perm("vehicles.manage")):
    v = get_scoped(db, Vehicle, vehicle_id, actor, "Vehicle")
    if actor.role == Role.RESIDENT and v.property_id not in resident_property_ids(db, actor):
        raise not_found("Vehicle")
    v.deleted_at = utcnow()
    audit.record(db, actor, "vehicle.removed", "vehicle", v.id, old={"number": v.number})
    db.commit()


@router.post("/vehicles/log", response_model=VehicleLogOut, status_code=201)
def log_vehicle(body: VehicleLogIn, db: DB, actor: Perm("vehicles.log")):
    log = ops.log_vehicle(db, actor, body.model_dump())
    db.commit()
    return log


@router.get("/vehicles/log", response_model=Page[VehicleLogOut])
def vehicle_logs(db: DB, actor: Perm("vehicles.read"), number: str | None = None, limit: int = Limit, offset: int = Offset):
    if actor.role == Role.RESIDENT:
        raise HTTPException(403, "Gate logs are available to security staff")
    stmt = select(VehicleLog).where(VehicleLog.tenant_id == actor.tenant_id).order_by(VehicleLog.at.desc())
    if number:
        stmt = stmt.where(VehicleLog.vehicle_number.ilike(f"%{ops.norm_plate(number)}%"))
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


# ------------------------------------------------------------------ patrol


def _route_out(db, r: PatrolRoute) -> RouteOut:
    cps = db.scalars(select(PatrolCheckpoint).where(PatrolCheckpoint.route_id == r.id).order_by(PatrolCheckpoint.position))
    return RouteOut.model_validate(r).model_copy(update={"checkpoints": [CheckpointOut.model_validate(c) for c in cps]})


def _run_out(db, run: PatrolRun) -> PatrolRunOut:
    scans = db.scalars(select(PatrolScan).where(PatrolScan.run_id == run.id).order_by(PatrolScan.scanned_at))
    route = db.get(PatrolRoute, run.route_id)
    total = len(list(db.scalars(select(PatrolCheckpoint.id).where(PatrolCheckpoint.route_id == run.route_id))))
    return PatrolRunOut.model_validate(run).model_copy(
        update={
            "scans": [PatrolScanOut.model_validate(s) for s in scans],
            "route_name": route.name if route else None,
            "guard_name": user_names(db, [run.guard_id]).get(run.guard_id),
            "checkpoints_total": total,
        }
    )


@router.get("/patrol/routes", response_model=list[RouteOut])
def list_routes(db: DB, actor: Perm("patrol.read")):
    return [_route_out(db, r) for r in db.scalars(tenant_select(PatrolRoute, actor).order_by(PatrolRoute.name))]


@router.post("/patrol/routes", response_model=RouteOut, status_code=201)
def create_route(body: RouteIn, db: DB, actor: Perm("patrol.manage")):
    r = PatrolRoute(tenant_id=actor.tenant_id, name=body.name, description=body.description)
    db.add(r)
    db.flush()
    for i, cp in enumerate(body.checkpoints):
        db.add(
            PatrolCheckpoint(
                tenant_id=actor.tenant_id,
                route_id=r.id,
                **{**cp.model_dump(), "position": cp.position or i, "qr_code": cp.qr_code or f"GP-CP-{secrets.token_hex(5).upper()}"},
            )
        )
    audit.record(db, actor, "patrol.route_created", "patrol_route", r.id, new={"name": r.name, "checkpoints": len(body.checkpoints)})
    db.commit()
    return _route_out(db, r)


@router.post("/patrol/routes/{route_id}/checkpoints", response_model=CheckpointOut, status_code=201)
def add_checkpoint(route_id: uuid.UUID, body: CheckpointIn, db: DB, actor: Perm("patrol.manage")):
    r = get_scoped(db, PatrolRoute, route_id, actor, "Route")
    cp = PatrolCheckpoint(
        tenant_id=actor.tenant_id,
        route_id=r.id,
        **{**body.model_dump(), "qr_code": body.qr_code or f"GP-CP-{secrets.token_hex(5).upper()}"},
    )
    db.add(cp)
    db.commit()
    return cp


@router.get("/patrol/checkpoints/{checkpoint_id}/qr.svg")
def checkpoint_qr(checkpoint_id: uuid.UUID, db: DB, actor: Perm("patrol.read")):
    from app.services.qr import qr_svg

    cp = get_scoped(db, PatrolCheckpoint, checkpoint_id, actor, "Checkpoint")
    return Response(qr_svg(cp.qr_code, caption=cp.name), media_type="image/svg+xml")


@router.post("/patrol/routes/{route_id}/start", response_model=PatrolRunOut, status_code=201)
def start_patrol(route_id: uuid.UUID, db: DB, actor: Perm("patrol.perform")):
    run = ops.start_patrol(db, actor, route_id)
    db.commit()
    return _run_out(db, run)


@router.post("/patrol/runs/{run_id}/scan", response_model=PatrolRunOut)
def scan(run_id: uuid.UUID, body: PatrolScanIn, db: DB, actor: Perm("patrol.perform")):
    run = get_scoped(db, PatrolRun, run_id, actor, "Patrol")
    ops.scan_checkpoint(db, actor, run, body.model_dump())
    db.commit()
    return _run_out(db, run)


@router.post("/patrol/runs/{run_id}/finish", response_model=PatrolRunOut)
def finish(run_id: uuid.UUID, body: PatrolFinishIn, db: DB, actor: Perm("patrol.read")):
    run = get_scoped(db, PatrolRun, run_id, actor, "Patrol")
    ops.finish_patrol(db, actor, run, body.notes)
    db.commit()
    return _run_out(db, run)


@router.get("/patrol/runs", response_model=list[PatrolRunOut])
def list_runs(db: DB, actor: Perm("patrol.read"), active: bool | None = None, limit: int = Limit):
    stmt = select(PatrolRun).where(PatrolRun.tenant_id == actor.tenant_id).order_by(PatrolRun.started_at.desc())
    if actor.role == Role.GUARD:
        stmt = stmt.where(PatrolRun.guard_id == actor.id)
    if active:
        stmt = stmt.where(PatrolRun.status == "in_progress")
    return [_run_out(db, r) for r in db.scalars(stmt.limit(limit))]


@router.get("/patrol/runs/{run_id}", response_model=PatrolRunOut)
def get_run(run_id: uuid.UUID, db: DB, actor: Perm("patrol.read")):
    return _run_out(db, get_scoped(db, PatrolRun, run_id, actor, "Patrol"))


# ------------------------------------------------------------------ incidents


def _incident_visible(db, actor, inc: Incident) -> bool:
    if actor.role == Role.RESIDENT:
        return inc.reported_by == actor.id or (inc.property_id in resident_property_ids(db, actor))
    if actor.role == Role.STAFF:
        return inc.reported_by == actor.id
    return actor.can("incidents.read")


def _incident_out(db, inc: Incident, updates=False) -> IncidentOut:
    o = IncidentOut.model_validate(inc)
    o.reported_by_name = user_names(db, [inc.reported_by]).get(inc.reported_by)
    if updates:
        rows = list(db.scalars(select(IncidentUpdate).where(IncidentUpdate.incident_id == inc.id).order_by(IncidentUpdate.created_at)))
        names = user_names(db, (r.author_id for r in rows))
        o.updates = [IncidentUpdateOut.model_validate(r).model_copy(update={"author_name": names.get(r.author_id)}) for r in rows]
    return o


@router.get("/incidents", response_model=Page[IncidentOut])
def list_incidents(
    db: DB,
    actor: CurrentActor,
    status: IncidentStatus | None = None,
    severity: str | None = None,
    property_id: uuid.UUID | None = None,
    open_only: bool = False,
    limit: int = Limit,
    offset: int = Offset,
):
    if not (actor.can("incidents.read") or actor.can("incidents.create")):
        raise HTTPException(403, "Missing permission: incidents.read")
    stmt = tenant_select(Incident, actor).order_by(Incident.occurred_at.desc())
    if actor.role == Role.RESIDENT:
        stmt = stmt.where(
            or_(Incident.reported_by == actor.id, Incident.property_id.in_(resident_property_ids(db, actor) or {uuid.uuid4()}))
        )
    elif actor.role == Role.STAFF:
        stmt = stmt.where(Incident.reported_by == actor.id)
    if status:
        stmt = stmt.where(Incident.status == status)
    if open_only:
        stmt = stmt.where(Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED, IncidentStatus.INVESTIGATING]))
    if severity:
        stmt = stmt.where(Incident.severity == severity)
    if property_id:
        stmt = stmt.where(Incident.property_id == property_id)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=[_incident_out(db, i) for i in items], total=total, limit=limit, offset=offset)


@router.post("/incidents", response_model=IncidentOut, status_code=201)
def create_incident(body: IncidentIn, db: DB, actor: Perm("incidents.create")):
    inc = ops.create_incident(db, actor, body.model_dump())
    db.commit()
    return _incident_out(db, inc)


@router.get("/incidents/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: uuid.UUID, db: DB, actor: CurrentActor):
    inc = get_scoped(db, Incident, incident_id, actor, "Incident")
    if not _incident_visible(db, actor, inc):
        raise not_found("Incident")
    return _incident_out(db, inc, updates=True)


@router.post("/incidents/{incident_id}/status", response_model=IncidentOut)
def incident_status(incident_id: uuid.UUID, body: IncidentStatusIn, db: DB, actor: Perm("incidents.manage")):
    inc = get_scoped(db, Incident, incident_id, actor, "Incident")
    ops.change_incident(db, actor, inc, body.status, body.note, body.assigned_to)
    db.commit()
    return _incident_out(db, inc, updates=True)


@router.post("/incidents/{incident_id}/updates", response_model=IncidentOut)
def incident_note(incident_id: uuid.UUID, body: PatrolFinishIn, db: DB, actor: Perm("incidents.manage")):
    inc = get_scoped(db, Incident, incident_id, actor, "Incident")
    if not body.notes:
        raise HTTPException(422, "Note is required")
    db.add(IncidentUpdate(tenant_id=inc.tenant_id, incident_id=inc.id, author_id=actor.id, body=body.notes))
    audit.record(db, actor, "incident.note_added", "incident", inc.id, new={"note": body.notes})
    db.commit()
    return _incident_out(db, inc, updates=True)


# ------------------------------------------------------------------ SOS


def _sos_out(db, s: SosAlert) -> SosOut:
    return SosOut.model_validate(s).model_copy(update={"raised_by_name": user_names(db, [s.raised_by]).get(s.raised_by)})


@router.post("/sos", response_model=SosOut, status_code=201)
def raise_sos(body: SosIn, db: DB, actor: Perm("sos.raise")):
    sos = ops.raise_sos(db, actor, body.model_dump())
    db.commit()
    return _sos_out(db, sos)


@router.get("/sos", response_model=list[SosOut])
def list_sos(db: DB, actor: CurrentActor, active: bool = True):
    stmt = select(SosAlert).where(SosAlert.tenant_id == actor.tenant_id).order_by(SosAlert.created_at.desc())
    if not actor.can("sos.respond"):
        stmt = stmt.where(SosAlert.raised_by == actor.id)
    if active:
        stmt = stmt.where(SosAlert.status.in_([SosStatus.ACTIVE, SosStatus.ACKNOWLEDGED]))
    return [_sos_out(db, s) for s in db.scalars(stmt.limit(100))]


@router.post("/sos/{sos_id}/action", response_model=SosOut)
def sos_action(sos_id: uuid.UUID, body: SosActionIn, db: DB, actor: CurrentActor):
    sos = get_scoped(db, SosAlert, sos_id, actor, "SOS")
    # The person who raised an SOS may cancel it as a false alarm.
    if not actor.can("sos.respond") and not (sos.raised_by == actor.id and body.action == "false_alarm"):
        raise HTTPException(403, "Missing permission: sos.respond")
    ops.act_on_sos(db, actor, sos, body.action, body.note)
    db.commit()
    return _sos_out(db, sos)
