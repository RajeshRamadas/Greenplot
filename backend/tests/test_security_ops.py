"""Visitors, vehicles, patrols, incidents and SOS (requirements §18)."""

from datetime import timedelta

from app.models import SosAlert
from app.services.jobs import escalate_sos


def test_visitor_needs_resident_approval(as_, world):
    guard, resident, other = as_(world.guard), as_(world.resident), as_(world.resident2)
    v = guard.ok(
        "post",
        "/visitors",
        {
            "name": "Courier Ravi",
            "phone": "9990001111",
            "purpose": "Delivery",
            "property_id": str(world.p117.id),
            "vehicle_number": "ka 01 ab 1234",
        },
    )
    assert v["status"] == "pending_approval" and v["vehicle_number"] == "KA01AB1234"
    assert any("Visitor at the gate" in n["title"] for n in resident.ok("get", "/notifications")["items"])
    assert guard.post(f"/visitors/{v['id']}/entry").status_code == 409
    assert other.post(f"/visitors/{v['id']}/decision", {"approve": True}).status_code == 404
    v = resident.ok("post", f"/visitors/{v['id']}/decision", {"approve": True})
    assert v["status"] == "approved"
    v = guard.ok("post", f"/visitors/{v['id']}/entry")
    assert v["status"] == "inside" and v["entry_at"]
    v = guard.ok("post", f"/visitors/{v['id']}/exit")
    assert v["status"] == "exited"
    logs = as_(world.admin).ok("get", "/vehicles/log", params={"number": "KA01AB1234"})["items"]
    assert [entry["direction"] for entry in logs] == ["out"]
    # residents only see their own visitors
    assert [x["id"] for x in resident.ok("get", "/visitors")["items"]] == [v["id"]]
    assert other.ok("get", "/visitors")["total"] == 0


def test_preapproved_visitor_walks_in(as_, world):
    guard, resident = as_(world.guard), as_(world.resident)
    pre = resident.ok(
        "post", "/visitors", {"name": "Plumber Joseph", "phone": "9876500000", "purpose": "Kitchen tap", "property_id": str(world.p117.id)}
    )
    assert pre["status"] == "approved" and pre["pre_approved"]
    assert resident.post("/visitors", {"name": "X Y", "purpose": "Visit", "property_id": str(world.p204.id)}).status_code == 403
    v = guard.ok(
        "post", "/visitors", {"name": "Joseph", "phone": "9876500000", "purpose": "Kitchen tap", "property_id": str(world.p117.id)}
    )
    assert v["id"] == pre["id"] and v["status"] == "inside"


def test_vehicles(as_, world):
    resident, guard = as_(world.resident), as_(world.guard)
    v = resident.ok("post", "/vehicles", {"number": "KA-05-MN-7777", "property_id": str(world.p117.id), "vehicle_type": "car"})
    assert v["number"] == "KA05MN7777"
    assert resident.post("/vehicles", {"number": "KA05MN7777", "property_id": str(world.p117.id)}).status_code == 409
    log = guard.ok("post", "/vehicles/log", {"vehicle_number": "ka05mn7777", "direction": "in"})
    assert log["vehicle_id"] == v["id"] and not log["is_visitor"]
    log = guard.ok("post", "/vehicles/log", {"vehicle_number": "TN01ZZ0001", "direction": "in"})
    assert log["is_visitor"]
    assert resident.get("/vehicles/log").status_code == 403


def test_patrol_route_and_run(as_, world):
    admin, guard = as_(world.admin), as_(world.guard)
    route = admin.ok(
        "post",
        "/patrol/routes",
        {"name": "Night perimeter", "checkpoints": [{"name": "Main gate", "qr_code": "CP-GATE"}, {"name": "Park"}, {"name": "Pump house"}]},
    )
    assert len(route["checkpoints"]) == 3 and all(c["qr_code"] for c in route["checkpoints"])
    assert admin.get(f"/patrol/checkpoints/{route['checkpoints'][0]['id']}/qr.svg").headers["content-type"].startswith("image/svg")
    run = guard.ok("post", f"/patrol/routes/{route['id']}/start")
    run = guard.ok("post", f"/patrol/runs/{run['id']}/scan", {"code": "CP-GATE", "latitude": 12.9, "longitude": 77.6})
    assert guard.post(f"/patrol/runs/{run['id']}/scan", {"code": "NOT-HERE"}).status_code == 422
    run = guard.ok(
        "post", f"/patrol/runs/{run['id']}/scan", {"code": route["checkpoints"][1]["qr_code"], "exception": "Park light not working"}
    )
    assert any("Patrol exception" in n["title"] for n in as_(world.supervisor).ok("get", "/notifications")["items"])
    run = guard.ok("post", f"/patrol/runs/{run['id']}/finish", {"notes": "Skipped pump house (locked)"})
    assert run["status"] == "incomplete" and len(run["scans"]) == 2 and run["checkpoints_total"] == 3


def test_incident_lifecycle(as_, world):
    guard, sup, resident = as_(world.guard), as_(world.supervisor), as_(world.resident)
    inc = resident.ok(
        "post", "/incidents", {"title": "Stranger loitering near plot 117", "category": "trespass", "property_id": str(world.p117.id)}
    )
    assert inc["number"].startswith("GP-INC-") and inc["status"] == "open"
    assert any(inc["number"] in n["title"] for n in guard.ok("get", "/notifications")["items"])
    assert resident.post(f"/incidents/{inc['id']}/status", {"status": "acknowledged"}).status_code == 403
    guard.ok("post", f"/incidents/{inc['id']}/status", {"status": "acknowledged", "note": "On my way"})
    guard.ok("post", f"/incidents/{inc['id']}/status", {"status": "investigating"})
    assert sup.post(f"/incidents/{inc['id']}/status", {"status": "resolved"}).status_code == 422
    sup.ok("post", f"/incidents/{inc['id']}/status", {"status": "resolved", "note": "Person was a delivery agent, escorted out"})
    full = sup.ok("post", f"/incidents/{inc['id']}/status", {"status": "closed", "note": "Closed"})
    assert full["status"] == "closed" and len(full["updates"]) == 4
    assert sup.post(f"/incidents/{inc['id']}/status", {"status": "investigating"}).status_code == 409
    # incident media gets legal-hold retention
    from tests.conftest import jpeg_bytes

    m = guard.upload("incident", inc["id"], jpeg_bytes(), "image/jpeg").json()
    assert m["legal_hold"] is True


def test_sos_raise_ack_escalate(as_, world, db):
    resident, guard = as_(world.resident), as_(world.guard)
    sos = resident.ok("post", "/sos", {"latitude": 12.97, "longitude": 77.59, "message": "Help, intruder!"})
    assert sos["status"] == "active" and sos["incident_id"] and sos["property_id"] == str(world.p117.id)
    notes = guard.ok("get", "/notifications")["items"]
    assert any(n["kind"] == "sos" for n in notes)
    sms = [n for n in notes if n["kind"] == "sos"][0]["channels"]
    assert "sms" in sms and "whatsapp" in sms
    # escalation after timeout when nobody responds
    row = db.get(SosAlert, __import__("uuid").UUID(sos["id"]))
    row.created_at = row.created_at - timedelta(minutes=10)
    db.commit()
    assert escalate_sos(db) == 1
    db.commit()
    assert any("ESCALATED" in n["title"] for n in as_(world.admin).ok("get", "/notifications")["items"])
    assert resident.post(f"/sos/{sos['id']}/action", {"action": "acknowledge"}).status_code == 403
    guard.ok("post", f"/sos/{sos['id']}/action", {"action": "acknowledge"})
    assert any("Help is on the way" in n["title"] for n in resident.ok("get", "/notifications")["items"])
    s = guard.ok("post", f"/sos/{sos['id']}/action", {"action": "resolve", "note": "Area checked, all clear"})
    assert s["status"] == "resolved"
    inc = guard.ok("get", f"/incidents/{sos['incident_id']}")
    assert inc["status"] == "resolved"
    assert guard.ok("get", "/sos") == []
