"""End-to-end Proof of Work flow (requirements §31, §42, §49)."""

import uuid

from app.models import Asset
from tests.conftest import PDF_BYTES, jpeg_bytes


def make_gate_asset(world):
    a = Asset(
        tenant_id=world.ta.id,
        code="GATE-MAIN",
        qr_code="GP-AST-GATE01",
        name="Main Entrance Gate",
        category="gate",
        property_id=world.p117.id,
        service_interval_days=90,
    )
    world.db.add(a)
    world.db.commit()
    return a


def test_end_to_end_complaint_to_searchable_history(as_, world):
    asset = make_gate_asset(world)
    resident, admin, sup, staff = as_(world.resident), as_(world.admin), as_(world.supervisor), as_(world.staff)

    # Resident reports: "Gate is difficult to close."
    c = resident.ok("post", "/complaints", {"category": "gate", "title": "Gate is difficult to close", "property_id": str(world.p117.id)})
    assert c["number"].startswith("GP-CMP-") and c["status"] == "open"

    # Supervisor assigns → maintenance created and linked
    c = sup.ok("post", f"/complaints/{c['id']}/assign", {"assigned_staff_id": str(world.staff.id)})
    assert c["status"] == "assigned" and c["task_number"].startswith("GP-MNT-")
    task_id = c["maintenance_task_id"]
    sup.ok("patch", f"/maintenance/{task_id}", {"title": "Gate hinge lubrication and alignment"})
    admin.ok(
        "post", f"/maintenance/{task_id}/assign", {"assigned_staff_id": str(world.staff.id), "supervisor_id": str(world.supervisor.id)}
    )
    t = staff.ok("get", f"/maintenance/{task_id}")
    assert t["status"] == "assigned" and t["category"] == "gate_fence"
    assert "accept" in t["allowed_actions"]

    # Link the asset to the task (asset-driven work)
    world.db.expire_all()
    from app.models import MaintenanceTask

    mt = world.db.get(MaintenanceTask, uuid.UUID(task_id))
    mt.asset_id = asset.id
    world.db.commit()

    # Worker accepts, scans the gate QR, captures the before photo, starts work
    staff.ok("post", f"/maintenance/{task_id}/accept")
    bad = staff.post(f"/maintenance/{task_id}/scan", {"code": "WRONG", "method": "qr"})
    assert bad.status_code == 422
    staff.ok("post", f"/maintenance/{task_id}/scan", {"code": "GP-AST-GATE01", "method": "qr"})
    before = staff.upload(
        "maintenance_task",
        task_id,
        jpeg_bytes((120, 100, 90)),
        "image/jpeg",
        "before_photo",
        latitude=12.9716,
        longitude=77.5946,
        captured_at="2026-09-26T04:10:00Z",
    )
    assert before.status_code == 200, before.text
    assert before.json()["status"] == "ready" and len(before.json()["sha256"]) == 64
    t = staff.ok("post", f"/maintenance/{task_id}/start", {"latitude": 12.9716, "longitude": 77.5946, "accuracy_m": 8})
    assert t["status"] == "started"
    assert t["complaint_id"] == c["id"]
    assert resident.ok("get", f"/complaints/{c['id']}")["status"] == "in_progress"

    # Submitting now must fail: checklist pending, no after photo, no notes
    r = staff.post(f"/maintenance/{task_id}/complete", {})
    assert r.status_code == 422
    missing = r.json()["detail"]["missing"]
    assert {"after_photo", "checklist", "work_notes"} <= set(missing)

    # Checklist, after photo, notes, materials, invoice
    for item in t["checklist"]:
        staff.ok("patch", f"/maintenance/{task_id}/checklist/{item['id']}", {"status": "completed"})
    staff.upload("maintenance_task", task_id, jpeg_bytes((60, 160, 90)), "image/jpeg", "after_photo")
    staff.ok("post", f"/maintenance/{task_id}/materials", {"name": "Grease", "quantity": 0.5, "unit": "kg", "unit_cost": 240})
    inv = staff.upload("maintenance_task", task_id, PDF_BYTES, "application/pdf", "invoice", filename="invoice.pdf")
    assert inv.status_code == 200, inv.text
    staff.ok(
        "patch",
        f"/maintenance/{task_id}",
        {"work_notes": "Hinges cleaned, greased and realigned; gate closes smoothly.", "issue_found": "Dry hinges, sagging leaf"},
    )
    t = staff.ok(
        "post", f"/maintenance/{task_id}/complete", {"latitude": 12.9717, "longitude": 77.5947, "outcome": "Gate operates normally"}
    )
    assert t["status"] == "completed" and t["completed_by"] == str(world.staff.id)
    assert t["proof"]["missing"] == []

    # Worker cannot approve own job; supervisor approves → auto-closed
    assert staff.post(f"/maintenance/{task_id}/approve", {}).status_code == 403
    t = sup.ok("post", f"/maintenance/{task_id}/approve", {"comment": "Verified on site"})
    assert t["status"] == "closed" and t["review_decision"] == "approved" and t["approved_at"]
    assert t["reviewed_by_name"] == "Anita Supervisor"
    assert t["materials_cost"] == 120.0

    # Complaint resolved automatically, resident can see the evidence now and acknowledge
    cr = resident.ok("get", f"/complaints/{c['id']}")
    assert cr["status"] == "resolved"
    rt = resident.ok("get", f"/maintenance/{task_id}")
    types = {e["evidence_type"] for e in rt["evidence"]}
    assert {"before_photo", "after_photo", "invoice"} <= types
    assert all(e["url"] for e in rt["evidence"])
    resident.ok("post", f"/maintenance/{task_id}/acknowledge", {"note": "Thanks!"})

    # Evidence is preserved after approval
    ev_media = rt["evidence"][0]["media_id"]
    assert staff.delete(f"/media/{ev_media}", {"reason": "oops"}).status_code in (403, 409)
    assert sup.delete(f"/media/{ev_media}", {"reason": "oops"}).status_code == 409

    # Audit trail (§9) contains the full lifecycle
    actions = [a["action"] for a in sup.ok("get", f"/maintenance/{task_id}/audit")]
    for a in [
        "maintenance.created",
        "maintenance.assign",
        "maintenance.accept",
        "maintenance.asset_scan_mismatch",
        "maintenance.asset_scanned",
        "maintenance.start",
        "maintenance.evidence_uploaded",
        "maintenance.checklist_changed",
        "maintenance.complete",
        "maintenance.approve",
        "maintenance.close",
        "maintenance.resident_acknowledged",
    ]:
        assert a in actions, a

    # Downloadable proof report
    pdf = sup.get(f"/maintenance/{task_id}/report.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert resident.get(f"/maintenance/{task_id}/report.pdf").status_code == 200

    # Searchable history
    res = admin.ok("get", "/records/search", params={"q": "Show all gate repairs for Plot 117 in the last 12 months"})
    assert res["interpreted"]["plot"] == "117" and res["interpreted"]["category"] == "gate_fence"
    assert [h["number"] for h in res["items"]] == [t["number"]]
    hist = resident.ok("get", f"/properties/{world.p117.id}/history")
    assert any(h["number"] == t["number"] for h in hist)

    # Asset next service date rolled forward
    world.db.expire_all()
    assert world.db.get(Asset, asset.id).next_service_due is not None

    # Notifications went to the right people
    assert any("approved" in n["title"] for n in staff.ok("get", "/notifications")["items"])
    assert any("submitted for review" in n["title"] for n in sup.ok("get", "/notifications")["items"])


def test_rework_requires_fresh_after_photo(as_, world):
    sup, staff = as_(world.supervisor), as_(world.staff)
    t = sup.ok(
        "post",
        "/maintenance",
        {
            "title": "Clean plot 204",
            "category": "cleaning",
            "property_id": str(world.p204.id),
            "assigned_staff_id": str(world.staff.id),
            "checklist_items": ["Weeds cleared"],
        },
    )
    tid = t["id"]
    t = staff.ok("post", f"/maintenance/{tid}/start", {})
    assert t["accepted_at"], "starting from ASSIGNED records acceptance"
    staff.ok("patch", f"/maintenance/{tid}/checklist/{t['checklist'][0]['id']}", {"status": "completed"})
    staff.upload("maintenance_task", tid, jpeg_bytes(), "image/jpeg", "after_photo")
    staff.ok("patch", f"/maintenance/{tid}", {"work_notes": "Cleared"})
    staff.ok("post", f"/maintenance/{tid}/complete", {})

    assert sup.post(f"/maintenance/{tid}/reject", {"comment": ""}).status_code == 422
    t = sup.ok("post", f"/maintenance/{tid}/reject", {"comment": "Corner near the gate still has debris"})
    assert t["status"] == "rework_required" and t["rework_count"] == 1
    assert any("Rework required" in n["title"] for n in staff.ok("get", "/notifications")["items"])

    t = staff.ok("post", f"/maintenance/{tid}/start", {})
    assert t["status"] == "started"
    r = staff.post(f"/maintenance/{tid}/complete", {})
    assert r.status_code == 422 and r.json()["detail"]["missing"] == ["after_photo"]
    staff.upload("maintenance_task", tid, jpeg_bytes((10, 200, 10)), "image/jpeg", "after_photo")
    t = staff.ok("post", f"/maintenance/{tid}/complete", {})
    assert t["status"] == "completed"
    rounds = sorted(e["rework_round"] for e in t["evidence"] if e["evidence_type"] == "after_photo")
    assert rounds == [0, 1], "both rounds of evidence preserved"
    t = sup.ok("post", f"/maintenance/{tid}/approve", {})
    assert t["status"] == "closed"

    # Reopen requires a reason and goes back to rework
    assert sup.post(f"/maintenance/{tid}/reopen", {"reason": ""}).status_code == 422
    t = sup.ok("post", f"/maintenance/{tid}/reopen", {"reason": "Resident reported debris again"})
    assert t["status"] == "rework_required" and t["rework_count"] == 2


def test_vendor_job_flow(as_, world):
    sup, vendor = as_(world.supervisor), as_(world.vendor_user)
    t = sup.ok(
        "post",
        "/maintenance",
        {"title": "Repair gate motor", "category": "gate_fence", "property_id": str(world.p117.id), "vendor_id": str(world.vendor.id)},
    )
    assert t["status"] == "assigned" and t["vendor_name"] == "FixIt Gates"
    mine = vendor.ok("get", "/tasks/mine")
    assert [x["id"] for x in mine["maintenance"]] == [t["id"]]
    vendor.ok("post", f"/maintenance/{t['id']}/accept")
    r = vendor.upload("maintenance_task", t["id"], PDF_BYTES, "application/pdf", "service_report")
    assert r.status_code == 200
    assert vendor.get(f"/maintenance/{t['id']}/audit").status_code == 200
    # vendor cannot see other tasks
    other = sup.ok("post", "/maintenance", {"title": "Paint", "category": "painting", "assigned_staff_id": str(world.staff.id)})
    assert vendor.get(f"/maintenance/{other['id']}").status_code == 404


def test_decline_returns_task_to_pool(as_, world):
    sup, staff = as_(world.supervisor), as_(world.staff)
    t = sup.ok(
        "post", "/maintenance", {"title": "Drain cleaning", "category": "compound_maintenance", "assigned_staff_id": str(world.staff.id)}
    )
    staff.ok("post", f"/maintenance/{t['id']}/decline", {"reason": "On leave today"})
    t = sup.ok("get", f"/maintenance/{t['id']}")
    assert t["status"] == "created" and t["assigned_staff_id"] is None
    assert staff.get(f"/maintenance/{t['id']}").status_code == 404
