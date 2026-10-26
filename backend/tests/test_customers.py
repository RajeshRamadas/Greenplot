"""The customer record: plots, history, conversations and photos in one place, for layout admins only."""

import json
import uuid

from app.models import Media, Property, WhatsAppMessage
from tests.conftest import jpeg_bytes
from tests.test_tickets import raise_ticket


def test_customer_record_is_admin_only(as_, world):
    world.resident.phone = "98450 12345"
    world.db.commit()
    admin = as_(world.admin)
    c = admin.ok("get", f"/customers/{world.resident.id}")
    assert c["full_name"] == "Priya Owner" and c["phone"] == "98450 12345"
    assert [p["code"] for p in c["plots"]] == ["GV-117"] and c["plots"][0]["relation"] == "owner"

    for who in (world.supervisor, world.staff, world.guard, world.vendor_user, world.resident):
        api = as_(who)
        assert api.get(f"/customers/{world.resident.id}").status_code == 403
        assert api.get("/customers").status_code == 403
        assert api.post(f"/customers/{world.resident.id}/interactions", {"summary": "hi"}).status_code == 403
    # Another layout's admin cannot see the customer, and staff are not customers.
    assert as_(world.admin_b).get(f"/customers/{world.resident.id}").status_code == 404
    assert admin.get(f"/customers/{world.staff.id}").status_code == 404


def test_list_and_search_customers(as_, world):
    admin = as_(world.admin)
    page = admin.ok("get", "/customers")
    assert {c["full_name"] for c in page["items"]} == {"Priya Owner", "Rahul Owner"}
    assert admin.ok("get", "/customers", params={"q": "204"})["items"][0]["full_name"] == "Rahul Owner"
    found = admin.ok("get", "/customers", params={"q": "GV-117"})["items"]
    assert [(c["full_name"], c["plots"]) for c in found] == [("Priya Owner", ["Plot 117"])]


def test_conversations_and_history(as_, world, db):
    world.resident.phone = "98450 12345"
    db.commit()
    admin, resident = as_(world.admin), as_(world.resident)
    t = raise_ticket(resident, world)
    resident.ok("post", f"/tickets/{t['id']}/comments", {"message": "Please come after 5"})
    admin.ok("post", f"/tickets/{t['id']}/comments", {"message": "Check the hinge first", "visibility": "internal"})
    db.add(
        WhatsAppMessage(tenant_id=world.ta.id, user_id=world.resident.id, direction="in", phone="919845012345", body="Is the gate fixed?")
    )
    db.commit()

    call = admin.ok(
        "post",
        f"/customers/{world.resident.id}/interactions",
        {
            "kind": "phone_call",
            "direction": "in",
            "summary": "Asked about the AMC plan",
            "outcome": "Will decide next week",
            "property_id": str(world.p117.id),
        },
    )
    assert call["author_name"] == "Asha Admin" and call["property_id"] == str(world.p117.id)
    # A plot that isn't theirs is refused.
    bad = admin.post(f"/customers/{world.resident.id}/interactions", {"summary": "x", "property_id": str(world.p204.id)})
    assert bad.status_code == 422

    # WhatsApp calls from a ticket land on the record by themselves.
    admin.ok("post", f"/tickets/{t['id']}/whatsapp-call", {"mode": "video"})
    convo = admin.ok("get", f"/customers/{world.resident.id}/interactions")
    assert [i["kind"] for i in convo] == ["whatsapp_call", "phone_call"]
    assert convo[0]["ticket_id"] == t["id"] and "Video call" in convo[0]["summary"]

    history = admin.ok("get", f"/customers/{world.resident.id}/history")
    kinds = {e["kind"] for e in history}
    assert {"account", "ticket", "ticket_message", "whatsapp", "phone_call", "whatsapp_call"} <= kinds
    internal = [e for e in history if e["kind"] == "ticket_message" and e["body"] == "Check the hinge first"]
    assert internal and internal[0]["internal"] and internal[0]["direction"] == "out"
    mine = [e for e in history if e["body"] == "Please come after 5"][0]
    assert mine["direction"] == "in" and not mine["internal"]
    calls = admin.ok("get", f"/customers/{world.resident.id}/history", params={"kind": "phone_call"})
    assert calls and all(e["kind"] == "phone_call" for e in calls)
    # The customer list shows the latest conversation too.
    listed = admin.ok("get", "/customers", params={"q": "Priya"})["items"][0]
    assert listed["last_contact_at"] is not None and listed["open_tickets"] == 1

    # A ticket can only be linked to its own customer's conversations.
    other = raise_ticket(as_(world.resident2), world, property_id=str(world.p204.id))
    bad = admin.post(f"/customers/{world.resident.id}/interactions", {"summary": "x", "ticket_id": other["id"]})
    assert bad.status_code == 422

    c = admin.ok("get", f"/customers/{world.resident.id}")
    assert c["stats"]["tickets"] == 1 and c["stats"]["open_tickets"] == 1 and c["stats"]["conversations"] == 2
    assert c["stats"]["last_contact_at"] is not None

    # Edit and delete a note; both are audited and the note leaves the record.
    admin.ok("patch", f"/customer-interactions/{call['id']}", {"outcome": "Signed up for Standard"})
    assert admin.ok("get", f"/customers/{world.resident.id}/interactions")[1]["outcome"] == "Signed up for Standard"
    admin.ok("delete", f"/customer-interactions/{call['id']}", status=204)
    assert len(admin.ok("get", f"/customers/{world.resident.id}/interactions")) == 1
    assert as_(world.admin_b).delete(f"/customer-interactions/{call['id']}").status_code == 404


def test_notes_for_an_owner_without_a_login(as_, world, db):
    plot = Property(
        tenant_id=world.ta.id, layout_id=world.layout.id, code="GV-301", plot_number="301", owner_name="Kiran", owner_phone="9900011122"
    )
    db.add(plot)
    db.commit()
    admin = as_(world.admin)
    admin.ok("post", f"/properties/{plot.id}/interactions", {"kind": "site_visit", "summary": "Met Kiran at the plot, wants fencing"})
    rows = admin.ok("get", f"/properties/{plot.id}/interactions")
    assert len(rows) == 1 and rows[0]["customer_id"] is None and rows[0]["kind"] == "site_visit"
    assert as_(world.supervisor).get(f"/properties/{plot.id}/interactions").status_code == 403

    # A plot page shows its own notes and the owner's general ones, not notes about their other plots.
    admin.ok("post", f"/customers/{world.resident2.id}/interactions", {"summary": "About plot 204", "property_id": str(world.p204.id)})
    admin.ok("post", f"/customers/{world.resident2.id}/interactions", {"summary": "General chat"})
    plot.owner_user_id = world.resident2.id
    db.commit()
    assert {i["summary"] for i in admin.ok("get", f"/properties/{plot.id}/interactions")} == {
        "Met Kiran at the plot, wants fencing",
        "General chat",
    }

    # Once the owner has an account, the plot's notes show on their record too.
    assert "Met Kiran at the plot, wants fencing" in [
        i["summary"] for i in admin.ok("get", f"/customers/{world.resident2.id}/interactions")
    ]


def test_photos_from_every_record_and_customer_files(as_, world, db):
    admin, resident = as_(world.admin), as_(world.resident)
    t = raise_ticket(resident, world)
    r = resident.upload("ticket", t["id"], jpeg_bytes(), "image/jpeg", "photo", filename="gate.jpg")
    assert r.status_code == 200, r.text
    r = admin.upload("customer", world.resident.id, jpeg_bytes((10, 200, 10)), "image/jpeg", "document", filename="agreement.jpg")
    assert r.status_code == 200, r.text
    customer_file = r.json()
    # Files on the customer's own record never expire.
    assert customer_file["retention_until"] is None
    assert db.get(Media, uuid.UUID(customer_file["id"])).retention_until is None

    files = admin.ok("get", f"/customers/{world.resident.id}/media")
    assert {f["source"] for f in files} == {"Customer file", f"Ticket {t['number']}"}
    assert all(f["url"] for f in files)
    assert admin.ok("get", f"/customers/{world.resident.id}")["stats"]["photos"] == 2

    # Only admins can open or add to the customer file, even through the media endpoints.
    assert as_(world.supervisor).upload("customer", world.resident.id, jpeg_bytes(), "image/jpeg", "document").status_code == 404
    assert resident.get("/media", params={"entity_type": "customer", "entity_id": str(world.resident.id)}).status_code == 404
    assert len(admin.ok("get", "/media", params={"entity_type": "customer", "entity_id": str(world.resident.id)})) == 1

    # Photos of a deleted ticket leave the record with it.
    from app.models import Ticket
    from app.models.base import utcnow

    db.get(Ticket, uuid.UUID(t["id"])).deleted_at = utcnow()
    db.commit()
    assert [f["source"] for f in admin.ok("get", f"/customers/{world.resident.id}/media")] == ["Customer file"]


def test_export_everything(as_, world):
    admin = as_(world.admin)
    raise_ticket(as_(world.resident), world)
    admin.ok("post", f"/customers/{world.resident.id}/interactions", {"summary": "Welcome call"})
    r = admin.get(f"/customers/{world.resident.id}/export")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = json.loads(r.content)
    assert data["customer"]["full_name"] == "Priya Owner"
    assert data["conversations"][0]["summary"] == "Welcome call"
    assert any(e["kind"] == "ticket" for e in data["history"])

    # Names outside Latin-1 still download, with an ASCII fallback file name.
    world.resident.full_name = "ಪ್ರಿಯಾ Nair"
    world.db.commit()
    r = admin.get(f"/customers/{world.resident.id}/export")
    assert r.status_code == 200
    assert 'filename="greenplot-nair.json"' in r.headers["content-disposition"] and "filename*=UTF-8''" in r.headers["content-disposition"]
