"""Property Watch, complaints, assets, schedules, notices, reports and jobs."""

from datetime import date, timedelta

from app.models import Media
from app.services import jobs
from tests.conftest import jpeg_bytes


def test_property_watch_inspection_to_follow_up(as_, world):
    resident, sup, staff = as_(world.resident), as_(world.supervisor), as_(world.staff)
    req = resident.ok("post", "/inspections", {"property_id": str(world.p117.id)})
    assert req["is_property_watch"] and req["inspector_id"] is None and len(req["items"]) == 10
    i = sup.ok("post", f"/inspections/{req['id']}/assign?inspector_id={world.staff.id}")
    assert i["inspector_id"] == str(world.staff.id)
    assert staff.ok("get", "/tasks/mine")["inspections"][0]["id"] == i["id"]
    staff.ok("post", f"/inspections/{i['id']}/start")
    for item in i["items"]:
        cond = "attention" if item["point"] == "streetlights" else "good"
        body = {"condition": cond, **({"notes": "Lamp flickering"} if cond == "attention" else {})}
        assert staff.patch(f"/inspections/{i['id']}/items/{item['id']}", {"condition": "issue"}).status_code == 422
        staff.ok("patch", f"/inspections/{i['id']}/items/{item['id']}", body)
    assert staff.post(f"/inspections/{i['id']}/complete", {"overall_condition": "attention"}).status_code == 422, "photo required"
    staff.upload("inspection", i["id"], jpeg_bytes(), "image/jpeg")
    done = staff.ok("post", f"/inspections/{i['id']}/complete", {"overall_condition": "attention", "findings": "Streetlight needs repair"})
    assert done["status"] == "completed"
    assert any("Property Watch report ready" in n["title"] for n in resident.ok("get", "/notifications")["items"])
    report = resident.ok("get", f"/inspections/{i['id']}")
    assert len(report["media"]) == 1 and report["media"][0]["url"]
    light = next(x for x in done["items"] if x["point"] == "streetlights")
    task = sup.ok("post", f"/inspections/{i['id']}/follow-up", {"item_id": light["id"], "assigned_staff_id": str(world.staff.id)})
    assert task["category"] == "electrical" and task["inspection_id"] == i["id"] and task["source"] == "inspection"
    assert sup.post(f"/inspections/{i['id']}/follow-up", {"item_id": light["id"]}).status_code == 409
    assert resident.ok("get", f"/properties/{world.p117.id}")["condition"] == "attention"


def test_complaint_comments_and_status_rules(as_, world):
    resident, sup = as_(world.resident), as_(world.supervisor)
    c = resident.ok("post", "/complaints", {"category": "water", "title": "Low water pressure"})
    assert c["property_id"] == str(world.p117.id), "single-property residents default to their plot"
    sup.ok("post", f"/complaints/{c['id']}/comments", {"body": "Check pump schedule", "internal": True})
    sup.ok("post", f"/complaints/{c['id']}/comments", {"body": "We'll look into it today"})
    seen = resident.ok("get", f"/complaints/{c['id']}")["comments"]
    assert [x["body"] for x in seen] == ["We'll look into it today"]
    assert resident.post(f"/complaints/{c['id']}/status", {"status": "resolved"}).status_code == 403
    assert sup.post(f"/complaints/{c['id']}/status", {"status": "resolved"}).status_code == 422
    sup.ok("post", f"/complaints/{c['id']}/status", {"status": "resolved", "resolution": "Pump timer reset"})
    c = resident.ok("post", f"/complaints/{c['id']}/status", {"status": "closed"})
    assert c["status"] == "closed" and c["closed_at"]


def test_assets_qr_scan_lookup(as_, world):
    admin, staff = as_(world.admin), as_(world.staff)
    a = admin.ok("post", "/assets", {"code": "PUMP-1", "name": "Borewell pump", "category": "pump", "service_interval_days": 30})
    assert a["qr_code"].startswith("GP-AST-")
    svg = admin.get(f"/assets/{a['id']}/qr.svg")
    assert svg.status_code == 200 and b"<svg" in svg.content and b"PUMP-1" in svg.content
    found = staff.ok("get", f"/maintenance/scan/{a['qr_code']}")
    assert found["asset"]["id"] == a["id"] and found["open_tasks"] == []
    assert staff.get("/maintenance/scan/NOPE").status_code == 404
    assert as_(world.resident).get("/assets").status_code == 403


def test_recurring_schedule_generates_tasks(as_, world, db):
    sup = as_(world.supervisor)
    today = date.today()
    s = sup.ok(
        "post",
        "/maintenance/schedules",
        {
            "title": "Weekly common-area sweep",
            "category": "cleaning",
            "interval_days": 7,
            "next_run_on": str(today - timedelta(days=14)),
            "assigned_staff_id": str(world.staff.id),
        },
    )
    out = sup.ok("post", "/maintenance/schedules/run")
    assert len(out["created"]) == 3, "catches up on missed runs"
    s = next(x for x in sup.ok("get", "/maintenance/schedules") if x["id"] == s["id"])
    assert s["next_run_on"] == str(today + timedelta(days=7))
    tasks = as_(world.staff).ok("get", "/tasks/mine")["maintenance"]
    assert len(tasks) == 3 and all(t["source"] == "schedule" for t in tasks)
    assert sup.ok("post", "/maintenance/schedules/run")["created"] == []
    garden = sup.ok("post", "/maintenance", {"title": "Hedge trimming", "category": "gardening"})
    assert [t["id"] for t in sup.ok("get", "/gardening")["items"]] == [garden["id"]]


def test_overdue_reminders_and_retention(as_, world, db):
    sup = as_(world.supervisor)
    t = sup.ok(
        "post",
        "/maintenance",
        {"title": "Fix leak", "category": "plumbing", "assigned_staff_id": str(world.staff.id), "due_at": "2020-01-01T00:00:00Z"},
    )
    assert sup.ok("get", "/maintenance", params={"overdue": True})["items"][0]["id"] == t["id"]
    assert jobs.remind_due_and_overdue(db) == 1
    db.commit()
    assert jobs.remind_due_and_overdue(db) == 0, "notified once"
    assert any("Overdue" in n["title"] for n in as_(world.staff).ok("get", "/notifications")["items"])
    staff = as_(world.staff)
    staff.ok("post", f"/maintenance/{t['id']}/accept")
    m = staff.upload("maintenance_task", t["id"], jpeg_bytes(), "image/jpeg", "before_photo").json()
    row = db.get(Media, __import__("uuid").UUID(m["id"]))
    assert row.retention_until == date.today() + timedelta(days=90)
    assert jobs.purge_expired_media(db, today=date.today() + timedelta(days=91)) == 1
    db.commit()
    db.refresh(row)
    assert row.status == "deleted" and row.sha256 == m["sha256"], "hash and metadata survive purge"


def test_notices_reach_audience(as_, world):
    admin = as_(world.admin)
    admin.ok(
        "post",
        "/notices",
        {
            "kind": "outage",
            "title": "Water outage Sunday",
            "body": "Tank cleaning 10am-2pm",
            "audience": "residents",
            "channels": ["in_app", "sms", "whatsapp"],
        },
    )
    assert as_(world.resident).ok("get", "/notices")["total"] == 1
    assert as_(world.guard).ok("get", "/notices")["total"] == 0
    n = as_(world.resident2).ok("get", "/notifications")["items"][0]
    assert set(n["channels"]) >= {"in_app", "sms", "whatsapp"}
    assert as_(world.resident).ok("get", "/notifications/unread-count")["count"] == 1
    as_(world.resident).ok("post", "/notifications/read")
    assert as_(world.resident).ok("get", "/notifications/unread-count")["count"] == 0
    assert admin.post("/notices", {"title": "x" * 5, "body": "b", "channels": ["fax"]}).status_code == 422


def test_dashboards_reports_and_csv(as_, world):
    sup, admin = as_(world.supervisor), as_(world.admin)
    sup.ok(
        "post",
        "/maintenance",
        {"title": "Overdue job", "category": "civil", "assigned_staff_id": str(world.staff.id), "due_at": "2020-01-01T00:00:00Z"},
    )
    d = admin.ok("get", "/dashboard")
    for key in (
        "open_complaints",
        "active_maintenance",
        "overdue_tasks",
        "pending_approvals",
        "maintenance_cost_this_month",
        "billing",
        "metrics",
    ):
        assert key in d
    assert d["overdue_tasks"] == 1 and d["properties"] == 2
    assert as_(world.staff).ok("get", "/dashboard")["overdue"] == 1
    assert as_(world.resident).ok("get", "/dashboard")["properties"][0]["plot_number"] == "117"
    assert "visitors_inside" in as_(world.guard).ok("get", "/dashboard")
    rep = admin.ok("get", "/reports/maintenance", params={"report": "pending"})
    assert rep["summary"]["count"] == 1 and rep["rows"][0]["overdue"]
    csv = admin.get("/reports/maintenance", params={"report": "history", "format": "csv"})
    assert csv.status_code == 200 and csv.text.splitlines()[0].startswith("number,")
    assert admin.ok("get", "/reports/vendors")[0]["vendor"] == "FixIt Gates"
    assert as_(world.resident).get("/reports/maintenance").status_code == 403
    staff_rows = admin.ok("get", "/reports/staff")
    assert staff_rows[0]["name"] == "Ramesh Kumar" and staff_rows[0]["overdue"] == 1


def test_search_interpretation():
    from app.services.search import interpret

    f = interpret("Show all gate repairs for Plot 117 in the last 12 months")
    assert f["plot"] == "117" and f["category"] == "gate_fence" and f["type"] == "maintenance" and "text" not in f
    assert interpret("GP-MNT-2026-00418") == {"number": "GP-MNT-2026-00418", "type": "maintenance"}
    f = interpret("open complaints plot 204")
    assert f["type"] == "complaint" and f["plot"] == "204" and "open" in f["status"]
    assert interpret("pump motor")["text"] == "pump motor"


def test_search_matches_words_left_after_interpretation(as_, world):
    sup = as_(world.supervisor)
    t = sup.ok("post", "/maintenance", {"title": "E2E clean 12345 batch", "category": "cleaning"})
    res = sup.ok("get", "/records/search", params={"q": "E2E clean 12345"})
    assert res["interpreted"]["category"] == "cleaning" and res["interpreted"]["text"] == "e2e 12345"
    assert [h["id"] for h in res["items"]] == [t["id"]]
