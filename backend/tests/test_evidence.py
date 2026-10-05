"""Evidence requirements, exceptions and integrity (requirements §10, §13, §41 evidence integrity)."""

import hashlib

from tests.conftest import MP4_BYTES, PDF_BYTES, jpeg_bytes


def started_task(sup, staff, world, category="gate_fence", **extra):
    t = sup.ok(
        "post",
        "/maintenance",
        {
            "title": "Job",
            "category": category,
            "property_id": str(world.p117.id),
            "assigned_staff_id": str(world.staff.id),
            "checklist_items": ["Step one"],
            **extra,
        },
    )
    return staff.ok("post", f"/maintenance/{t['id']}/start", {})


def test_checklist_failed_or_skipped_needs_reason(as_, world):
    sup, staff = as_(world.supervisor), as_(world.staff)
    t = started_task(sup, staff, world)
    item = t["checklist"][0]["id"]
    assert staff.patch(f"/maintenance/{t['id']}/checklist/{item}", {"status": "failed"}).status_code == 422
    assert staff.patch(f"/maintenance/{t['id']}/checklist/{item}", {"status": "skipped", "reason": " "}).status_code == 422
    t = staff.ok("patch", f"/maintenance/{t['id']}/checklist/{item}", {"status": "failed", "reason": "Spare part unavailable"})
    assert t["checklist"][0]["status"] == "failed"


def test_exception_satisfies_requirement_and_is_reviewed(as_, world):
    sup, staff = as_(world.supervisor), as_(world.staff)
    t = started_task(sup, staff, world)  # gate_fence requires before + after photos
    tid = t["id"]
    staff.ok("patch", f"/maintenance/{tid}/checklist/{t['checklist'][0]['id']}", {"status": "completed"})
    staff.upload("maintenance_task", tid, jpeg_bytes(), "image/jpeg", "after_photo")
    staff.ok("patch", f"/maintenance/{tid}", {"work_notes": "Done"})
    r = staff.post(f"/maintenance/{tid}/complete", {})
    assert r.status_code == 422 and r.json()["detail"]["missing"] == ["before_photo"]

    assert (
        staff.post(f"/maintenance/{tid}/exceptions", {"requirement": "before_photo", "reason_code": "other", "reason": "x"}).status_code
        == 422
    )
    t = staff.ok(
        "post",
        f"/maintenance/{tid}/exceptions",
        {"requirement": "before_photo", "reason_code": "camera_unavailable", "reason": "Phone camera failed before starting"},
    )
    assert t["exceptions"][0]["review_status"] == "pending"
    t = staff.ok("post", f"/maintenance/{tid}/complete", {})
    before = next(r for r in t["proof"]["requirements"] if r["key"] == "before_photo")
    assert before["state"] == "excepted"
    t = sup.ok("post", f"/maintenance/{tid}/approve", {})
    assert t["exceptions"][0]["review_status"] == "accepted"
    actions = [a["action"] for a in sup.ok("get", f"/maintenance/{tid}/audit")]
    assert "maintenance.evidence_exception" in actions and "maintenance.exception_accepted" in actions


def test_configurable_policy_gps_video_materials_invoice(as_, world):
    admin, sup, staff = as_(world.admin), as_(world.supervisor), as_(world.staff)
    p = admin.ok("patch", "/maintenance/policies/electrical", {"gps": True, "video": True, "materials": True, "invoice": True})
    assert p["gps"] and p["video"] and p["materials"] and p["invoice"]
    assert sup.patch("/maintenance/policies/electrical", {"gps": False}).status_code == 403
    t = started_task(sup, staff, world, category="electrical")
    tid = t["id"]
    staff.ok("patch", f"/maintenance/{tid}/checklist/{t['checklist'][0]['id']}", {"status": "completed"})
    staff.upload("maintenance_task", tid, jpeg_bytes(), "image/jpeg", "before_photo")
    staff.upload("maintenance_task", tid, jpeg_bytes(), "image/jpeg", "after_photo")
    staff.ok("patch", f"/maintenance/{tid}", {"work_notes": "Replaced MCB"})
    r = staff.post(f"/maintenance/{tid}/complete", {})
    assert set(r.json()["detail"]["missing"]) == {"gps", "video", "materials", "invoice"}
    assert staff.upload("maintenance_task", tid, MP4_BYTES, "video/mp4", "video").status_code == 200
    staff.ok("post", f"/maintenance/{tid}/materials", {"name": "MCB 16A", "quantity": 1, "unit": "pc", "unit_cost": 350})
    staff.upload("maintenance_task", tid, PDF_BYTES, "application/pdf", "receipt")
    t = staff.ok("post", f"/maintenance/{tid}/complete", {"latitude": 12.97, "longitude": 77.59})
    assert t["status"] == "completed"


def test_supervisor_approval_not_required_auto_closes(as_, world):
    admin, sup, staff = as_(world.admin), as_(world.supervisor), as_(world.staff)
    admin.ok("patch", "/maintenance/policies/cleaning", {"supervisor_approval": False})
    t = started_task(sup, staff, world, category="cleaning")
    staff.ok("patch", f"/maintenance/{t['id']}/checklist/{t['checklist'][0]['id']}", {"status": "completed"})
    staff.upload("maintenance_task", t["id"], jpeg_bytes(), "image/jpeg", "after_photo")
    staff.ok("patch", f"/maintenance/{t['id']}", {"work_notes": "Swept"})
    t = staff.ok("post", f"/maintenance/{t['id']}/complete", {})
    assert t["status"] == "closed" and t["review_decision"] == "approved" and t["reviewed_by"] is None


def test_upload_integrity_checks(as_, world):
    sup, staff = as_(world.supervisor), as_(world.staff)
    t = started_task(sup, staff, world)
    tid = t["id"]
    img = jpeg_bytes()
    # checksum mismatch → FAILED, recorded in audit
    r = staff.upload("maintenance_task", tid, img, "image/jpeg", "before_photo", sha="0" * 64)
    assert r.status_code == 422 and "Checksum" in r.text
    # declared type does not match content
    r = staff.upload("maintenance_task", tid, PDF_BYTES, "image/jpeg", "before_photo")
    assert r.status_code == 415
    # unsupported type
    r = staff.post(
        "/media/upload-url",
        {
            "entity_type": "maintenance_task",
            "entity_id": tid,
            "content_type": "application/x-msdownload",
            "size_bytes": 10,
            "evidence_type": "document",
        },
    )
    assert r.status_code == 415
    # too large
    r = staff.post(
        "/media/upload-url",
        {
            "entity_type": "maintenance_task",
            "entity_id": tid,
            "content_type": "image/jpeg",
            "size_bytes": 10**9,
            "evidence_type": "before_photo",
        },
    )
    assert r.status_code == 413
    # malware (EICAR) rejected
    eicar = b"%PDF-1.4\nX5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    r = staff.upload("maintenance_task", tid, eicar, "application/pdf", "invoice")
    assert r.status_code == 422 and "malware" in r.text
    # good upload: hash matches, thumbnail generated, original preserved byte-for-byte
    r = staff.upload("maintenance_task", tid, img, "image/jpeg", "before_photo")
    m = r.json()
    assert m["sha256"] == hashlib.sha256(img).hexdigest() and m["thumbnail_url"]
    blob = staff.c.get(m["url"].replace("http://testserver", ""))
    assert blob.status_code == 200 and blob.content == img
    # tampered/expired signed URL is refused
    tampered = m["url"].replace("http://testserver", "")[:-4] + "beef"
    assert staff.c.get(tampered).status_code == 403


def test_replacement_and_deletion_are_audited(as_, world):
    sup, staff = as_(world.supervisor), as_(world.staff)
    t = started_task(sup, staff, world)
    tid = t["id"]
    first = staff.upload("maintenance_task", tid, jpeg_bytes((1, 2, 3)), "image/jpeg", "before_photo").json()
    second = staff.upload(
        "maintenance_task", tid, jpeg_bytes((200, 2, 3)), "image/jpeg", "before_photo", replaces_media_id=first["id"]
    ).json()
    t = staff.ok("get", f"/maintenance/{tid}")
    befores = [e for e in t["evidence"] if e["evidence_type"] == "before_photo"]
    assert [e["media_id"] for e in befores] == [second["id"]], "replaced evidence is no longer active"
    old = sup.ok("get", f"/media/{first['id']}")
    assert old["replaced_by_id"] == second["id"]
    assert staff.delete(f"/media/{second['id']}", {"reason": "blurred"}).json()["status"] == "deleted"
    actions = [a["action"] for a in as_(world.admin).ok("get", "/audit", params={"entity_id": tid})["items"]]
    assert "media.replaced" in actions and "media.deleted" in actions
    # deleted file is hidden from workers but visible to managers with its hash
    assert staff.get(f"/media/{second['id']}").status_code == 404
    assert sup.ok("get", f"/media/{second['id']}")["sha256"]


def test_evidence_only_in_working_states(as_, world):
    sup, staff = as_(world.supervisor), as_(world.staff)
    t = sup.ok("post", "/maintenance", {"title": "Paint wall", "category": "painting", "assigned_staff_id": str(world.staff.id)})
    r = staff.upload("maintenance_task", t["id"], jpeg_bytes(), "image/jpeg", "before_photo")
    assert r.status_code == 409, "must accept the task before capturing evidence"
    other = as_(world.staff2)
    assert other.upload("maintenance_task", t["id"], jpeg_bytes(), "image/jpeg", "before_photo").status_code == 404
    # notes cannot be written before start
    assert staff.patch(f"/maintenance/{t['id']}", {"work_notes": "x"}).status_code == 409
