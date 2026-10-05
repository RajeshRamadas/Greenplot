"""Customer ticketing & vendor service management (ticketing requirements §37-38)."""

import uuid
from datetime import timedelta

from app.models import NotificationDelivery, Ticket, TicketSLA
from app.models.base import utcnow
from app.services import notifications
from app.services import tickets as tsvc
from tests.conftest import jpeg_bytes


def raise_ticket(resident, world, **kw):
    body = {
        "category": "gate_fence",
        "subcategory": "Gate not closing",
        "title": "Gate does not latch",
        "description": "The plot gate swings open in the wind.",
        "property_id": str(world.p117.id),
        "preferred_time": "After 5 pm",
        **kw,
    }
    return resident.ok("post", "/tickets", body)


def do_vendor_work(vendor, ticket_id, task_id):
    """Accept → start → before/after photos → checklist → notes → submit, all from the ticket."""
    vendor.ok("post", f"/tickets/{ticket_id}/accept")
    r = vendor.upload("maintenance_task", task_id, jpeg_bytes((120, 90, 80)), "image/jpeg", "before_photo")
    assert r.status_code == 200, r.text
    t = vendor.ok("post", f"/tickets/{ticket_id}/start", {"latitude": 12.97, "longitude": 77.59})
    assert t["status"] == "in_progress"
    # Proof is enforced: completion without evidence fails.
    r = vendor.post(f"/tickets/{ticket_id}/complete", {"work_notes": "Done"})
    assert r.status_code == 422 and "after_photo" in r.json()["detail"]["missing"]
    task = vendor.ok("get", f"/maintenance/{task_id}")
    for item in task["checklist"]:
        vendor.ok("patch", f"/maintenance/{task_id}/checklist/{item['id']}", {"status": "completed"})
    r = vendor.upload("maintenance_task", task_id, jpeg_bytes((60, 160, 90)), "image/jpeg", "after_photo")
    assert r.status_code == 200, r.text
    return vendor.ok("post", f"/tickets/{ticket_id}/complete", {"work_notes": "Replaced the latch and realigned the gate."})


def test_full_ticket_lifecycle_customer_to_vendor_to_closure(as_, world, db):
    resident, admin, sup, vendor = as_(world.resident), as_(world.admin), as_(world.supervisor), as_(world.vendor_user)

    # 1-2. Customer creates a ticket with a unique number and SLA.
    t = raise_ticket(resident, world)
    assert t["number"].startswith("GP-TKT-") and len(t["number"].split("-")[-1]) == 6
    assert t["status"] == "open" and t["priority"] == "medium" and t["category_code"] == "gate_fence"
    assert t["sla"]["state"] == "on_track"
    tid = t["id"]
    photo = resident.upload("ticket", tid, jpeg_bytes(), "image/jpeg")
    assert photo.status_code == 200, photo.text

    # 3-4. Office sees it, reviews and re-prioritises (audited, SLA recomputed).
    listed = admin.ok("get", "/tickets?bucket=new")
    assert [x["number"] for x in listed["items"]] == [t["number"]]
    before_due = t["due_at"]
    admin.ok("post", f"/tickets/{tid}/review")
    t = admin.ok("patch", f"/tickets/{tid}", {"priority": "high"})
    assert t["status"] == "under_review" and t["priority"] == "high" and t["due_at"] < before_due
    assert t["first_response_at"]

    # Vendor cannot see the ticket before assignment.
    assert vendor.get(f"/tickets/{tid}").status_code == 404

    # 5-6. Assign to the vendor: a linked work order is raised and the vendor is notified.
    t = admin.ok("post", f"/tickets/{tid}/assign", {"vendor_id": str(world.vendor.id), "notes": "Bring a latch"})
    assert t["status"] == "assigned" and t["assignee_name"] == "FixIt Gates"
    task_id = t["work_order"]["id"]
    assert t["work_order"]["number"].startswith("GP-MNT-") and t["work_order"]["category"] == "gate_fence"
    notes = vendor.ok("get", "/notifications")
    items = notes["items"] if isinstance(notes, dict) else notes
    assert any(n["entity_type"] == "ticket" and n["entity_id"] == tid for n in items)
    vt = vendor.ok("get", f"/tickets/{tid}")
    assert {"accept", "reject_assignment", "start"} <= set(vt["allowed_actions"])
    assert vt["customer_phone"] is None  # contact hidden by default
    assert vendor.ok("get", "/tickets/dashboard")["sections"]["new_assignments"] == 1

    # 7-11. Vendor accepts, works with proof, and submits.
    t = do_vendor_work(vendor, tid, task_id)
    assert t["status"] == "verification"

    # Customer sees progress but not the proof before approval.
    rt = resident.ok("get", f"/tickets/{tid}")
    assert rt["status"] == "verification"
    assert [a["source"] for a in rt["attachments"]] == ["ticket"]

    # 13. Supervisor requests rework; 12/14. then verifies and approves.
    t = sup.ok("post", f"/tickets/{tid}/verify", {"decision": "rework", "comment": "Latch still loose"})
    assert t["status"] == "in_progress" and t["rework_count"] == 1
    vendor.ok("post", f"/tickets/{tid}/start")
    vendor.upload("maintenance_task", task_id, jpeg_bytes((10, 200, 10)), "image/jpeg", "after_photo")
    t = vendor.ok("post", f"/tickets/{tid}/complete", {"work_notes": "Tightened the latch bolts."})
    assert t["status"] == "verification"
    t = sup.ok("post", f"/tickets/{tid}/verify", {"decision": "approve", "comment": "Checked on site"})
    assert t["status"] == "resolved" and t["verified_at"] and t["sla"]["state"] == "met"

    # 18. Customer views the completed ticket with proof; 19. feedback closes it.
    rt = resident.ok("get", f"/tickets/{tid}")
    assert {"confirm", "feedback", "reopen"} <= set(rt["allowed_actions"])
    assert any(a["source"] == "work" and a["evidence_type"] == "after_photo" for a in rt["attachments"])
    t = resident.ok("post", f"/tickets/{tid}/feedback", {"outcome": "resolved", "rating": 5, "comment": "Quick fix"})
    assert t["status"] == "closed" and t["rating"] == 5 and t["closed_at"]

    # 16-17. Closure notification sent and delivery logged.
    db.expire_all()
    rows = db.query(NotificationDelivery).filter_by(entity_id=uuid.UUID(tid), event_type="ticket_closed").all()
    assert {r.channel for r in rows} >= {"in_app", "push", "whatsapp"}
    assert all(r.user_id == world.resident.id for r in rows)
    log = admin.ok("get", f"/tickets/{tid}/notifications")
    assert any(r["event_type"] == "ticket_closed" and r["channel"] == "in_app" and r["status"] == "stored" for r in log)
    resident_notes = resident.ok("get", "/notifications")
    items = resident_notes["items"] if isinstance(resident_notes, dict) else resident_notes
    assert any(n["title"] == "GreenPlot Ticket Closed" for n in items)

    # Timeline tells the whole story.
    timeline = [i["title"] for i in t["timeline"]]
    for step in ("Ticket created", "Assigned to FixIt Gates", "Work in progress", "Awaiting supervisor verification", "Resolved", "Closed"):
        assert step in timeline, step
    assert any(i["kind"] == "notification" for i in t["timeline"])

    # 21. Ticket appears in the property history; 22. audit retained.
    hist = admin.ok("get", f"/properties/{world.p117.id}/history")
    assert any(e["kind"] == "ticket" and e["status"] == "closed" for e in hist)
    audit = admin.ok("get", f"/tickets/{tid}/history")["audit"]
    actions = {a["action"] for a in audit}
    assert {"ticket.created", "ticket.assigned", "ticket.closed", "ticket.customer_notified", "ticket.feedback"} <= actions

    # Reports and dashboards include it.
    rep = admin.ok("get", "/tickets/reports")
    assert rep["volume"]["closed"] == 1 and rep["vendors"][0]["name"] == "FixIt Gates" and rep["vendors"][0]["avg_rating"] == 5
    assert vendor.ok("get", "/tickets/dashboard")["sections"]["completed"] == 1


def test_vendor_rejection_returns_ticket_for_reassignment(as_, world):
    resident, admin, vendor, staff = as_(world.resident), as_(world.admin), as_(world.vendor_user), as_(world.staff)
    t = raise_ticket(resident, world)
    tid = t["id"]
    admin.ok("post", f"/tickets/{tid}/assign", {"vendor_id": str(world.vendor.id)})
    r = vendor.post(f"/tickets/{tid}/reject", {"reason_code": "bogus", "reason": "x"})
    assert r.status_code == 422
    vendor.ok("post", f"/tickets/{tid}/reject", {"reason_code": "no_availability", "reason": "Team booked all week"})

    t = admin.ok("get", f"/tickets/{tid}")
    assert t["status"] == "under_review" and t["assigned_to_id"] is None  # not closed
    assert "assign" in t["allowed_actions"]
    assert any("declined" in i["title"] for i in t["timeline"])
    assert vendor.get(f"/tickets/{tid}").status_code == 404
    dash = vendor.ok("get", "/tickets/dashboard")
    assert dash["sections"]["rejected"] == 1 and dash["rejected"][0]["reason"].startswith("no availability")

    # Customer does not see the internal rejection reason.
    rt = resident.ok("get", f"/tickets/{tid}")
    assert not any("Team booked" in (i["detail"] or "") for i in rt["timeline"])
    assert not any(c["visibility"] == "internal" for c in rt["comments"])

    # Reassign to staff, preserving history.
    t = admin.ok("post", f"/tickets/{tid}/assign", {"staff_id": str(world.staff.id)})
    assert t["status"] == "assigned" and t["assigned_to_type"] == "staff"
    rows = admin.ok("get", f"/tickets/{tid}/assignments")
    assert len(rows) == 2 and rows[0]["rejected_at"] and rows[0]["rejection_reason"]
    # Reassigning an active assignment needs a reason.
    r = admin.post(f"/tickets/{tid}/assign", {"vendor_id": str(world.vendor.id)})
    assert r.status_code == 422
    staff.ok("post", f"/tickets/{tid}/accept")
    assert staff.ok("get", f"/tickets/{tid}")["status"] == "accepted"


def test_work_done_from_job_screen_keeps_ticket_in_step(as_, world):
    """Vendors may work from the maintenance job; the ticket follows (§32)."""
    resident, admin, vendor = as_(world.resident), as_(world.admin), as_(world.vendor_user)
    tid = raise_ticket(resident, world)["id"]
    task_id = admin.ok("post", f"/tickets/{tid}/assign", {"vendor_id": str(world.vendor.id)})["work_order"]["id"]
    vendor.ok("post", f"/maintenance/{task_id}/accept")
    assert resident.ok("get", f"/tickets/{tid}")["status"] == "accepted"
    vendor.ok("post", f"/maintenance/{task_id}/start", {})
    assert resident.ok("get", f"/tickets/{tid}")["status"] == "in_progress"
    vendor.ok("post", f"/maintenance/{task_id}/decline", {"reason": "Wrong trade"}, status=(200, 409))


def test_internal_notes_and_comment_visibility(as_, world):
    resident, admin, vendor = as_(world.resident), as_(world.admin), as_(world.vendor_user)
    tid = raise_ticket(resident, world)["id"]
    admin.ok("post", f"/tickets/{tid}/assign", {"vendor_id": str(world.vendor.id)})
    admin.ok("post", f"/tickets/{tid}/comments", {"message": "Customer is difficult", "visibility": "internal"})
    admin.ok("post", f"/tickets/{tid}/comments", {"message": "Vendor: use side entrance", "visibility": "vendor"})
    resident.ok("post", f"/tickets/{tid}/comments", {"message": "Please call before coming"})
    assert resident.post(f"/tickets/{tid}/comments", {"message": "x", "visibility": "internal"}).status_code == 403
    assert vendor.post(f"/tickets/{tid}/comments", {"message": "x", "visibility": "internal"}).status_code == 403

    seen_by = {
        "resident": {c["message"] for c in resident.ok("get", f"/tickets/{tid}")["comments"]},
        "vendor": {c["message"] for c in vendor.ok("get", f"/tickets/{tid}")["comments"]},
        "admin": {c["message"] for c in admin.ok("get", f"/tickets/{tid}")["comments"]},
    }
    assert "Customer is difficult" not in seen_by["resident"] | seen_by["vendor"]
    assert "Vendor: use side entrance" not in seen_by["resident"] and "Vendor: use side entrance" in seen_by["vendor"]
    assert "Please call before coming" in seen_by["vendor"] and "Customer is difficult" in seen_by["admin"]


def test_access_isolation(as_, world):
    resident, resident2, admin_b, guard, vendor = (
        as_(world.resident),
        as_(world.resident2),
        as_(world.admin_b),
        as_(world.guard),
        as_(world.vendor_user),
    )
    tid = raise_ticket(resident, world)["id"]
    # Another resident, another tenant, a guard and an unassigned vendor cannot read it.
    assert resident2.get(f"/tickets/{tid}").status_code == 404
    assert admin_b.get(f"/tickets/{tid}").status_code == 404
    assert guard.get(f"/tickets/{tid}").status_code == 403
    assert vendor.get(f"/tickets/{tid}").status_code == 404
    assert resident2.ok("get", "/tickets")["total"] == 0
    # Nor attach evidence to it.
    r = resident2.upload("ticket", tid, jpeg_bytes(), "image/jpeg")
    assert r.status_code == 404
    # Residents cannot raise tickets for someone else's plot or manage tickets.
    r = resident.post("/tickets", {"category": "plumbing", "title": "Leak", "description": "Leak here", "property_id": str(world.p204.id)})
    assert r.status_code == 403
    assert resident.post(f"/tickets/{tid}/assign", {"vendor_id": str(world.vendor.id)}).status_code == 403
    assert resident.post(f"/tickets/{tid}/verify", {"decision": "approve"}).status_code == 403


def test_customer_priority_cap_and_reopen_policy(as_, world, db):
    resident, admin = as_(world.resident), as_(world.admin)
    t = raise_ticket(resident, world, priority="critical")
    assert t["priority"] == "high"  # capped by ticket_customer_max_priority
    tid = t["id"]
    admin.ok("post", f"/tickets/{tid}/resolve", {"resolution": "Latch adjusted by the guard"})
    t = admin.ok("post", f"/tickets/{tid}/close", {})
    assert t["status"] == "closed"

    # Customer reopens within the window with a reason; the SLA restarts.
    assert resident.post(f"/tickets/{tid}/reopen", {"resolution": ""}).status_code == 422
    t = resident.ok("post", f"/tickets/{tid}/reopen", {"resolution": "Gate is open again"})
    assert t["status"] == "reopened" and t["reopen_count"] == 1 and t["closed_at"] is None
    assert t["customer_confirmation"] == "still_issue"

    # Close again, then move the closure outside the reopen window.
    admin.ok("post", f"/tickets/{tid}/resolve", {"resolution": "Hinge replaced"})
    admin.ok("post", f"/tickets/{tid}/close", {})
    db.expire_all()
    row = db.get(Ticket, uuid.UUID(tid))
    row.closed_at = utcnow() - timedelta(days=30)
    db.commit()
    r = resident.post(f"/tickets/{tid}/reopen", {"resolution": "Again"})
    assert r.status_code == 409
    admin.ok("post", f"/tickets/{tid}/reopen", {"resolution": "Office reopens per policy"})


def test_still_an_issue_reopens_and_customer_can_cancel_unassigned(as_, world):
    resident, admin = as_(world.resident), as_(world.admin)
    tid = raise_ticket(resident, world)["id"]
    admin.ok("post", f"/tickets/{tid}/resolve", {"resolution": "Fixed"})
    t = resident.ok("post", f"/tickets/{tid}/feedback", {"outcome": "still_issue", "comment": "Still swinging open"})
    assert t["status"] == "reopened"
    t = resident.ok("post", f"/tickets/{tid}/status", {"action": "cancel", "reason": "Fixed it myself"})
    assert t["status"] == "cancelled"

    tid2 = raise_ticket(resident, world)["id"]
    admin.ok("post", f"/tickets/{tid2}/assign", {"vendor_id": str(world.vendor.id)})
    assert resident.post(f"/tickets/{tid2}/status", {"action": "cancel"}).status_code == 403


def test_waiting_for_customer_resumes_on_reply(as_, world):
    resident, admin = as_(world.resident), as_(world.admin)
    tid = raise_ticket(resident, world)["id"]
    admin.ok("post", f"/tickets/{tid}/review")
    t = admin.ok("post", f"/tickets/{tid}/status", {"action": "wait", "reason": "Which gate, front or side?"})
    assert t["status"] == "waiting_for_customer"
    resident.ok("post", f"/tickets/{tid}/comments", {"message": "The front gate"})
    assert resident.ok("get", f"/tickets/{tid}")["status"] == "under_review"


def test_sla_breach_escalation_and_auto_close(as_, world, db):
    resident, admin = as_(world.resident), as_(world.admin)
    tid = raise_ticket(resident, world, category="electrical", title="Power out", description="No power on the plot")["id"]
    t = resident.ok("get", f"/tickets/{tid}")
    assert t["priority"] == "high"  # category default
    db.expire_all()
    ticket = db.get(Ticket, uuid.UUID(tid))
    sla = db.query(TicketSLA).filter_by(ticket_id=ticket.id).one()
    # Approaching: 85% of the response window elapsed.
    now = ticket.created_at + (sla.response_due_at - ticket.created_at) * 0.85
    assert tsvc.run_sla_checks(db, now) == 1
    db.commit()
    assert sla.at_risk_notified_at is not None
    # Breach: notify office, then escalate later.
    later = sla.resolution_due_at + timedelta(minutes=1)
    assert tsvc.run_sla_checks(db, later) == 1
    db.commit()
    assert sla.response_breached and sla.resolution_breached and sla.escalation_level == 1
    assert tsvc.run_sla_checks(db, later + timedelta(minutes=5)) == 0  # not re-sent immediately
    assert tsvc.run_sla_checks(db, later + timedelta(hours=25)) == 1
    db.commit()
    assert sla.escalation_level == 2
    assert admin.ok("get", "/tickets?bucket=sla_breached")["total"] == 1
    assert admin.ok("get", "/tickets/dashboard")["kpis"]["sla_breached"] == 1

    # Resolved tickets close themselves after the configured days, with the closure notice.
    admin.ok("post", f"/tickets/{tid}/resolve", {"resolution": "Fuse replaced"})
    db.expire_all()
    assert tsvc.auto_close_resolved(db, utcnow() + timedelta(days=4)) == 1
    db.commit()
    db.expire_all()
    assert db.get(Ticket, ticket.id).status == "closed"
    assert db.query(NotificationDelivery).filter_by(entity_id=ticket.id, event_type="ticket_closed").count() >= 1


def test_notification_failures_are_logged_and_retried(as_, world, db, monkeypatch):
    calls = {"n": 0}

    def flaky(user, title, body):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("provider down")
        return "sent"

    monkeypatch.setattr(notifications.ADAPTERS["push"], "send", flaky)
    notifications.notify(db, world.ta.id, [world.resident.id], "ticket_update", "Hello", None, "ticket", None, ["in_app", "push"])
    db.commit()
    row = db.query(NotificationDelivery).filter_by(channel="push").one()
    assert row.status == "failed" and "provider down" in row.failure_reason
    assert notifications.retry_failed_deliveries(db) == 1
    db.commit()
    assert row.status == "sent" and row.attempts == 2


def test_category_configuration_and_search(as_, world):
    admin, resident = as_(world.admin), as_(world.resident)
    cats = resident.ok("get", "/tickets/categories")
    assert len(cats) == 14 and {c["code"] for c in cats} >= {"cleaning", "plumbing", "streetlight", "other"}
    plumbing = next(c for c in cats if c["code"] == "plumbing")
    assert plumbing["effective_response_minutes"] == 240
    assert resident.patch(f"/tickets/categories/{plumbing['id']}", {"resolution_sla_minutes": 60}).status_code == 403
    c = admin.ok("patch", f"/tickets/categories/{plumbing['id']}", {"resolution_sla_minutes": 120, "customer_sets_priority": False})
    assert c["effective_resolution_minutes"] == 120
    t = resident.ok("post", "/tickets", {"category": "plumbing", "title": "Tap leak", "description": "Kitchen tap", "priority": "high"})
    assert t["priority"] == "medium"  # category does not let customers pick
    hits = resident.ok("get", f"/records/search?q={t['number']}")
    assert any(h["type"] == "ticket" and h["id"] == t["id"] for h in hits["items"])
