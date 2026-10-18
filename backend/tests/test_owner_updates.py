import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models import Inspection, InspectionItem, Invoice, MaintenanceSchedule, Notification, PlotReport, Tenant, User
from app.models.base import utcnow
from app.services import owner_contact, plot_reminders, plot_reports
from app.services import whatsapp as wa
from app.services.reports import IST
from tests.conftest import jpeg_bytes

LINK = re.compile(r"https?://\S+")


@pytest.fixture()
def wa_sent():
    sent = []

    def transport(payload):
        sent.append(payload)
        return {"messages": [{"id": f"wamid.{len(sent)}"}]}

    wa.set_transport(transport)
    yield sent
    wa.set_transport(None)


def opt_in(db, user, in_session=False):
    u = db.get(User, user.id)
    u.phone, u.whatsapp_opt_in = "98450 12345", True
    u.whatsapp_last_inbound_at = utcnow() if in_session else None
    db.commit()


def finish_job(as_, world, property_id=None, before=True):
    sup, staff = as_(world.supervisor), as_(world.staff)
    t = sup.ok(
        "post",
        "/maintenance",
        {
            "title": "Plot clearing",
            "category": "cleaning",
            "property_id": str(property_id or world.p117.id),
            "assigned_staff_id": str(world.staff.id),
            "checklist_items": ["Weeds cleared"],
        },
    )
    tid = t["id"]
    t = staff.ok("post", f"/maintenance/{tid}/start", {})
    if before:
        staff.upload("maintenance_task", tid, jpeg_bytes((120, 90, 40)), "image/jpeg", "before_photo")
    staff.ok("patch", f"/maintenance/{tid}/checklist/{t['checklist'][0]['id']}", {"status": "completed"})
    staff.upload("maintenance_task", tid, jpeg_bytes((40, 160, 60)), "image/jpeg", "after_photo")
    staff.ok("patch", f"/maintenance/{tid}", {"work_notes": "Cleared"})
    staff.ok("post", f"/maintenance/{tid}/complete", {})
    t = sup.ok("post", f"/maintenance/{tid}/approve", {})
    assert t["status"] == "closed"
    return t


def owner_notes(db, user, kind):
    db.expire_all()
    return db.query(Notification).filter(Notification.user_id == user.id, Notification.kind == kind).all()


def test_owner_gets_before_and_after_photos_when_job_closes(as_, world, client, wa_sent):
    opt_in(world.db, world.resident, in_session=True)
    t = finish_job(as_, world)

    [note] = owner_notes(world.db, world.resident, "job_proof")
    assert "Plot GV-117" in note.title and "See the before and after photos: http" in note.body
    assert note.delivery["whatsapp"] == "sent"
    # Inside the 24-hour window the photos themselves go into the chat, after the message
    images = [p for p in wa_sent if p["type"] == "image"]
    assert [i["image"]["caption"] for i in images] == ["Before · plot GV-117", "After · plot GV-117"]

    token = LINK.search(note.body).group(0).rsplit("/proof/", 1)[1]
    r = client.get(f"/api/v1/public/job-proof/{token}")
    assert r.status_code == 200, r.text
    proof = r.json()
    assert proof["number"] == t["number"] and proof["plot"] == "GV-117"
    assert len(proof["before"]) == 1 and len(proof["after"]) == 1
    photo = client.get(proof["after"][0]["url"].replace("http://testserver", ""))
    assert photo.status_code == 200 and photo.content[:2] == b"\xff\xd8"

    tampered = token[:-1] + ("1" if token[-1] == "0" else "0")
    assert client.get(f"/api/v1/public/job-proof/{tampered}").status_code == 404
    other = owner_contact.link_token("plot-report", uuid.UUID(t["id"]), 30)
    assert client.get(f"/api/v1/public/job-proof/{other}").status_code == 404, "tokens are bound to their kind"


def test_proof_outside_whatsapp_window_is_a_link_only(as_, world, wa_sent):
    opt_in(world.db, world.resident)
    finish_job(as_, world, before=False)
    [note] = owner_notes(world.db, world.resident, "job_proof")
    assert "See the photos: http" in note.body
    assert [p["type"] for p in wa_sent] == ["template"]


def test_proof_respects_settings_and_can_be_resent(as_, world):
    t = finish_job(as_, world, property_id=world.p204.id)  # owner via the residents list
    assert len(owner_notes(world.db, world.resident2, "job_proof")) == 1

    tenant = world.db.get(Tenant, world.ta.id)
    tenant.settings = {"resident_evidence_visibility": "none"}
    world.db.commit()
    sup = as_(world.supervisor)
    assert sup.post(f"/maintenance/{t['id']}/send-proof").status_code == 422

    tenant.settings = {}
    world.db.commit()
    r = sup.ok("post", f"/maintenance/{t['id']}/send-proof")
    assert "in_app" in r["channels"] and "/proof/" in r["url"]
    assert len(owner_notes(world.db, world.resident2, "job_proof")) == 2
    assert as_(world.staff).post(f"/maintenance/{t['id']}/send-proof").status_code == 403


def test_plot_due_reminder_with_pay_link_once_per_visit(world, wa_sent):
    db = world.db
    opt_in(db, world.resident)
    today = date(2026, 10, 17)
    due = MaintenanceSchedule(
        tenant_id=world.ta.id,
        title="Monthly plot cleaning",
        category="cleaning",
        property_id=world.p117.id,
        interval_days=30,
        next_run_on=today + timedelta(days=5),
    )
    weekly = MaintenanceSchedule(
        tenant_id=world.ta.id,
        title="Sweep",
        category="cleaning",
        property_id=world.p204.id,
        interval_days=7,
        next_run_on=today + timedelta(days=2),
    )
    later = MaintenanceSchedule(
        tenant_id=world.ta.id,
        title="Gardening",
        category="gardening",
        property_id=world.p117.id,
        interval_days=90,
        next_run_on=today + timedelta(days=20),
    )
    inv = Invoice(
        tenant_id=world.ta.id,
        number="GP-INV-1",
        property_id=world.p117.id,
        description="Cleaning Oct",
        amount=Decimal("1500"),
        amount_paid=Decimal("500"),
        due_date=today,
        status="partial",
    )
    db.add_all([due, weekly, later, inv])
    db.commit()

    assert plot_reminders.remind_plot_due(db, today) == 1
    db.commit()
    [note] = owner_notes(db, world.resident, "plot_due")
    assert note.title == "Plot GV-117 is due for cleaning on 22 Oct"
    assert "₹1000.00 is due. Pay in one tap: http://localhost:3000/billing?invoice=" in note.body
    assert note.delivery["whatsapp"] == "sent"
    assert plot_reminders.remind_plot_due(db, today) == 0, "one reminder per visit"

    # The next visit gets its own reminder; a payment gateway can supply the link
    owner_contact.set_pay_link_builder(lambda _db, i: f"https://rzp.io/l/{i.number}")
    try:
        due.next_run_on = today + timedelta(days=35)
        db.commit()
        assert plot_reminders.remind_plot_due(db, today + timedelta(days=30)) == 1
        db.commit()
        assert "https://rzp.io/l/GP-INV-1" in owner_notes(db, world.resident, "plot_due")[-1].body
    finally:
        owner_contact.set_pay_link_builder(None)

    tenant = db.get(Tenant, world.ta.id)
    tenant.settings = {"plot_due_reminder_days": 0}
    due.next_run_on = today + timedelta(days=65)
    db.commit()
    assert plot_reminders.remind_plot_due(db, today + timedelta(days=60)) == 0


def test_monthly_plot_report(as_, world, client):
    db = world.db
    finish_job(as_, world)
    insp = Inspection(
        tenant_id=world.ta.id,
        number="GP-INS-1",
        property_id=world.p117.id,
        status="completed",
        completed_at=utcnow(),
        overall_condition="attention",
    )
    db.add(insp)
    db.flush()
    db.add(
        InspectionItem(
            tenant_id=world.ta.id, inspection_id=insp.id, point="boundary", condition="issue", notes="Garbage dumped near the gate"
        )
    )
    db.commit()

    admin, owner = as_(world.admin), as_(world.resident)
    today = datetime.now(IST).date()
    month = today.strftime("%Y-%m")
    rep = admin.ok("post", f"/properties/{world.p117.id}/plot-reports", {"month": month})
    s = rep["summary"]
    assert s["visit_count"] == 2 and s["photo_count"] == 2
    assert s["issues"] == [
        {"source": "inspection", "severity": "issue", "text": "Boundary: Garbage dumped near the gate", "date": s["issues"][0]["date"]}
    ]
    assert "in_app" in rep["channels"]

    [listed] = owner.ok("get", f"/properties/{world.p117.id}/plot-reports")
    assert listed["id"] == rep["id"]
    pdf = owner.get(f"/properties/{world.p117.id}/plot-reports/{rep['id']}/report.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert as_(world.resident2).get(f"/properties/{world.p117.id}/plot-reports").status_code == 404
    assert owner.post(f"/properties/{world.p117.id}/plot-reports", {"month": month}).status_code == 403

    [note] = owner_notes(db, world.resident, "plot_report")
    assert "2 visits, 2 photos, 1 issue spotted (Boundary: Garbage dumped near the gate)." in note.body
    url = LINK.search(note.body).group(0)
    public = client.get(url.replace("http://localhost:3000", ""))
    assert public.status_code == 200 and public.content.startswith(b"%PDF")

    # The worker sends last month's report once to every plot with an owner
    first_of_next = plot_reports.add_months(today.replace(day=1), 1)
    unsent = admin.ok("post", f"/properties/{world.p204.id}/plot-reports", {"month": month, "send": False})
    assert unsent["sent_at"] is None
    assert plot_reports.send_monthly(db, first_of_next) == 1  # GV-204's unsent draft; GV-117 was already sent
    db.commit()
    assert plot_reports.send_monthly(db, first_of_next) == 0
    assert {r.property_id for r in db.query(PlotReport)} == {world.p117.id, world.p204.id}
