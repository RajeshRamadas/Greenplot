"""Offline queue replay (requirements §30, §41 offline sync)."""

import uuid


def op(entity, operation, payload, op_id=None):
    return {
        "client_op_id": op_id or f"op-{uuid.uuid4().hex[:12]}",
        "entity": entity,
        "operation": operation,
        "payload": payload,
        "client_timestamp": "2026-10-05T03:00:00Z",
    }


def test_guard_offline_batch_is_idempotent(as_, world):
    admin, guard = as_(world.admin), as_(world.guard)
    route = admin.ok(
        "post",
        "/patrol/routes",
        {"name": "Perimeter", "checkpoints": [{"name": "Gate", "qr_code": "CP-1"}, {"name": "Park", "qr_code": "CP-2"}]},
    )
    start = op("patrol", "start", {"route_id": route["id"]}, "run-op-0001")
    batch = [
        op("visitor", "create", {"name": "Milkman", "purpose": "Delivery"}, "visitor-op-001"),
        op("vehicle_log", "create", {"vehicle_number": "KA01XY0001", "direction": "in"}),
        start,
        op("patrol", "scan", {"run_op_id": "run-op-0001", "code": "CP-1"}),
        op("patrol", "scan", {"run_op_id": "run-op-0001", "code": "CP-2"}),
        op("patrol", "finish", {"run_op_id": "run-op-0001"}),
        op("incident", "create", {"title": "Broken streetlight near park", "category": "infrastructure"}),
        op("visitor", "exit", {"visitor_op_id": "visitor-op-001"}),
        op("unknown", "thing", {}),
        op("maintenance", "start", {"task_id": str(uuid.uuid4())}),
    ]
    res = guard.ok("post", "/sync", {"device_id": "guard-phone-1", "operations": batch})["results"]
    status = [r["status"] for r in res]
    assert status[:8] == ["synced"] * 8, res
    assert status[8] == "failed" and status[9] == "failed"
    assert res[2]["result"]["id"] == res[3]["result"]["run_id"]
    run = guard.ok("get", f"/patrol/runs/{res[2]['result']['id']}")
    assert run["status"] == "completed" and len(run["scans"]) == 2
    # Replaying the same batch changes nothing
    again = guard.ok("post", "/sync", {"operations": batch})["results"]
    assert [r["result"] for r in again[:8]] == [r["result"] for r in res[:8]]
    assert admin.ok("get", "/visitors")["total"] == 1
    assert admin.ok("get", "/incidents")["total"] == 1


def test_staff_offline_maintenance_and_conflicts(as_, world):
    from tests.conftest import jpeg_bytes

    sup, staff = as_(world.supervisor), as_(world.staff)
    t = sup.ok(
        "post",
        "/maintenance",
        {
            "title": "Weeding plot 117",
            "category": "cleaning",
            "property_id": str(world.p117.id),
            "assigned_staff_id": str(world.staff.id),
            "checklist_items": ["Weeds removed", "Waste bagged"],
        },
    )
    items = t["checklist"]
    res = staff.ok(
        "post",
        "/sync",
        {
            "operations": [
                op("attendance", "check_in", {"latitude": 12.9, "longitude": 77.6}),
                op("maintenance", "start", {"task_id": t["id"], "latitude": 12.97, "longitude": 77.59}),
                op("maintenance", "checklist", {"task_id": t["id"], "item_id": items[0]["id"], "status": "completed"}),
                op("maintenance", "checklist", {"task_id": t["id"], "item_id": items[1]["id"], "status": "skipped"}),
                op(
                    "maintenance",
                    "checklist",
                    {"task_id": t["id"], "item_id": items[1]["id"], "status": "skipped", "reason": "No bags available"},
                ),
                op("maintenance", "notes", {"task_id": t["id"], "work_notes": "Weeded whole plot"}),
                op("maintenance", "material", {"task_id": t["id"], "name": "Gloves", "quantity": 1, "unit": "pair"}),
            ]
        },
    )["results"]
    assert [r["status"] for r in res] == ["synced", "synced", "synced", "failed", "synced", "synced", "synced"], res
    # evidence uploaded when back online with a client_ref (idempotent)
    m1 = staff.upload("maintenance_task", t["id"], jpeg_bytes(), "image/jpeg", "after_photo", client_ref="photo-abc").json()
    m2 = staff.upload("maintenance_task", t["id"], jpeg_bytes(), "image/jpeg", "after_photo", client_ref="photo-abc").json()
    assert m1["id"] == m2["id"]
    done = staff.ok("post", "/sync", {"operations": [op("maintenance", "complete", {"task_id": t["id"]}, "complete-op-1")]})["results"][0]
    assert done["status"] == "synced" and done["result"]["status"] == "completed"
    # a second device acting on stale state gets a conflict, not a silent overwrite
    stale = staff.ok("post", "/sync", {"operations": [op("maintenance", "start", {"task_id": t["id"]})]})["results"][0]
    assert stale["status"] == "conflict" and stale["result"]["current_status"] == "completed"
    detail = sup.ok("get", f"/maintenance/{t['id']}")
    assert len(detail["evidence"]) == 1 and detail["checklist"][1]["reason"] == "No bags available"
