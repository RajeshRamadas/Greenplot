"""Authentication, RBAC and tenant isolation (requirements §24-25, §37, §41 security)."""

from tests.conftest import PASSWORD, Api, jpeg_bytes


def test_login_refresh_logout(client, world):
    r = client.post("/api/v1/auth/login", json={"email": world.admin.email, "password": "nope"})
    assert r.status_code == 401
    api = Api(client, world.admin.email)
    me = api.ok("get", "/auth/me")
    assert me["role"] == "layout_admin" and "maintenance.configure" in me["permissions"] and me["tenant_name"] == "Green Valley Layout"
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": api.refresh})
    assert r.status_code == 200
    # refresh tokens rotate: the old one is now spent
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": api.refresh}).status_code == 401
    # device loss: logout-all revokes outstanding access tokens
    api.ok("post", "/auth/logout-all")
    assert api.get("/auth/me").status_code == 401


def test_login_rate_limit(client, world, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "login_rate_per_minute", 3)
    codes = [client.post("/api/v1/auth/login", json={"email": world.staff.email, "password": "bad"}).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[-1] == 429


def test_invite_and_accept(as_, client, world):
    admin = as_(world.admin)
    out = admin.ok(
        "post",
        "/residents",
        {"property_id": str(world.p117.id), "name": "New Tenant", "email": "tenant@gv.in", "relation": "tenant", "invite": True},
    )
    token = out["invite_token"]
    assert token and "accept-invite" in out["invite_url"]
    assert client.post("/api/v1/auth/accept-invite", json={"token": token, "password": "short"}).status_code == 422
    r = client.post("/api/v1/auth/accept-invite", json={"token": token, "password": "Str0ngPass!"})
    assert r.status_code == 200
    api = Api.__new__(Api)
    api.c, api.h = client, {"Authorization": f"Bearer {r.json()['access_token']}"}
    props = api.ok("get", "/properties")["items"]
    assert [p["code"] for p in props] == ["GV-117"]
    assert client.post("/api/v1/auth/accept-invite", json={"token": token, "password": "Str0ngPass!"}).status_code == 400


def test_cross_tenant_access_is_prevented(as_, world):
    a, b = as_(world.admin), as_(world.admin_b)
    t = as_(world.supervisor).ok("post", "/maintenance", {"title": "A task", "category": "civil", "property_id": str(world.p117.id)})
    assert b.get(f"/maintenance/{t['id']}").status_code == 404
    assert b.get(f"/properties/{world.p117.id}").status_code == 404
    assert b.patch(f"/properties/{world.p117.id}", {"notes": "x"}).status_code == 404
    assert b.post(f"/maintenance/{t['id']}/assign", {"assigned_staff_id": str(world.staff.id)}).status_code == 404
    assert t["id"] not in [x["id"] for x in b.ok("get", "/maintenance")["items"]]
    assert b.ok("get", "/records/search", params={"q": "A task"})["total"] == 0
    # B cannot assign A's staff to its own work
    bt = b.ok("post", "/maintenance", {"title": "B task", "category": "civil"})
    assert b.post(f"/maintenance/{bt['id']}/assign", {"assigned_staff_id": str(world.staff.id)}).status_code == 422
    # Media of tenant A is invisible to tenant B even with the id
    staff = as_(world.staff)
    t2 = as_(world.supervisor).ok(
        "post", "/maintenance", {"title": "Photo job", "category": "cleaning", "assigned_staff_id": str(world.staff.id)}
    )
    staff.ok("post", f"/maintenance/{t2['id']}/accept")
    m = staff.upload("maintenance_task", t2["id"], jpeg_bytes(), "image/jpeg", "before_photo").json()
    assert b.get(f"/media/{m['id']}").status_code == 404
    assert b.ok("get", "/audit")["total"] >= 0 and all(x["tenant_id"] == str(world.tb.id) for x in b.ok("get", "/audit")["items"])
    assert a.ok("get", "/audit")["total"] > 0


def test_role_scoping(as_, world):
    sup = as_(world.supervisor)
    t117 = sup.ok(
        "post",
        "/maintenance",
        {"title": "117 job", "category": "civil", "property_id": str(world.p117.id), "assigned_staff_id": str(world.staff.id)},
    )
    t204 = sup.ok(
        "post",
        "/maintenance",
        {"title": "204 job", "category": "civil", "property_id": str(world.p204.id), "assigned_staff_id": str(world.staff2.id)},
    )
    resident, resident2 = as_(world.resident), as_(world.resident2)
    assert [x["id"] for x in resident.ok("get", "/maintenance")["items"]] == [t117["id"]]
    assert [x["id"] for x in resident2.ok("get", "/maintenance")["items"]] == [t204["id"]]
    assert resident.get(f"/maintenance/{t204['id']}").status_code == 404
    assert resident.get(f"/properties/{world.p204.id}").status_code == 404
    staff = as_(world.staff)
    assert [x["id"] for x in staff.ok("get", "/maintenance")["items"]] == [t117["id"]]
    assert staff.get(f"/maintenance/{t204['id']}").status_code == 404
    # guards do not see maintenance; residents cannot create tasks or read audit logs
    assert as_(world.guard).get("/maintenance").status_code == 403
    assert resident.post("/maintenance", {"title": "x", "category": "civil"}).status_code == 403
    assert resident.get("/audit").status_code == 403
    assert staff.get(f"/maintenance/{t117['id']}/audit").status_code == 200
    assert resident.get(f"/maintenance/{t117['id']}/audit").status_code == 403
    # staff cannot assign or approve
    assert staff.post(f"/maintenance/{t117['id']}/assign", {"assigned_staff_id": str(world.staff2.id)}).status_code == 403
    # super admin manages tenants but has no tenant data access
    root = as_(world.super)
    assert root.ok("get", "/tenants")["total"] == 2
    assert root.get("/maintenance").status_code == 403
    assert sup.get("/tenants").status_code == 403


def test_resident_evidence_privacy(as_, world):
    sup, staff, resident = as_(world.supervisor), as_(world.staff), as_(world.resident)
    t = sup.ok(
        "post",
        "/maintenance",
        {
            "title": "Clean 117",
            "category": "cleaning",
            "property_id": str(world.p117.id),
            "assigned_staff_id": str(world.staff.id),
            "checklist_items": ["Done"],
        },
    )
    t = staff.ok("post", f"/maintenance/{t['id']}/start", {})
    m = staff.upload("maintenance_task", t["id"], jpeg_bytes(), "image/jpeg", "after_photo").json()
    view = resident.ok("get", f"/maintenance/{t['id']}")
    assert view["evidence"] == [] and view["proof"] is None, "evidence hidden until approval (default policy)"
    assert resident.get(f"/media/{m['id']}").status_code == 404
    staff.ok("patch", f"/maintenance/{t['id']}/checklist/{t['checklist'][0]['id']}", {"status": "completed"})
    staff.ok("patch", f"/maintenance/{t['id']}", {"work_notes": "ok"})
    staff.ok("post", f"/maintenance/{t['id']}/complete", {})
    sup.ok("post", f"/maintenance/{t['id']}/approve", {})
    assert len(resident.ok("get", f"/maintenance/{t['id']}")["evidence"]) == 1
    as_(world.admin).ok("patch", "/settings", {"resident_evidence_visibility": "none"})
    assert resident.ok("get", f"/maintenance/{t['id']}")["evidence"] == []


def test_role_change_forces_relogin_and_is_audited(as_, world):
    admin, staff = as_(world.admin), as_(world.staff)
    admin.ok("patch", f"/users/{world.staff.id}", {"role": "supervisor"})
    assert staff.get("/auth/me").status_code == 401
    assert admin.patch(f"/users/{world.admin.id}", {"role": "staff"}).status_code == 422
    assert admin.patch(f"/users/{world.staff.id}", {"role": "super_admin"}).status_code == 403
    log = admin.ok("get", "/audit", params={"action": "user.role_changed"})["items"]
    assert log and log[0]["old_value"]["role"] == "staff" and log[0]["new_value"]["role"] == "supervisor"
    assert PASSWORD


def test_tenant_provisioning_and_suspension(as_, client, world):
    root = as_(world.super)
    out = root.ok(
        "post",
        "/tenants",
        {"name": "Lake View", "slug": "lake-view", "admin_email": "admin@lake.in", "admin_name": "Lake Admin", "admin_password": PASSWORD},
    )
    assert out["user"]["role"] == "layout_admin"
    lake = Api(client, "admin@lake.in")
    assert len(lake.ok("get", "/maintenance/policies")) >= 10
    assert len(lake.ok("get", "/layouts")) == 1
    root.ok("patch", f"/tenants/{out['user']['tenant_id']}", {"status": "suspended"})
    assert lake.get("/auth/me").status_code == 403
    assert client.post("/api/v1/auth/login", json={"email": "admin@lake.in", "password": PASSWORD}).status_code == 403
