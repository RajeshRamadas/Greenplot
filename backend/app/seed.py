"""Demo data: `python -m app.seed` creates Green Valley Layout with one login per role.

Every record is synthetic (requirements §32: public/demo surfaces never show real tenant data).
All demo accounts use the password printed at the end.
"""

import io
import random
import sys
from datetime import date, timedelta

from PIL import Image, ImageDraw
from sqlalchemy import select

from app.core.db import Base, SessionLocal, engine
from app.core.deps import Actor
from app.core.security import hash_password
from app.models import (
    Asset,
    BillingPlan,
    ChecklistTemplate,
    Layout,
    MaintenanceSchedule,
    Notice,
    PatrolCheckpoint,
    PatrolRoute,
    Property,
    Resident,
    StaffProfile,
    Tenant,
    User,
    Vehicle,
    Vendor,
)
from app.models.base import utcnow
from app.models.enums import Role
from app.services import billing, media, security_ops
from app.services import maintenance as m
from app.services.maintenance import ensure_default_policies

DEMO_PASSWORD = "GreenPlot@2026"


def scene(kind: str) -> bytes:
    """A simple synthetic before/after illustration (no real photos in demo data)."""
    w, h = 640, 480
    img = Image.new("RGB", (w, h), (196, 220, 206) if kind == "after" else (186, 176, 150))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 300, w, h], fill=(110, 160, 120) if kind == "after" else (140, 120, 90))
    d.rectangle([180, 140, 460, 330], outline=(60, 70, 70), width=10)
    for x in range(200, 460, 40):
        d.line([x, 150, x, 320], fill=(70, 80, 80), width=6)
    if kind == "before":
        for _ in range(40):
            x, y = random.randint(0, w), random.randint(300, h)
            d.ellipse([x, y, x + 18, y + 10], fill=(90, 110, 60))
        d.line([180, 140, 470, 170], fill=(150, 60, 50), width=8)
    d.text((16, 16), f"GreenPlot demo · {kind.upper()}", fill=(20, 40, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return buf.getvalue()


def attach(db, actor, task, kind, evidence_type):
    from app.schemas.maintenance import UploadUrlIn
    from app.services.storage import get_storage

    data = scene(kind)
    req = UploadUrlIn(
        entity_type="maintenance_task",
        entity_id=task.id,
        content_type="image/jpeg",
        size_bytes=len(data),
        evidence_type=evidence_type,
        filename=f"{kind}.jpg",
        latitude=12.9141,
        longitude=77.6387,
        captured_at=utcnow(),
    )
    row, _ = media.create_upload(db, actor, req)
    get_storage().put(row.storage_key, data, "image/jpeg")
    media.finalize(db, actor, row)


def run(reset: bool = False) -> None:
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    if db.scalar(select(Tenant).where(Tenant.slug == "green-valley")):
        print("Demo tenant already exists. Use --reset to recreate.")
        return
    random.seed(7)
    pw = hash_password(DEMO_PASSWORD)

    def user(tenant, email, role, name, phone=None, **kw):
        u = User(tenant_id=tenant.id if tenant else None, email=email, full_name=name, role=role, password_hash=pw, phone=phone, **kw)
        db.add(u)
        db.flush()
        if tenant and role in (Role.STAFF, Role.GUARD, Role.SUPERVISOR):
            db.add(
                StaffProfile(
                    tenant_id=tenant.id, user_id=u.id, designation=role.title(), shift_name="Day", shift_start="08:00", shift_end="17:00"
                )
            )
        return u

    user(None, "platform@greenplot.in", Role.SUPER_ADMIN, "Platform Admin")
    t = Tenant(
        name="Green Valley Layout",
        slug="green-valley",
        city="Bangalore",
        contact_email="association@greenvalley.example",
        settings={"auto_close_on_approval": True, "resident_evidence_visibility": "after_approval"},
    )
    db.add(t)
    db.flush()
    ensure_default_policies(db, t.id)
    layout = Layout(tenant_id=t.id, name="Green Valley Layout", address="Sarjapur Road, Bangalore", latitude=12.9141, longitude=77.6387)
    db.add(layout)
    db.flush()

    admin = user(t, "admin@greenvalley.example", Role.LAYOUT_ADMIN, "Asha Rao", "9000000010")
    sup = user(t, "supervisor@greenvalley.example", Role.SUPERVISOR, "Anita Menon", "9000000011")
    staff = user(t, "staff@greenvalley.example", Role.STAFF, "Ramesh Kumar", "9000000012")
    staff2 = user(t, "gardener@greenvalley.example", Role.STAFF, "Lakshmi Devi", "9000000013")
    guard = user(t, "guard@greenvalley.example", Role.GUARD, "Gopal Singh", "9000000014")
    v_gate = Vendor(
        tenant_id=t.id,
        name="FixIt Gates & Fabrication",
        contact_person="Vikram",
        phone="9000000020",
        service_categories=["gate_fence", "civil"],
    )
    v_elec = Vendor(
        tenant_id=t.id, name="BrightSpark Electricals", contact_person="Imran", phone="9000000021", service_categories=["electrical"]
    )
    db.add_all([v_gate, v_elec])
    db.flush()
    vendor_user = user(t, "vendor@greenvalley.example", Role.VENDOR, "Vikram Shetty", "9000000022", vendor_id=v_gate.id)
    resident = user(t, "resident@greenvalley.example", Role.RESIDENT, "Priya Nair", "9000000030")

    props = {}
    for i, plot in enumerate(["101", "102", "103", "104", "105", "117", "204", "221", "89"] + [str(300 + n) for n in range(15)]):
        p = Property(
            tenant_id=t.id,
            layout_id=layout.id,
            code=f"GV-{plot}",
            plot_number=plot,
            block="A" if i % 2 == 0 else "B",
            area_sqft=random.choice([1200, 1500, 2400, 4000]),
            status=random.choice(["vacant_plot", "occupied", "under_construction"]),
            owner_name=f"Owner {plot}",
            owner_phone=f"98{random.randint(10000000, 99999999)}",
            latitude=12.9141 + i * 0.0003,
            longitude=77.6387 + i * 0.0002,
        )
        db.add(p)
        props[plot] = p
    db.flush()
    p117 = props["117"]
    p117.owner_user_id, p117.owner_name, p117.status = resident.id, resident.full_name, "vacant_plot"
    props["103"].condition = "attention"
    props["89"].condition = "issue"
    db.add(
        Resident(
            tenant_id=t.id,
            property_id=p117.id,
            user_id=resident.id,
            name=resident.full_name,
            phone=resident.phone,
            email=resident.email,
            relation="owner",
            is_primary=True,
            in_directory=True,
        )
    )
    db.add(Vehicle(tenant_id=t.id, number="KA05MN4521", property_id=p117.id, owner_name=resident.full_name, vehicle_type="car"))

    gate = Asset(
        tenant_id=t.id,
        code="GATE-MAIN",
        qr_code="GP-AST-GATE-MAIN",
        name="Main Entrance Gate",
        category="gate",
        layout_id=layout.id,
        location="Layout entrance",
        vendor_id=v_gate.id,
        installed_on=date(2023, 4, 1),
        service_interval_days=90,
    )
    pump = Asset(
        tenant_id=t.id,
        code="PUMP-01",
        qr_code="GP-AST-PUMP-01",
        name="Borewell Pump 1",
        category="pump",
        layout_id=layout.id,
        location="Pump house, Block A",
        installed_on=date(2022, 11, 15),
        warranty_until=date(2027, 11, 15),
        service_interval_days=30,
        next_service_due=date.today() - timedelta(days=2),
    )
    light = Asset(
        tenant_id=t.id,
        code="SL-A12",
        qr_code="GP-AST-SL-A12",
        name="Streetlight A-12",
        category="streetlight",
        layout_id=layout.id,
        location="Road 2, near Plot 117",
        vendor_id=v_elec.id,
    )
    db.add_all([gate, pump, light])
    db.flush()

    A = Actor(admin, None, "seed")
    S = Actor(sup, None, "seed")
    W = Actor(staff, None, "seed")

    # 1. The §11 example: gate hinge job, fully proven and approved.
    task = m.create_task(
        db,
        S,
        t.id,
        dict(
            title="Gate hinge lubrication and alignment",
            category="gate_fence",
            priority="high",
            asset_id=gate.id,
            layout_id=layout.id,
            location_note="Main Entrance Gate",
            assigned_staff_id=staff.id,
            supervisor_id=sup.id,
            due_at=utcnow() + timedelta(days=1),
        ),
    )
    m.accept(db, W, task)
    m.record_asset_scan(db, W, task, gate.qr_code, "qr")
    attach(db, W, task, "before", "before_photo")
    m.start(db, W, task, 12.9141, 77.6387, 6)
    for item in task.checklist:
        m.update_checklist_item(db, W, task, item, "completed", None)
    from app.models import MaintenanceMaterial

    db.add(
        MaintenanceMaterial(
            tenant_id=t.id,
            task_id=task.id,
            name="Lithium grease",
            quantity=0.25,
            unit="kg",
            unit_cost=480,
            supplier="Local hardware",
            added_by=staff.id,
        )
    )
    attach(db, W, task, "after", "after_photo")
    task.work_notes = "Cleaned and greased both hinges, re-aligned the right leaf by 6 mm, tightened latch bolts."
    task.issue_found, task.outcome = "Dry hinges; right leaf sagging", "Gate opens and closes smoothly"
    db.flush()
    m.complete(db, W, task, 12.9141, 77.6387, 6)
    m.approve(db, S, task, "Verified on site — gate closes smoothly.")

    # 2. A cleaning job awaiting approval
    clean = m.create_task(
        db, S, t.id, dict(title="Plot cleaning and weed removal", category="cleaning", property_id=p117.id, assigned_staff_id=staff.id)
    )
    m.start(db, W, clean)
    for item in clean.checklist:
        m.update_checklist_item(db, W, clean, item, "completed", None)
    attach(db, W, clean, "after", "after_photo")
    clean.work_notes = "Cleared weeds and debris along all four boundaries."
    db.flush()
    m.complete(db, W, clean)

    # 3. Open work in various states
    m.create_task(
        db,
        S,
        t.id,
        dict(
            title="Repair sagging fence on west boundary",
            category="gate_fence",
            property_id=props["89"].id,
            vendor_id=v_gate.id,
            priority="high",
            due_at=utcnow() + timedelta(days=2),
        ),
    )
    m.create_task(
        db,
        S,
        t.id,
        dict(
            title="Monthly pump servicing",
            category="asset_servicing",
            asset_id=pump.id,
            assigned_staff_id=staff.id,
            due_at=utcnow() - timedelta(hours=6),
        ),
    )
    m.create_task(
        db,
        S,
        t.id,
        dict(
            title="Hedge trimming and lawn mowing — Park A",
            category="gardening",
            assigned_staff_id=staff2.id,
            location_note="Park A",
            due_at=utcnow() + timedelta(days=1),
        ),
    )
    m.create_task(db, S, t.id, dict(title="Replace streetlight A-12 driver", category="electrical", asset_id=light.id, vendor_id=v_elec.id))

    # Complaint linked to maintenance (the §49 example)
    from app.models import Complaint
    from app.services.numbering import next_number

    comp = Complaint(
        tenant_id=t.id,
        number=next_number(db, t.id, "CMP"),
        property_id=p117.id,
        category="streetlight",
        priority="medium",
        title="Streetlight near my plot flickers at night",
        raised_by=resident.id,
    )
    db.add(comp)
    db.flush()

    # Recurring schedules (§14-15)
    tpl = db.scalar(select(ChecklistTemplate).where(ChecklistTemplate.tenant_id == t.id, ChecklistTemplate.category == "gardening"))
    db.add(
        MaintenanceSchedule(
            tenant_id=t.id,
            title="Weekly common-area gardening",
            category="gardening",
            interval_days=7,
            next_run_on=date.today() + timedelta(days=2),
            assigned_staff_id=staff2.id,
            location_note="Parks A & B",
            checklist_template_id=tpl.id if tpl else None,
        )
    )
    db.add(
        MaintenanceSchedule(
            tenant_id=t.id,
            title="Fortnightly drain cleaning",
            category="compound_maintenance",
            interval_days=14,
            next_run_on=date.today() + timedelta(days=5),
            assigned_staff_id=staff.id,
        )
    )

    # Property Watch inspection for the absentee owner
    from app.models import Inspection, InspectionItem
    from app.models.enums import INSPECTION_POINTS

    ins = Inspection(
        tenant_id=t.id,
        number=next_number(db, t.id, "INS"),
        property_id=p117.id,
        inspector_id=sup.id,
        is_property_watch=True,
        status="completed",
        started_at=utcnow() - timedelta(days=2, hours=1),
        completed_at=utcnow() - timedelta(days=2),
        overall_condition="attention",
        findings="Plot is clean and secure. Streetlight on Road 2 needs attention.",
    )
    for i, pt in enumerate(INSPECTION_POINTS):
        ins.items.append(
            InspectionItem(
                tenant_id=t.id,
                position=i,
                point=pt,
                condition="attention" if pt == "streetlights" else "good",
                notes="Flickering at night" if pt == "streetlights" else None,
            )
        )
    db.add(ins)
    p117.condition = "attention"

    # Security: visitors, patrol route, incident
    G = Actor(guard, None, "seed")
    security_ops.register_visitor(
        db, G, {"name": "Courier — BlueDart", "phone": "9000000099", "purpose": "Parcel delivery", "vehicle_number": "KA01AB1234"}
    )
    route = PatrolRoute(tenant_id=t.id, name="Night perimeter round")
    db.add(route)
    db.flush()
    for i, (name, code) in enumerate(
        [("Main gate", "GP-CP-GATE"), ("Park A", "GP-CP-PARKA"), ("Pump house", "GP-CP-PUMP"), ("Back gate", "GP-CP-BACK")]
    ):
        db.add(PatrolCheckpoint(tenant_id=t.id, route_id=route.id, name=name, position=i, qr_code=code))
    security_ops.create_incident(
        db, G, {"title": "Stray cattle entered Block B", "category": "trespass", "severity": "low", "location": "Block B, Road 4"}
    )

    # Billing
    plan = BillingPlan(tenant_id=t.id, name="Quarterly maintenance", basis="per_sqft", rate=2, frequency_months=3, due_days=15)
    db.add(plan)
    db.flush()
    first_of_month = date.today().replace(day=1)
    billing.generate_invoices(db, A, plan, first_of_month)

    db.add(
        Notice(
            tenant_id=t.id,
            kind="outage",
            title="Water supply interruption on Sunday",
            body="Overhead tank cleaning from 10:00 to 14:00.",
            audience="all",
            published_by=admin.id,
            published_at=utcnow(),
            pinned=True,
        )
    )
    db.add(
        Notice(
            tenant_id=t.id,
            kind="event",
            title="Tree plantation drive",
            body="Join us in Park A this Saturday at 7:30 AM.",
            audience="residents",
            published_by=admin.id,
            published_at=utcnow(),
        )
    )
    db.commit()
    print(f"Seeded Green Valley Layout. Demo logins (password: {DEMO_PASSWORD}):")
    for email in [
        "platform@greenplot.in",
        admin.email,
        sup.email,
        staff.email,
        staff2.email,
        guard.email,
        vendor_user.email,
        resident.email,
    ]:
        print("  ", email)


if __name__ == "__main__":
    run(reset="--reset" in sys.argv)
