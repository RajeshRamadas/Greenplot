"""Offline queue replay (requirements §30).

Each client operation carries a client_op_id. Replays of the same id return the
stored result instead of re-applying the change, so the PWA can retry freely.
Operations run in their own savepoint: one failure does not discard the batch.

Operations created offline can reference each other: a patrol scan queued
before its patrol run reached the server sends ``run_op_id`` (the client_op_id
of the patrol.start operation) instead of ``run_id``.
"""

import uuid
from collections.abc import Callable
from datetime import datetime

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import Attendance, Complaint, MaintenanceMaterial, PatrolRun, SyncOperation, Visitor
from app.models.base import utcnow
from app.models.enums import SyncState
from app.services import audit
from app.services import maintenance as msvc
from app.services import security_ops as ops
from app.services.access import get_scoped, get_task
from app.services.numbering import next_number


def _uuid(v) -> uuid.UUID:
    try:
        return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))
    except (TypeError, ValueError):
        raise HTTPException(422, f"Invalid id: {v}")


def _resolve_ref(db: Session, actor: Actor, payload: dict, id_key: str, ref_key: str) -> uuid.UUID:
    if payload.get(id_key):
        return _uuid(payload[id_key])
    ref = payload.get(ref_key)
    if not ref:
        raise HTTPException(422, f"{id_key} is required")
    prior = db.scalar(select(SyncOperation).where(SyncOperation.user_id == actor.id, SyncOperation.client_op_id == ref))
    if not prior or prior.status != SyncState.SYNCED or not prior.result:
        raise HTTPException(409, f"Referenced operation {ref} has not synced yet")
    return _uuid(prior.result["id"])


def _dt(v) -> datetime | None:
    if not v:
        return None
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace("Z", "+00:00"))


# ------------------------------------------------------------------ handlers


def visitor_create(db, actor, p, ts):
    if not (actor.can("visitors.manage") or actor.can("visitors.preapprove")):
        raise HTTPException(403, "Not allowed")
    from app.schemas.operations import VisitorIn

    data = VisitorIn.model_validate(p).model_dump()
    v = ops.register_visitor(db, actor, data)
    if v.entry_at and ts:
        v.entry_at = ts
    return {"id": v.id, "status": v.status}


def visitor_exit(db, actor, p, ts):
    if not actor.can("visitors.manage"):
        raise HTTPException(403, "Not allowed")
    vid = _resolve_ref(db, actor, p, "visitor_id", "visitor_op_id")
    v = ops.visitor_exit(db, actor, get_scoped(db, Visitor, vid, actor, "Visitor"), ts)
    return {"id": v.id, "status": v.status}


def visitor_entry(db, actor, p, ts):
    if not actor.can("visitors.manage"):
        raise HTTPException(403, "Not allowed")
    v = ops.visitor_entry(db, actor, get_scoped(db, Visitor, _uuid(p.get("visitor_id")), actor, "Visitor"), ts)
    return {"id": v.id, "status": v.status}


def vehicle_log(db, actor, p, ts):
    if not actor.can("vehicles.log"):
        raise HTTPException(403, "Not allowed")
    from app.schemas.operations import VehicleLogIn

    data = VehicleLogIn.model_validate(p).model_dump()
    data["at"] = data.get("at") or ts
    log = ops.log_vehicle(db, actor, data)
    return {"id": log.id}


def patrol_start(db, actor, p, ts):
    if not actor.can("patrol.perform"):
        raise HTTPException(403, "Not allowed")
    run = ops.start_patrol(db, actor, _uuid(p.get("route_id")), ts)
    return {"id": run.id}


def patrol_scan(db, actor, p, ts):
    if not actor.can("patrol.perform"):
        raise HTTPException(403, "Not allowed")
    run = get_scoped(db, PatrolRun, _resolve_ref(db, actor, p, "run_id", "run_op_id"), actor, "Patrol")
    from app.schemas.operations import PatrolScanIn

    data = PatrolScanIn.model_validate(p).model_dump()
    data["scanned_at"] = data.get("scanned_at") or ts
    s = ops.scan_checkpoint(db, actor, run, data)
    return {"id": s.id, "run_id": run.id}


def patrol_finish(db, actor, p, ts):
    run = get_scoped(db, PatrolRun, _resolve_ref(db, actor, p, "run_id", "run_op_id"), actor, "Patrol")
    ops.finish_patrol(db, actor, run, p.get("notes"))
    return {"id": run.id, "status": run.status}


def incident_create(db, actor, p, ts):
    if not actor.can("incidents.create"):
        raise HTTPException(403, "Not allowed")
    from app.schemas.operations import IncidentIn

    data = IncidentIn.model_validate(p).model_dump()
    data["occurred_at"] = data.get("occurred_at") or ts
    inc = ops.create_incident(db, actor, data)
    return {"id": inc.id, "number": inc.number}


def sos_create(db, actor, p, ts):
    if not actor.can("sos.raise"):
        raise HTTPException(403, "Not allowed")
    sos = ops.raise_sos(db, actor, p)
    return {"id": sos.id, "incident_id": sos.incident_id}


def complaint_create(db, actor, p, ts):
    if not actor.can("complaints.create"):
        raise HTTPException(403, "Not allowed")
    from app.schemas.maintenance import ComplaintIn

    data = ComplaintIn.model_validate(p).model_dump()
    c = Complaint(tenant_id=actor.tenant_id, number=next_number(db, actor.tenant_id, "CMP"), raised_by=actor.id, **data)
    db.add(c)
    db.flush()
    audit.record(db, actor, "complaint.created", "complaint", c.id, new={"title": c.title, "via": "offline_sync"})
    return {"id": c.id, "number": c.number}


def ticket_create(db, actor, p, ts):
    if not actor.can("tickets.create"):
        raise HTTPException(403, "Not allowed")
    from app.schemas.tickets import TicketIn
    from app.services import tickets as tickets_svc

    data = TicketIn.model_validate(p).model_dump()
    data["source"] = "offline"
    t = tickets_svc.create(db, actor, data)
    return {"id": t.id, "number": t.number}


def ticket_comment(db, actor, p, ts):
    from app.services import tickets as tickets_svc
    from app.services.access import get_ticket

    t = get_ticket(db, actor, _uuid(p.get("ticket_id")))
    c = tickets_svc.add_comment(db, actor, t, str(p.get("message") or "")[:4000] or "-", p.get("visibility") or "customer")
    return {"id": c.id}


def _task(db, actor, p):
    if not actor.can("maintenance.work"):
        raise HTTPException(403, "Not allowed")
    return get_task(db, actor, _uuid(p.get("task_id")))


def m_accept(db, actor, p, ts):
    t = _task(db, actor, p)
    msvc.accept(db, actor, t)
    return {"id": t.id, "status": t.status}


def m_start(db, actor, p, ts):
    t = _task(db, actor, p)
    msvc.start(db, actor, t, p.get("latitude"), p.get("longitude"), p.get("accuracy_m"))
    if ts and t.started_at and t.started_at > ts:
        t.started_at = ts
    return {"id": t.id, "status": t.status}


def m_scan(db, actor, p, ts):
    t = _task(db, actor, p)
    msvc.record_asset_scan(db, actor, t, p["code"], p.get("method", "qr"))
    return {"id": t.id}


def m_checklist(db, actor, p, ts):
    t = _task(db, actor, p)
    item = next((i for i in t.checklist if str(i.id) == str(p.get("item_id"))), None)
    if not item:
        raise HTTPException(404, "Checklist item not found")
    msvc.update_checklist_item(db, actor, t, item, p["status"], p.get("reason"))
    return {"id": t.id, "item_id": item.id, "status": item.status}


def m_notes(db, actor, p, ts):
    t = _task(db, actor, p)
    msvc.ensure_editable(actor, t)
    changed = {}
    for k in ("work_notes", "issue_found", "outcome", "observations"):
        if k in p:
            changed[k] = p[k]
            setattr(t, k, p[k])
    audit.record(db, actor, "maintenance.updated", "maintenance_task", t.id, new={**changed, "via": "offline_sync"})
    return {"id": t.id}


def m_material(db, actor, p, ts):
    t = _task(db, actor, p)
    msvc.ensure_editable(actor, t)
    from app.schemas.maintenance import MaterialIn

    data = MaterialIn.model_validate(p).model_dump()
    m = MaintenanceMaterial(tenant_id=t.tenant_id, task_id=t.id, added_by=actor.id, **data)
    db.add(m)
    db.flush()
    audit.record(db, actor, "maintenance.material_added", "maintenance_task", t.id, new={**data, "via": "offline_sync"})
    return {"id": m.id}


def m_exception(db, actor, p, ts):
    t = _task(db, actor, p)
    x = msvc.add_exception(db, actor, t, p["requirement"], p["reason_code"], p["reason"])
    return {"id": x.id}


def m_complete(db, actor, p, ts):
    t = _task(db, actor, p)
    if p.get("work_notes"):
        msvc.ensure_editable(actor, t)
        t.work_notes = p["work_notes"]
    msvc.complete(db, actor, t, p.get("latitude"), p.get("longitude"), p.get("accuracy_m"))
    return {"id": t.id, "status": t.status}


def attendance(db, actor, p, ts, direction):
    if not actor.can("attendance.self"):
        raise HTTPException(403, "Not allowed")
    at = ts or utcnow()
    row = db.scalar(select(Attendance).where(Attendance.user_id == actor.id, Attendance.work_date == at.date()))
    if direction == "in":
        row = row or Attendance(tenant_id=actor.tenant_id, user_id=actor.id, work_date=at.date())
        row.check_in_at = row.check_in_at or at
        row.latitude, row.longitude, row.method = p.get("latitude"), p.get("longitude"), "offline"
        db.add(row)
    else:
        if not row:
            raise HTTPException(409, "No check-in for that day")
        row.check_out_at = at
    db.flush()
    return {"id": row.id}


HANDLERS: dict[tuple[str, str], Callable] = {
    ("visitor", "create"): visitor_create,
    ("visitor", "entry"): visitor_entry,
    ("visitor", "exit"): visitor_exit,
    ("vehicle_log", "create"): vehicle_log,
    ("patrol", "start"): patrol_start,
    ("patrol", "scan"): patrol_scan,
    ("patrol", "finish"): patrol_finish,
    ("incident", "create"): incident_create,
    ("sos", "create"): sos_create,
    ("complaint", "create"): complaint_create,
    ("ticket", "create"): ticket_create,
    ("ticket", "comment"): ticket_comment,
    ("maintenance", "accept"): m_accept,
    ("maintenance", "start"): m_start,
    ("maintenance", "scan"): m_scan,
    ("maintenance", "checklist"): m_checklist,
    ("maintenance", "notes"): m_notes,
    ("maintenance", "material"): m_material,
    ("maintenance", "exception"): m_exception,
    ("maintenance", "complete"): m_complete,
    ("attendance", "check_in"): lambda db, a, p, ts: attendance(db, a, p, ts, "in"),
    ("attendance", "check_out"): lambda db, a, p, ts: attendance(db, a, p, ts, "out"),
}


def process(db: Session, actor: Actor, ops_in, device_id: str | None) -> list[dict]:
    results = []
    for op in ops_in:
        existing = db.scalar(select(SyncOperation).where(SyncOperation.user_id == actor.id, SyncOperation.client_op_id == op.client_op_id))
        if existing and existing.status in (SyncState.SYNCED, SyncState.FAILED, SyncState.CONFLICT):
            results.append({"client_op_id": op.client_op_id, "status": existing.status, "result": existing.result, "error": existing.error})
            continue
        handler = HANDLERS.get((op.entity, op.operation))
        record = existing or SyncOperation(
            tenant_id=actor.tenant_id,
            user_id=actor.id,
            client_op_id=op.client_op_id,
            entity=op.entity,
            operation=op.operation,
            payload=audit.jsonable(op.payload),
            client_timestamp=op.client_timestamp,
            status=SyncState.SYNCING,
            device_id=device_id,
        )
        if not existing:
            db.add(record)
            db.flush()
        if handler is None:
            record.status, record.error = SyncState.FAILED, f"Unsupported operation {op.entity}.{op.operation}"
        else:
            sp = db.begin_nested()
            try:
                result = handler(db, actor, dict(op.payload), _dt(op.client_timestamp))
                db.flush()
                sp.commit()
                record.status, record.result, record.error = SyncState.SYNCED, audit.jsonable(result), None
            except HTTPException as e:
                sp.rollback()
                detail = (
                    e.detail if isinstance(e.detail, str) else (e.detail.get("message") if isinstance(e.detail, dict) else str(e.detail))
                )
                if e.status_code == 409 and "has not synced yet" in str(detail):
                    record.status = SyncState.RETRY
                elif e.status_code == 409:
                    record.status = SyncState.CONFLICT
                else:
                    record.status = SyncState.FAILED
                record.error = detail
                if isinstance(e.detail, dict):
                    record.result = audit.jsonable(e.detail)
            except (ValidationError, KeyError, ValueError) as e:
                sp.rollback()
                record.status, record.error = SyncState.FAILED, f"Invalid payload: {e}"[:500]
            except Exception as e:  # noqa: BLE001 - unexpected errors are retried by the client
                sp.rollback()
                record.status, record.error = SyncState.RETRY, f"Server error: {type(e).__name__}"
        results.append({"client_op_id": op.client_op_id, "status": record.status, "result": record.result, "error": record.error})
    db.commit()
    return results
