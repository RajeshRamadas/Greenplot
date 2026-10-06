"""Same app for customers and vendors; the layout admin switches features per role."""

from app.models import AuditLog


def test_defaults_give_each_role_its_full_view(as_, world):
    me = as_(world.resident).ok("get", "/auth/me")
    assert {"tickets", "billing", "visitors", "sos"} <= set(me["features"]) and "billing.read" in me["permissions"]
    vme = as_(world.vendor_user).ok("get", "/auth/me")
    assert set(vme["features"]) == {"tickets", "jobs", "scan", "proof_reports", "offline", "records"}
    assert as_(world.admin).ok("get", "/auth/me")["features"] is None  # office roles aren't switchable


def test_admin_switches_off_resident_features(as_, world, db):
    admin, resident, resident2 = as_(world.admin), as_(world.resident), as_(world.resident2)
    view = admin.ok("put", "/settings/features", {"role": "resident", "features": {"billing": False, "visitors": False}})
    assert {f["key"]: f["enabled"] for f in view["resident"]}["billing"] is False

    me = resident.ok("get", "/auth/me")
    assert "billing" not in me["features"] and "billing.read" not in me["permissions"] and "visitors.read" not in me["permissions"]
    assert resident.get("/billing/invoices").status_code == 403  # refused by the API, not just hidden
    assert resident2.get("/billing/invoices").status_code == 403
    assert resident.get("/tickets").status_code == 200  # everything else still works
    assert admin.get("/billing/invoices").status_code == 200  # office unaffected
    assert as_(world.admin_b).get("/billing/invoices").status_code == 200  # other layouts unaffected
    assert db.query(AuditLog).filter_by(action="settings.features_changed").count() == 1

    admin.ok("put", "/settings/features", {"role": "resident", "features": {"billing": True}})
    assert resident.get("/billing/invoices").status_code == 200


def test_vendor_features_and_dependencies(as_, world):
    admin, vendor, staff = as_(world.admin), as_(world.vendor_user), as_(world.staff)
    r = admin.put("/settings/features", json={"role": "vendor", "features": {"jobs": False}})
    assert r.status_code == 422 and "needs Work orders" in r.json()["detail"]
    admin.ok("put", "/settings/features", {"role": "vendor", "features": {"scan": False, "offline": False}})
    assert vendor.get("/maintenance/scan/ANY").status_code == 403
    assert vendor.post("/sync", json={"operations": []}).status_code == 403
    assert staff.get("/maintenance/scan/ANY").status_code == 404  # staff keep scanning (no such asset)
    admin.ok("put", "/settings/features", {"role": "vendor", "features": {"tickets": False, "jobs": False}})
    assert vendor.get("/tickets").status_code == 403


def test_only_admins_change_features_and_input_is_checked(as_, world):
    assert as_(world.supervisor).put("/settings/features", json={"role": "resident", "features": {"sos": False}}).status_code == 403
    admin = as_(world.admin)
    assert admin.put("/settings/features", json={"role": "guard", "features": {}}).status_code == 422
    assert admin.put("/settings/features", json={"role": "resident", "features": {"teleport": False}}).status_code == 422
