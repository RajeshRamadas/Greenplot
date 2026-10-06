"""Sign-in and account management: lockout, one-time codes, password reset, 2-step verification,
sessions, invite delivery and self-registration."""

import time

import pytest

from app.core.config import get_settings
from app.models import RefreshToken, Resident, User, Vendor
from app.services import accounts, messaging
from tests.conftest import PASSWORD, Api


@pytest.fixture()
def mail():
    box = []
    messaging.set_smtp_sender(box.append)
    yield box
    messaging.set_smtp_sender(None)


def login_raw(client, email, password=PASSWORD, **extra):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password, **extra})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- lockout


def test_lockout_after_repeated_failures_and_unlock(client, world, as_, mail):
    s = get_settings()
    for _ in range(s.lockout_threshold):
        assert login_raw(client, world.resident.email, "wrong-pass1").status_code == 401
    r = login_raw(client, world.resident.email)  # even the right password is refused while locked
    assert r.status_code == 423 and "Try again" in r.json()["detail"]
    assert any("locked" in m["Subject"] for m in mail)  # security alert to the user

    u = as_(world.admin).ok("get", f"/users/{world.resident.id}")
    assert u["locked_until"]
    as_(world.admin).ok("post", f"/users/{world.resident.id}/unlock")
    assert login_raw(client, world.resident.email).status_code == 200


# --------------------------------------------------------------------------- forgot password


def test_password_reset_by_email_and_phone(client, world, db, mail):
    old = Api(client, world.resident.email)
    unknown = client.post("/api/v1/auth/password/forgot", json={"identifier": "nobody@example.com"})
    assert unknown.json() == {"sent": True, "channels": []}  # no account enumeration

    r = client.post("/api/v1/auth/password/forgot", json={"identifier": world.resident.email.upper()})
    code = r.json()["dev_code"]
    assert r.json()["channels"] == ["email"] and code in mail[-1].get_content()
    bad = client.post(
        "/api/v1/auth/password/reset", json={"identifier": world.resident.email, "code": "000000", "new_password": "NewPass#2026"}
    )
    assert bad.status_code == 400
    weak = client.post("/api/v1/auth/password/reset", json={"identifier": world.resident.email, "code": code, "new_password": "abcdefgh"})
    assert weak.status_code == 422
    ok = client.post("/api/v1/auth/password/reset", json={"identifier": world.resident.email, "code": code, "new_password": "NewPass#2026"})
    assert ok.status_code == 200, ok.text
    # Old sessions are gone, the code is single-use, and the new password works.
    assert client.get("/api/v1/auth/me", headers=old.h).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": old.refresh}).status_code == 401
    again = client.post(
        "/api/v1/auth/password/reset", json={"identifier": world.resident.email, "code": code, "new_password": "Other#2026x"}
    )
    assert again.status_code == 400
    assert login_raw(client, world.resident.email, "NewPass#2026").status_code == 200

    # By mobile number (staff member Ramesh has 9000000001 on file).
    r = client.post("/api/v1/auth/password/forgot", json={"identifier": "90000 00001"})
    assert r.json()["channels"] == ["sms"]
    client.post(
        "/api/v1/auth/password/reset", json={"identifier": "9000000001", "code": r.json()["dev_code"], "new_password": "Phone#2026"}
    )
    assert login_raw(client, world.staff.email, "Phone#2026").status_code == 200


def test_code_attempts_are_limited(client, world):
    code = client.post("/api/v1/auth/password/forgot", json={"identifier": world.resident.email}).json()["dev_code"]
    for _ in range(get_settings().otp_max_attempts):
        client.post(
            "/api/v1/auth/password/reset", json={"identifier": world.resident.email, "code": "111111", "new_password": "NewPass#2026"}
        )
    r = client.post("/api/v1/auth/password/reset", json={"identifier": world.resident.email, "code": code, "new_password": "NewPass#2026"})
    assert r.status_code == 400  # the right code no longer works once attempts are used up


# --------------------------------------------------------------------------- phone sign-in


def test_phone_code_sign_in(client, world, db):
    assert client.post("/api/v1/auth/otp/request", json={"phone": "9999999999"}).json() == {"sent": True, "channels": []}
    r = client.post("/api/v1/auth/otp/request", json={"phone": "+91 90000 00001"})
    code = r.json()["dev_code"]
    assert client.post("/api/v1/auth/otp/verify", json={"phone": "9000000001", "code": "123456"}).status_code == 400
    out = client.post("/api/v1/auth/otp/verify", json={"phone": "9000000001", "code": code})
    assert out.status_code == 200, out.text
    me = client.get("/api/v1/auth/me", headers=bearer(out.json()["access_token"])).json()
    assert me["email"] == world.staff.email and me["phone_verified_at"]

    # A number shared by two accounts can't be used to sign in.
    db.get(User, world.staff2.id).phone = "9000000001"
    db.commit()
    assert client.post("/api/v1/auth/otp/request", json={"phone": "9000000001"}).status_code == 409


def test_changing_own_phone_requires_a_code(as_, world):
    staff = as_(world.staff)
    code = staff.ok("post", "/auth/phone/request", {"phone": "98450 99999"})["dev_code"]
    assert staff.post("/auth/phone/confirm", json={"phone": "98450 99999", "code": "000000"}).status_code == 400
    out = staff.ok("post", "/auth/phone/confirm", {"phone": "98450 99999", "code": code})
    assert out == {"phone": "98450 99999", "verified": True}
    # Someone else's code can't confirm a number for this account.
    other = as_(world.staff2)
    code2 = other.ok("post", "/auth/phone/request", {"phone": "98450 88888"})["dev_code"]
    assert staff.post("/auth/phone/confirm", json={"phone": "98450 88888", "code": code2}).status_code == 400


# --------------------------------------------------------------------------- 2-step verification


def test_two_step_verification(client, world, as_, mail):
    admin = as_(world.admin)
    setup = admin.ok("post", "/auth/2fa/setup")
    secret = setup["secret"]
    assert setup["otpauth_uri"].startswith("otpauth://totp/GreenPlot:") and setup["qr_svg"].startswith("data:image/svg+xml")
    assert admin.post("/auth/2fa/enable", json={"code": "000000"}).status_code == 400
    enabled = admin.ok("post", "/auth/2fa/enable", {"code": accounts.totp(secret)})
    codes = enabled["recovery_codes"]
    assert len(codes) == 10 and admin.ok("get", "/auth/me")["totp_enabled"] is True

    # Password alone is no longer enough.
    first = login_raw(client, world.admin.email).json()
    assert first["mfa_required"] is True and first["access_token"] is None
    bad = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": first["mfa_token"], "code": "000000"})
    assert bad.status_code == 401
    ok = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": first["mfa_token"], "code": accounts.totp(secret)})
    assert ok.status_code == 200 and ok.json()["access_token"]

    # A recovery code works once.
    first = login_raw(client, world.admin.email).json()
    assert client.post("/api/v1/auth/2fa/verify", json={"mfa_token": first["mfa_token"], "code": codes[0]}).status_code == 200
    first = login_raw(client, world.admin.email).json()
    assert client.post("/api/v1/auth/2fa/verify", json={"mfa_token": first["mfa_token"], "code": codes[0]}).status_code == 401

    # Disabling needs the password and a code.
    fresh = Api.__new__(Api)
    fresh.c, fresh.h = client, bearer(ok.json()["access_token"])
    assert fresh.post("/auth/2fa/disable", json={"password": "nope", "code": accounts.totp(secret)}).status_code == 400
    assert fresh.post("/auth/2fa/disable", json={"password": PASSWORD, "code": accounts.totp(secret)}).status_code == 200
    assert login_raw(client, world.admin.email).json()["access_token"]


def test_admin_can_reset_a_lost_authenticator(client, world, as_):
    sup = as_(world.supervisor)
    secret = sup.ok("post", "/auth/2fa/setup")["secret"]
    sup.ok("post", "/auth/2fa/enable", {"code": accounts.totp(secret)})
    assert as_(world.admin).ok("post", f"/users/{world.supervisor.id}/reset-2fa")["totp_enabled"] is False
    assert client.get("/api/v1/auth/me", headers=sup.h).status_code == 401  # signed out everywhere
    assert login_raw(client, world.supervisor.email).json()["access_token"]


def test_required_two_step_verification_for_admin_roles(client, world, monkeypatch):
    monkeypatch.setattr(get_settings(), "mfa_required_roles", "layout_admin")
    admin = Api(client, world.admin.email)
    r = admin.get("/properties")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "mfa_setup_required"
    assert admin.ok("get", "/auth/me")["mfa_setup_required"] is True
    secret = admin.ok("post", "/auth/2fa/setup")["secret"]
    admin.ok("post", "/auth/2fa/enable", {"code": accounts.totp(secret)})
    assert admin.get("/properties").status_code == 200
    assert admin.post("/auth/2fa/disable", json={"password": PASSWORD, "code": accounts.totp(secret)}).status_code == 403


def test_totp_matches_rfc6238_vector():
    # RFC 6238 test secret "12345678901234567890", T=59 → 94287082 (8 digits) → last 6 digits 287082
    import base64

    secret = base64.b32encode(b"12345678901234567890").decode()
    assert accounts.totp(secret, at=59) == "287082"
    assert accounts.verify_totp(secret, accounts.totp(secret, at=time.time()))


# --------------------------------------------------------------------------- sessions


def test_sessions_list_and_sign_out_one_device(client, world, db):
    phone = Api(client, world.resident.email)
    laptop = Api(client, world.resident.email)
    rows = phone.ok("get", "/auth/sessions")
    assert len(rows) == 2 and sum(r["current"] for r in rows) == 1
    phone_sid = next(r["id"] for r in rows if r["current"])

    # Refreshing rotates the token but keeps the same session.
    new = client.post("/api/v1/auth/refresh", json={"refresh_token": phone.refresh}).json()
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": phone.refresh}).status_code == 401  # old token is spent
    phone.h = bearer(new["access_token"])
    assert {r["id"] for r in phone.ok("get", "/auth/sessions")} == {r["id"] for r in rows}

    laptop.ok("delete", f"/auth/sessions/{phone_sid}")
    assert client.get("/api/v1/auth/me", headers=phone.h).status_code == 401  # immediately, not after expiry
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401
    assert laptop.get("/auth/me").status_code == 200
    assert db.query(RefreshToken).filter(RefreshToken.revoked_at.is_(None)).count() == 1


# --------------------------------------------------------------------------- invites


def test_invites_are_sent_automatically(as_, world, mail, client):
    admin = as_(world.admin)
    out = admin.ok("post", "/users", {"email": "new.staff@gv.in", "full_name": "New Staff", "role": "staff", "phone": "9845011111"})
    assert set(out["sent_via"]) == {"email", "sms"}
    msg = next(m for m in mail if m["To"] == "new.staff@gv.in")
    assert "accept-invite?token=" in msg.get_content() and out["invite_token"] in msg.get_content()
    again = admin.ok("post", f"/users/{out['user']['id']}/reinvite")
    assert again["sent_via"] == ["email", "sms"]
    r = client.post("/api/v1/auth/accept-invite", json={"token": again["invite_token"], "password": "Welcome#2026"})
    assert r.status_code == 200 and r.json()["access_token"]


# --------------------------------------------------------------------------- self-registration


def _apply(client, **body):
    code = client.post("/api/v1/public/signup/code", json={"phone": body["phone"]}).json()["dev_code"]
    return client.post("/api/v1/public/signup", json={"code": code, **body})


def test_resident_and_vendor_self_registration(client, world, as_, db, mail):
    found = client.get("/api/v1/public/layouts", params={"q": "green"}).json()
    assert found == [{"slug": "green-valley", "name": "Green Valley Layout", "city": "Bangalore"}]

    wrong = client.post(
        "/api/v1/public/signup",
        json={
            "layout": "green-valley",
            "kind": "resident",
            "full_name": "Meera",
            "email": "meera@x.in",
            "phone": "9845022222",
            "code": "000000",
            "plot_number": "204",
        },
    )
    assert wrong.status_code == 400
    r = _apply(
        client,
        layout="green-valley",
        kind="resident",
        full_name="Meera Rao",
        email="Meera@x.in",
        phone="9845022222",
        plot_number="204",
        relation="tenant",
    )
    assert r.status_code == 201, r.text
    dup = _apply(
        client, layout="green-valley", kind="resident", full_name="Meera Rao", email="meera@x.in", phone="9845022222", plot_number="204"
    )
    assert dup.status_code == 409
    taken = _apply(
        client,
        layout="green-valley",
        kind="vendor",
        full_name="Xavier",
        email=world.resident.email,
        phone="9845033333",
        company_name="X Co",
    )
    assert taken.status_code == 409

    admin = as_(world.admin)
    assert as_(world.resident).get("/signups").status_code == 403
    pending = admin.ok("get", "/signups")["items"]
    req = next(p for p in pending if p["email"] == "meera@x.in")
    assert req["suggested_property_id"] == str(world.p204.id)
    assert admin.post(f"/signups/{req['id']}/approve", json={}).status_code == 422
    out = admin.ok("post", f"/signups/{req['id']}/approve", {"property_id": req["suggested_property_id"]})
    assert out["user"]["role"] == "resident" and "email" in out["sent_via"]
    db.expire_all()
    res = db.query(Resident).filter_by(email="meera@x.in").one()
    assert res.property_id == world.p204.id and res.relation == "tenant"
    assert admin.post(f"/signups/{req['id']}/approve", json={"property_id": req["suggested_property_id"]}).status_code == 409

    # Vendor: a new vendor company is created and linked.
    _apply(
        client,
        layout="green-valley",
        kind="vendor",
        full_name="Arjun",
        email="arjun@aquafix.in",
        phone="9845044444",
        company_name="AquaFix Plumbing",
        service_categories=["plumbing"],
    )
    v = next(p for p in admin.ok("get", "/signups")["items"] if p["kind"] == "vendor")
    out = admin.ok("post", f"/signups/{v['id']}/approve", {})
    db.expire_all()
    vendor = db.query(Vendor).filter_by(name="AquaFix Plumbing").one()
    assert out["user"]["vendor_id"] == str(vendor.id) and vendor.service_categories == ["plumbing"]

    # Rejection tells the applicant why.
    _apply(client, layout="green-valley", kind="resident", full_name="Spam", email="spam@x.in", phone="9845055555", plot_number="999")
    s = next(p for p in admin.ok("get", "/signups")["items"] if p["email"] == "spam@x.in")
    admin.ok("post", f"/signups/{s['id']}/reject", {"reason": "No such plot in this layout"})
    assert any(m["To"] == "spam@x.in" and "No such plot" in m.get_content() for m in mail)
    assert admin.ok("get", "/signups")["total"] == 0
