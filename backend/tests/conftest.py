import io
import os
import tempfile
import uuid

os.environ.setdefault("GP_SECRET_KEY", "test-secret-key-for-greenplot-tests-0123456789")
os.environ.setdefault("GP_PUBLIC_BASE_URL", "http://testserver")
os.environ.setdefault("GP_API_RATE_PER_MINUTE", "100000")
os.environ.setdefault("GP_LOGIN_RATE_PER_MINUTE", "1000")

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.pool import StaticPool

from app.core import db as dbmod
from app.core.db import Base
from app.core.ratelimit import limiter
from app.core.security import hash_password
from app.main import create_app
from app.models import Layout, Property, Resident, StaffProfile, Tenant, User, Vendor
from app.models.enums import Role
from app.services.maintenance import ensure_default_policies
from app.services.storage import LocalStorage, set_storage

PASSWORD = "Passw0rd!"


@pytest.fixture()
def engine():
    url = os.environ.get("GP_TEST_DATABASE_URL", "sqlite://")
    if url.startswith("sqlite"):
        from sqlalchemy import create_engine, event

        eng = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(eng, "connect")
        def _fk(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
    else:
        from sqlalchemy import create_engine

        eng = create_engine(url)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    dbmod.engine = eng
    dbmod.SessionLocal.configure(bind=eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def storage_dir():
    with tempfile.TemporaryDirectory() as d:
        set_storage(LocalStorage(d, "http://testserver", "/api/v1", 300))
        yield d
        set_storage(None)


@pytest.fixture()
def db(engine):
    s = dbmod.SessionLocal()
    yield s
    s.close()


class World:
    """Two tenants with one user per role in tenant A."""

    def __init__(self, db):
        self.db = db
        hpw = hash_password(PASSWORD)

        def user(tenant, email, role, name, **kw):
            u = User(tenant_id=tenant.id if tenant else None, email=email, full_name=name, role=role, password_hash=hpw, **kw)
            db.add(u)
            db.flush()
            if role in (Role.STAFF, Role.GUARD, Role.SUPERVISOR) and tenant:
                db.add(StaffProfile(tenant_id=tenant.id, user_id=u.id, designation=role.title()))
            return u

        self.super = user(None, "root@greenplot.in", Role.SUPER_ADMIN, "Platform Admin")
        self.ta = Tenant(name="Green Valley Layout", slug="green-valley")
        self.tb = Tenant(name="Other Layout", slug="other-layout")
        db.add_all([self.ta, self.tb])
        db.flush()
        ensure_default_policies(db, self.ta.id)
        ensure_default_policies(db, self.tb.id)
        self.layout = Layout(tenant_id=self.ta.id, name="Green Valley")
        self.layout_b = Layout(tenant_id=self.tb.id, name="Other")
        db.add_all([self.layout, self.layout_b])
        db.flush()
        self.vendor = Vendor(tenant_id=self.ta.id, name="FixIt Gates", service_categories=["gate_fence"])
        db.add(self.vendor)
        db.flush()
        self.admin = user(self.ta, "admin@gv.in", Role.LAYOUT_ADMIN, "Asha Admin")
        self.supervisor = user(self.ta, "anita@gv.in", Role.SUPERVISOR, "Anita Supervisor")
        self.staff = user(self.ta, "ramesh@gv.in", Role.STAFF, "Ramesh Kumar", phone="9000000001")
        self.staff2 = user(self.ta, "suresh@gv.in", Role.STAFF, "Suresh Staff")
        self.guard = user(self.ta, "guard@gv.in", Role.GUARD, "Gopal Guard")
        self.vendor_user = user(self.ta, "vendor@fixit.in", Role.VENDOR, "Vikram Vendor", vendor_id=self.vendor.id)
        self.resident = user(self.ta, "owner117@gv.in", Role.RESIDENT, "Priya Owner")
        self.resident2 = user(self.ta, "owner204@gv.in", Role.RESIDENT, "Rahul Owner")
        self.admin_b = user(self.tb, "admin@other.in", Role.LAYOUT_ADMIN, "Other Admin")
        self.p117 = Property(
            tenant_id=self.ta.id,
            layout_id=self.layout.id,
            code="GV-117",
            plot_number="117",
            area_sqft=2400,
            owner_user_id=self.resident.id,
            owner_name="Priya Owner",
        )
        self.p204 = Property(tenant_id=self.ta.id, layout_id=self.layout.id, code="GV-204", plot_number="204", area_sqft=1200, units=2)
        self.pb = Property(tenant_id=self.tb.id, layout_id=self.layout_b.id, code="OT-1", plot_number="1")
        db.add_all([self.p117, self.p204, self.pb])
        db.flush()
        db.add(Resident(tenant_id=self.ta.id, property_id=self.p204.id, user_id=self.resident2.id, name="Rahul Owner", relation="owner"))
        db.commit()


@pytest.fixture()
def world(db, storage_dir):
    return World(db)


@pytest.fixture()
def client(engine, storage_dir):
    limiter.reset()
    app = create_app()
    with TestClient(app) as c:
        yield c


class Api:
    def __init__(self, client: TestClient, email: str):
        self.c = client
        r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        self.token = r.json()["access_token"]
        self.refresh = r.json()["refresh_token"]
        self.h = {"Authorization": f"Bearer {self.token}"}

    def get(self, path, **kw):
        return self.c.get(f"/api/v1{path}", headers={**self.h, **kw.pop("headers", {})}, **kw)

    def post(self, path, json=None, **kw):
        return self.c.post(f"/api/v1{path}", json=json, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def patch(self, path, json=None, **kw):
        return self.c.patch(f"/api/v1{path}", json=json, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def put(self, path, json=None, **kw):
        return self.c.put(f"/api/v1{path}", json=json, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def delete(self, path, json=None, **kw):
        return self.c.request("DELETE", f"/api/v1{path}", json=json, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def ok(self, method, path, json=None, status=(200, 201), **kw):
        r = getattr(self, method)(path, json=json, **kw) if method not in ("get",) else self.get(path, **kw)
        assert r.status_code in (status if isinstance(status, tuple) else (status,)), (
            f"{method.upper()} {path} -> {r.status_code}: {r.text}"
        )
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else r

    def upload(self, entity_type, entity_id, data: bytes, content_type: str, evidence_type=None, sha=None, **extra):
        """Signed-URL flow: request URL → PUT bytes → complete."""
        import hashlib

        body = {
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "content_type": content_type,
            "size_bytes": len(data),
            "sha256": sha if sha is not None else hashlib.sha256(data).hexdigest(),
            "filename": extra.pop("filename", "evidence"),
            **({"evidence_type": evidence_type} if evidence_type else {}),
            **extra,
        }
        r = self.post("/media/upload-url", json=body)
        if r.status_code != 201:
            return r
        info = r.json()
        if info["upload"] is None:  # idempotent retry of a finished upload
            return self.post("/media/complete", json={"media_id": info["media_id"]})
        url = info["upload"]["url"].replace("http://testserver", "")
        put = self.c.put(url, content=data, headers=info["upload"]["headers"])
        assert put.status_code == 200, put.text
        return self.post("/media/complete", json={"media_id": info["media_id"]})


@pytest.fixture()
def as_(client, world):
    cache = {}

    def login(user) -> Api:
        if user.email not in cache:
            cache[user.email] = Api(client, user.email)
        return cache[user.email]

    return login


def jpeg_bytes(color=(80, 140, 100), size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64


def uid(x) -> str:
    return str(x if isinstance(x, uuid.UUID) else x)
