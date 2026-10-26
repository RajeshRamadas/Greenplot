"""WhatsApp audio/video calls to customers: only the office and the person assigned to the job."""

import uuid
from urllib.parse import unquote

from app.core.deps import Actor
from app.models import AuditLog, MaintenanceTask, Resident, Ticket
from app.services import customer_calls
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


def test_call_rules_apart_from_view_access(as_, world, db):
    """The call rules themselves refuse unassigned staff, even where view access would not stop them."""
    world.resident.phone = "9845012345"
    db.commit()
    resident, admin = as_(world.resident), as_(world.admin)
    tid = raise_ticket(resident, world)["id"]
    admin.ok("post", f"/tickets/{tid}/assign", {"staff_id": str(world.staff.id)})
    t = db.get(Ticket, uuid.UUID(tid))
    task = db.query(MaintenanceTask).filter_by(ticket_id=t.id).one()
    staff, staff2, sup = (Actor(user=u, ip=None, user_agent=None) for u in (world.staff, world.staff2, world.supervisor))
    assert customer_calls.may_call_ticket(db, staff, t) and not customer_calls.may_call_ticket(db, staff2, t)
    assert customer_calls.may_call_task(db, staff, task) and not customer_calls.may_call_task(db, staff2, task)

    # A job raised from a ticket calls the ticket's customer, greeting them by name, never the plot's other owners.
    assert customer_calls.task_contact(db, task) == ("919845012345", "Priya Owner")
    world.resident.phone = None
    world.p117.owner_phone = "9900011122"
    db.commit()
    assert customer_calls.task_contact(db, task) is None

    # Supervisors can still call once the job is approved; the worker no longer can.
    world.resident.phone = "9845012345"
    task.status = "approved"
    db.commit()
    assert customer_calls.may_call_task(db, sup, task) and not customer_calls.may_call_task(db, staff, task)


def test_owner_contact_order_and_fallbacks(world, db):
    p = world.p204
    db.add_all(
        [
            Resident(tenant_id=world.ta.id, property_id=p.id, name="Second Owner", relation="owner", phone="9000000222"),
            Resident(tenant_id=world.ta.id, property_id=p.id, name="Main Owner", relation="owner", phone="9000000111", is_primary=True),
        ]
    )
    p.owner_phone = "12"  # unusable: falls through to the next number
    task = MaintenanceTask(tenant_id=world.ta.id, number="GP-MNT-X", title="Weeding", category="cleaning", property_id=p.id)
    db.add(task)
    db.commit()
    assert customer_calls.task_contact(db, task) == ("919000000111", "Main Owner")
    assert "?text=Hi%2C%20this%20is" in customer_calls.call_link("919000000111", "audio", "Ramesh", "   ", "GP-MNT-X", "Weeding")
