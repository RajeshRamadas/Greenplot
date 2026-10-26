"""WhatsApp audio/video calls to customers: only the office and the person assigned to the job."""

from urllib.parse import unquote

from app.models import AuditLog
from tests.test_tickets import raise_ticket


def test_ticket_call_only_for_office_and_assignee(as_, world, db):
    world.resident.phone = "98450 12345"
    db.commit()
    resident, admin, staff, staff2, vendor = (
        as_(world.resident),
        as_(world.admin),
        as_(world.staff),
        as_(world.staff2),
        as_(world.vendor_user),
    )
    tid = raise_ticket(resident, world)["id"]

    # The customer and unassigned staff get no call button and are refused.
    assert "call_customer" not in resident.ok("get", f"/tickets/{tid}")["allowed_actions"]
    assert resident.post(f"/tickets/{tid}/whatsapp-call", {"mode": "audio"}).status_code == 403
    assert staff.post(f"/tickets/{tid}/whatsapp-call", {"mode": "audio"}).status_code == 404

    # The office can call; the link opens the customer's chat with a message saying who is calling.
    assert "call_customer" in admin.ok("get", f"/tickets/{tid}")["allowed_actions"]
    link = admin.ok("post", f"/tickets/{tid}/whatsapp-call", {"mode": "video"})
    assert link["mode"] == "video" and link["url"].startswith("https://wa.me/919845012345?text=")
    text = unquote(link["url"].split("text=", 1)[1])
    assert text.startswith("Hi Priya, this is Asha Admin from GreenPlot") and "video call" in text

    # Once assigned, only that staff member (not a colleague) can call.
    admin.ok("post", f"/tickets/{tid}/assign", {"staff_id": str(world.staff.id)})
    assert "call_customer" in staff.ok("get", f"/tickets/{tid}")["allowed_actions"]
    assert staff.ok("post", f"/tickets/{tid}/whatsapp-call", {"mode": "audio"})["mode"] == "audio"
    assert staff2.post(f"/tickets/{tid}/whatsapp-call", {"mode": "audio"}).status_code == 404

    calls = db.query(AuditLog).filter(AuditLog.action == "customer.whatsapp_call").all()
    assert sorted(c.new_value["mode"] for c in calls) == ["audio", "video"]

    # A vendor assignee needs the layout to share the customer's contact.
    admin.ok("post", f"/tickets/{tid}/assign", {"vendor_id": str(world.vendor.id), "reason": "Needs a gate specialist"})
    assert "call_customer" not in vendor.ok("get", f"/tickets/{tid}")["allowed_actions"]
    assert vendor.post(f"/tickets/{tid}/whatsapp-call", {"mode": "audio"}).status_code == 403
    assert staff.post(f"/tickets/{tid}/whatsapp-call", {"mode": "audio"}).status_code == 404
    admin.ok("patch", "/settings", {"ticket_share_customer_contact": True})
    assert "call_customer" in vendor.ok("get", f"/tickets/{tid}")["allowed_actions"]
    assert vendor.ok("post", f"/tickets/{tid}/whatsapp-call", {"mode": "video"})["url"].startswith("https://wa.me/91")


def test_job_call_reaches_plot_owner(as_, world, db):
    world.p204.owner_phone = "+91 99000 11122"
    world.p204.owner_name = "Rahul Owner"
    db.commit()
    sup, staff, staff2, resident = as_(world.supervisor), as_(world.staff), as_(world.staff2), as_(world.resident2)
    task = sup.ok(
        "post",
        "/maintenance",
        {"title": "Clear weeds", "category": "cleaning", "property_id": str(world.p204.id), "assigned_staff_id": str(world.staff.id)},
    )
    tid = task["id"]
    assert "call_customer" in staff.ok("get", f"/maintenance/{tid}")["allowed_actions"]
    link = staff.ok("post", f"/maintenance/{tid}/whatsapp-call", {"mode": "video"})
    assert link["url"].startswith("https://wa.me/919900011122?text=")
    assert "Hi Rahul, this is Ramesh Kumar" in unquote(link["url"])
    assert staff2.post(f"/maintenance/{tid}/whatsapp-call", {"mode": "video"}).status_code == 404
    assert resident.post(f"/maintenance/{tid}/whatsapp-call", {"mode": "video"}).status_code == 403
    assert staff.post(f"/maintenance/{tid}/whatsapp-call", {"mode": "fax"}).status_code == 422

    # No number on record: no button, and a clear error.
    t2 = sup.ok("post", "/maintenance", {"title": "Paint", "category": "painting", "assigned_staff_id": str(world.staff.id)})
    assert "call_customer" not in staff.ok("get", f"/maintenance/{t2['id']}")["allowed_actions"]
    assert staff.post(f"/maintenance/{t2['id']}/whatsapp-call", {"mode": "audio"}).status_code == 409
