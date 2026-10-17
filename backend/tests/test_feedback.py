"""Ratings after each job, low-rating alerts and the support contact (customer happiness)."""

import uuid

from app.core.config import get_settings
from app.models import MaintenanceTask, Notification
from app.services.numbering import next_number
from tests.test_tickets import do_vendor_work, raise_ticket


def submitted_job(world, **kw) -> MaintenanceTask:
    """A cleaning job on plot 117 that staff have finished and submitted for review."""
    db = world.db
    t = MaintenanceTask(
        tenant_id=world.ta.id,
        number=next_number(db, world.ta.id, "MNT"),
        title="Clear weeds and debris",
        category="cleaning",
        status="completed",
        source="schedule",
        property_id=world.p117.id,
        assigned_staff_id=world.staff.id,
        completed_by=world.staff.id,
        **kw,
    )
    db.add(t)
    db.commit()
    return t


def alerts(world, kind="low_rating"):
    world.db.expire_all()
    return list(world.db.query(Notification).filter(Notification.kind == kind).all())


def test_customer_is_asked_to_rate_and_low_rating_alerts_the_office(as_, world):
    resident, sup, staff = as_(world.resident), as_(world.supervisor), as_(world.staff)
    job = submitted_job(world)

    pending = resident.ok("get", f"/maintenance/{job.id}")
    assert "rate" not in pending["allowed_actions"]
    assert resident.post(f"/maintenance/{job.id}/rate", {"rating": 5}).status_code == 409

    sup.ok("post", f"/maintenance/{job.id}/approve", {"comment": "Looks clean"})
    asks = alerts(world, "job_feedback")
    assert [n.user_id for n in asks] == [world.resident.id] and asks[0].entity_id == job.id

    d = resident.ok("get", f"/maintenance/{job.id}")
    assert "rate" in d["allowed_actions"]
    assert resident.post(f"/maintenance/{job.id}/rate", {"rating": 0}).status_code == 422
    # Only the plot's customers can rate; staff and other residents cannot.
    assert staff.post(f"/maintenance/{job.id}/rate", {"rating": 5}).status_code == 403
    assert as_(world.resident2).post(f"/maintenance/{job.id}/rate", {"rating": 5}).status_code == 404

    d = resident.ok("post", f"/maintenance/{job.id}/rate", {"rating": 2, "comment": "  Debris left by the gate  "})
    assert d["rating"] == 2 and d["rating_comment"] == "Debris left by the gate" and d["rated_at"]
    assert "rate" not in d["allowed_actions"]
    assert resident.post(f"/maintenance/{job.id}/rate", {"rating": 5}).status_code == 409

    low = alerts(world)
    assert {n.user_id for n in low} == {world.admin.id, world.supervisor.id}
    assert low[0].title.startswith("Low rating 2/5") and "Debris left by the gate" in low[0].body
    assert low[0].entity_type == "maintenance_task" and low[0].entity_id == job.id
    assert sup.ok("get", f"/maintenance/{job.id}")["rating"] == 2


def test_good_job_rating_sends_no_alert(as_, world):
    job = submitted_job(world)
    as_(world.supervisor).ok("post", f"/maintenance/{job.id}/approve", {})
    as_(world.resident).ok("post", f"/maintenance/{job.id}/rate", {"rating": 4})
    assert alerts(world) == []


def test_ticket_jobs_are_rated_on_the_ticket(as_, world):
    resident, admin, sup, vendor = as_(world.resident), as_(world.admin), as_(world.supervisor), as_(world.vendor_user)
    t = raise_ticket(resident, world)
    t = admin.ok("post", f"/tickets/{t['id']}/assign", {"vendor_id": str(world.vendor.id)})
    task_id = t["maintenance_task_id"]
    do_vendor_work(vendor, t["id"], task_id)
    sup.ok("post", f"/tickets/{t['id']}/verify", {"decision": "approve"})

    # No second prompt for the work order: the ticket carries the rating.
    assert alerts(world, "job_feedback") == []
    assert "rate" not in resident.ok("get", f"/maintenance/{task_id}")["allowed_actions"]
    assert resident.post(f"/maintenance/{task_id}/rate", {"rating": 1}).status_code == 409

    resident.ok("post", f"/tickets/{t['id']}/feedback", {"outcome": "resolved", "rating": 3, "comment": "Took too long"})
    low = alerts(world)
    assert {n.user_id for n in low} == {world.admin.id, world.supervisor.id}
    assert low[0].entity_type == "ticket" and low[0].entity_id == uuid.UUID(t["id"])
    assert t["number"] in low[0].title and "Took too long" in low[0].body

    # Sending feedback again does not alert the office a second time.
    resident.post(f"/tickets/{t['id']}/feedback", {"rating": 1, "comment": "Again"})
    assert len(alerts(world)) == len(low)


def test_public_contact_returns_configured_whatsapp_number(client):
    r = client.get("/api/v1/public/contact")
    assert r.status_code == 200 and r.json() == {"whatsapp_number": get_settings().whatsapp_number}
