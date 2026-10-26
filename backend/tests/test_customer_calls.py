"""Customers' numbers and WhatsApp calls: only layout admins see the numbers, so only they can call."""

import uuid
from urllib.parse import unquote

from app.core.deps import Actor
from app.models import AuditLog, MaintenanceTask, Resident, Ticket
from app.services import customer_calls
from tests.test_tickets import raise_ticket


def test_only_admins_see_numbers_and_call(as_, world, db):
    world.resident.phone = "98450 12345"
    world.resident.whatsapp_phone = "98450 99999"
    db.commit()
    resident, admin, sup, staff, vendor = (
        as_(world.resident),
        as_(world.admin),
        as_(world.supervisor),
        as_(world.staff),
        as_(world.vendor_user),
    )
    tid = raise_ticket(resident, world)["id"]

    # The admin sees both numbers and can call; the call goes to the customer's WhatsApp number.
    t = admin.ok("get", f"/tickets/{tid}")
    assert t["customer_phone"] == "98450 12345" and t["customer_whatsapp"] == "98450 99999"
    assert "call_customer" in t["allowed_actions"]
    link = admin.ok("post", f"/tickets/{tid}/whatsapp-call", {"mode": "video"})
    assert link["mode"] == "video" and link["url"].startswith("https://wa.me/919845099999?text=")
    text = unquote(link["url"].split("text=", 1)[1])
    assert text.startswith("Hi Priya, this is Asha Admin from GreenPlot") and "video call" in text
    assert admin.post(f"/tickets/{tid}/whatsapp-call", {"mode": "fax"}).status_code == 422
    assert db.query(AuditLog).filter(AuditLog.action == "customer.whatsapp_call").count() == 1

    # Supervisors and the assigned staff member see no number and cannot call.
    admin.ok("post", f"/tickets/{tid}/assign", {"staff_id": str(world.staff.id)})
    for who in (sup, staff):
        t = who.ok("get", f"/tickets/{tid}")
        assert t["customer_phone"] is None and t["customer_whatsapp"] is None and t["contact_phone"] is None
        assert "call_customer" not in t["allowed_actions"]
        assert who.post(f"/tickets/{tid}/whatsapp-call", {"mode": "audio"}).status_code == 403
    # Not even when the layout shares contacts with vendors.
    admin.ok("patch", "/settings", {"ticket_share_customer_contact": True})
    assert staff.ok("get", f"/tickets/{tid}")["customer_phone"] is None

    # A vendor assignee sees the number only when the layout shares it, and still cannot call.
    admin.ok("post", f"/tickets/{tid}/assign", {"vendor_id": str(world.vendor.id), "reason": "Needs a gate specialist"})
    vt = vendor.ok("get", f"/tickets/{tid}")
    assert vt["customer_phone"] == "98450 12345" and "call_customer" not in vt["allowed_actions"]
    assert vendor.post(f"/tickets/{tid}/whatsapp-call", {"mode": "audio"}).status_code == 403

    # The customer sees their own numbers.
    assert resident.ok("get", f"/tickets/{tid}")["customer_whatsapp"] == "98450 99999"


def test_numbers_hidden_on_plots_residents_and_users(as_, world, db):
    world.p204.owner_phone = "9900011122"
    world.p204.owner_whatsapp = "9900033344"
    world.resident2.phone = "9000000204"
    db.add(Resident(tenant_id=world.ta.id, property_id=world.p117.id, name="Priya Owner", relation="owner", phone="9000000117"))
    db.commit()
    admin, sup, staff, guard, owner = as_(world.admin), as_(world.supervisor), as_(world.staff), as_(world.guard), as_(world.resident2)

    p = admin.ok("get", f"/properties/{world.p204.id}")
    assert (p["owner_phone"], p["owner_whatsapp"]) == ("9900011122", "9900033344")
    assert owner.ok("get", f"/properties/{world.p204.id}")["owner_whatsapp"] == "9900033344"
    for who in (sup, staff, guard):
        p = who.ok("get", f"/properties/{world.p204.id}")
        assert p["owner_phone"] is None and p["owner_whatsapp"] is None
        assert all(x["owner_phone"] is None for x in who.ok("get", "/properties")["items"])
    for who in (sup, guard):
        assert all(r["phone"] is None for r in who.ok("get", "/residents")["items"])
        assert who.ok("get", "/residents?q=9000000117")["total"] == 0  # no searching by a hidden number
    assert any(r["phone"] == "9000000117" for r in admin.ok("get", "/residents")["items"])

    residents = sup.ok("get", "/users?role=resident")["items"]
    assert residents and all(u["phone"] is None for u in residents)
    assert sup.ok("get", f"/users/{world.staff.id}")["phone"] == "9000000001"  # colleagues' numbers stay visible
    assert admin.ok("get", f"/users/{world.resident2.id}")["phone"] == "9000000204"


def test_job_call_reaches_plot_owner(as_, world, db):
    world.p204.owner_phone = "+91 99000 11122"
    world.p204.owner_name = "Rahul Owner"
    db.commit()
    admin, sup, staff = as_(world.admin), as_(world.supervisor), as_(world.staff)
    task = sup.ok(
        "post",
        "/maintenance",
        {"title": "Clear weeds", "category": "cleaning", "property_id": str(world.p204.id), "assigned_staff_id": str(world.staff.id)},
    )
    tid = task["id"]
    assert "call_customer" not in staff.ok("get", f"/maintenance/{tid}")["allowed_actions"]
    assert staff.post(f"/maintenance/{tid}/whatsapp-call", {"mode": "video"}).status_code == 403
    assert "call_customer" in admin.ok("get", f"/maintenance/{tid}")["allowed_actions"]
    link = admin.ok("post", f"/maintenance/{tid}/whatsapp-call", {"mode": "video"})
    assert link["url"].startswith("https://wa.me/919900011122?text=")
    assert "Hi Rahul, this is Asha Admin" in unquote(link["url"])

    # No number on record: no button, and a clear error.
    t2 = sup.ok("post", "/maintenance", {"title": "Paint", "category": "painting", "assigned_staff_id": str(world.staff.id)})
    assert "call_customer" not in admin.ok("get", f"/maintenance/{t2['id']}")["allowed_actions"]
    assert admin.post(f"/maintenance/{t2['id']}/whatsapp-call", {"mode": "audio"}).status_code == 409


def test_call_contacts(as_, world, db):
    world.resident.phone = "9845012345"
    db.commit()
    resident, admin = as_(world.resident), as_(world.admin)
    tid = raise_ticket(resident, world)["id"]
    admin.ok("post", f"/tickets/{tid}/assign", {"staff_id": str(world.staff.id)})
    t = db.get(Ticket, uuid.UUID(tid))
    task = db.query(MaintenanceTask).filter_by(ticket_id=t.id).one()
    office, staff = (Actor(user=u, ip=None, user_agent=None) for u in (world.admin, world.staff))
    assert customer_calls.may_call_ticket(office, t) and not customer_calls.may_call_ticket(staff, t)
    assert customer_calls.may_call_task(office, task) and not customer_calls.may_call_task(staff, task)

    # A job raised from a ticket calls the ticket's customer, greeting them by name, never the plot's other owners.
    assert customer_calls.task_contact(db, task) == ("919845012345", "Priya Owner")
    world.resident.phone = None
    world.p117.owner_phone = "9900011122"
    db.commit()
    assert customer_calls.task_contact(db, task) is None

    # A number given on the ticket wins; its WhatsApp number, if any, is the one called.
    t.contact_phone, t.contact_whatsapp = "9811111111", "9822222222"
    db.commit()
    assert customer_calls.ticket_contact(db, t) == ("919822222222", "Priya Owner")

    # The admin can still call once the job is approved, not once it is closed.
    task.status = "approved"
    db.commit()
    assert customer_calls.may_call_task(office, task)
    task.status = "closed"
    assert not customer_calls.may_call_task(office, task)


def test_owner_contact_order_and_fallbacks(world, db):
    p = world.p204
    db.add_all(
        [
            Resident(tenant_id=world.ta.id, property_id=p.id, name="Second Owner", relation="owner", phone="9000000222"),
            Resident(
                tenant_id=world.ta.id,
                property_id=p.id,
                name="Main Owner",
                relation="owner",
                phone="9000000111",
                whatsapp_phone="9000000333",
                is_primary=True,
            ),
        ]
    )
    p.owner_phone = "12"  # unusable: falls through to the next number
    task = MaintenanceTask(tenant_id=world.ta.id, number="GP-MNT-X", title="Weeding", category="cleaning", property_id=p.id)
    db.add(task)
    db.commit()
    assert customer_calls.task_contact(db, task) == ("919000000333", "Main Owner")
    assert "?text=Hi%2C%20this%20is" in customer_calls.call_link("919000000111", "audio", "Ramesh", "   ", "GP-MNT-X", "Weeding")
