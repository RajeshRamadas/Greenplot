"""Billing & dues (requirements §19)."""

import hashlib
import hmac
import json

import pytest

from app.core.config import get_settings
from app.services import billing as billing_svc
from app.services.billing import sign_payload


def test_plan_generation_by_basis_and_idempotency(as_, world):
    admin = as_(world.admin)
    per_sqft = admin.ok("post", "/billing/plans", {"name": "Maintenance", "basis": "per_sqft", "rate": 2.5, "frequency_months": 3})
    out = admin.ok("post", "/billing/generate", {"plan_id": per_sqft["id"], "period_start": "2026-10-01"})
    amounts = {i["property_label"]: i["amount"] for i in out["invoices"]}
    assert amounts == {"Plot 117": 6000.0, "Plot 204": 3000.0}
    assert out["invoices"][0]["period_end"] == "2026-12-31" and out["invoices"][0]["due_date"] == "2026-10-16"
    again = admin.ok("post", "/billing/generate", {"plan_id": per_sqft["id"], "period_start": "2026-10-01"})
    assert again["created"] == 0 and len(again["skipped"]) == 2
    per_unit = admin.ok("post", "/billing/plans", {"name": "Water", "basis": "per_unit", "rate": 300})
    out = admin.ok("post", "/billing/generate", {"plan_id": per_unit["id"], "period_start": "2026-10-01"})
    assert {i["property_label"]: i["amount"] for i in out["invoices"]} == {"Plot 117": 300.0, "Plot 204": 600.0}
    custom = admin.ok(
        "post", "/billing/plans", {"name": "Corpus", "basis": "custom", "rate": 0, "custom_amounts": {str(world.p117.id): 10000}}
    )
    out = admin.ok("post", "/billing/generate", {"plan_id": custom["id"], "period_start": "2026-10-01"})
    assert out["created"] == 1 and len(out["skipped"]) == 1
    # residents only see their own dues; other tenants none
    assert {i["property_label"] for i in as_(world.resident).ok("get", "/billing/invoices")["items"]} == {"Plot 117"}
    assert as_(world.admin_b).ok("get", "/billing/invoices")["total"] == 0


def test_online_payment_webhook_is_verified_and_idempotent(as_, client, world):
    admin, resident = as_(world.admin), as_(world.resident)
    inv = admin.ok(
        "post", "/billing/invoices", {"property_id": str(world.p117.id), "description": "Q4 dues", "amount": 4500, "due_date": "2026-10-15"}
    )
    assert resident.post("/payments", {"invoice_id": inv["id"]}).status_code == 422, "Idempotency-Key header is required"
    h = {"Idempotency-Key": "pay-117-q4-0001"}
    p = resident.ok("post", "/payments", {"invoice_id": inv["id"]}, headers=h)
    assert p["status"] == "created" and p["checkout"]["amount_paise"] == 450000 and "card" in p["checkout"]["note"]
    assert resident.ok("post", "/payments", {"invoice_id": inv["id"]}, headers=h)["id"] == p["id"], "same key → same payment"

    event = {
        "id": "evt_1",
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_abc", "order_id": p["provider_order_id"], "amount": 450000}}},
    }
    raw = json.dumps(event).encode()
    assert client.post("/api/v1/payments/webhook", content=raw, headers={"X-Razorpay-Signature": "bad"}).status_code == 401
    r = client.post("/api/v1/payments/webhook", content=raw, headers={"X-Razorpay-Signature": sign_payload(raw)})
    assert r.json()["status"] == "applied"
    r = client.post("/api/v1/payments/webhook", content=raw, headers={"X-Razorpay-Signature": sign_payload(raw)})
    assert r.json()["status"] == "duplicate"
    inv = resident.ok("get", "/billing/invoices")["items"][0]
    assert inv["status"] == "paid" and inv["amount_paid"] == 4500.0
    pay = resident.ok("get", "/payments")["items"][0]
    assert pay["receipt_number"].startswith("GP-RCT-") and pay["provider_payment_id"] == "pay_abc"
    pdf = resident.get(f"/payments/{pay['id']}/receipt.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert admin.ok("get", "/payments/reconciliation")["invoice_mismatches"] == []


def test_webhook_amount_mismatch_is_not_applied(as_, client, world):
    admin, resident = as_(world.admin), as_(world.resident)
    inv = admin.ok(
        "post", "/billing/invoices", {"property_id": str(world.p117.id), "description": "Dues", "amount": 1000, "due_date": "2026-10-15"}
    )
    p = resident.ok("post", "/payments", {"invoice_id": inv["id"]}, headers={"Idempotency-Key": "k-mismatch-1"})
    raw = json.dumps(
        {
            "id": "evt_2",
            "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": "pay_x", "order_id": p["provider_order_id"], "amount": 100}}},
        }
    ).encode()
    assert (
        client.post("/api/v1/payments/webhook", content=raw, headers={"X-Razorpay-Signature": sign_payload(raw)}).json()["status"]
        == "amount_mismatch"
    )
    assert resident.ok("get", "/billing/invoices")["items"][0]["status"] == "unpaid"


def test_offline_payment_partial_and_defaulters(as_, world):
    admin = as_(world.admin)
    inv = admin.ok(
        "post",
        "/billing/invoices",
        {"property_id": str(world.p204.id), "description": "Old dues", "amount": 2000, "due_date": "2026-01-15"},
    )
    assert admin.ok("get", "/billing/defaulters")[0]["outstanding"] == 2000.0
    h = {"Idempotency-Key": "cash-204-0001"}
    p = admin.ok("post", "/payments/record", {"invoice_id": inv["id"], "amount": 500, "method": "cash"}, headers=h)
    again = admin.ok("post", "/payments/record", {"invoice_id": inv["id"], "amount": 500, "method": "cash"}, headers=h)
    assert p["id"] == again["id"]
    assert (
        admin.post(
            "/payments/record", {"invoice_id": inv["id"], "amount": 5000, "method": "cash"}, headers={"Idempotency-Key": "cash-204-0002"}
        ).status_code
        == 422
    )
    inv = admin.ok("get", "/billing/invoices", params={"property_id": str(world.p204.id)})["items"][0]
    assert inv["status"] == "partial" and inv["amount_paid"] == 500.0 and inv["overdue"]
    assert admin.ok("get", "/billing/defaulters")[0]["outstanding"] == 1500.0
    admin.ok("post", "/billing/expenses", {"category": "electricity", "amount": 800, "spent_on": "2026-10-01"})
    summary = admin.ok("get", "/billing/summary")
    assert summary["collected"] == 500.0 and summary["expenses"] == 800.0
    assert (
        as_(world.resident)
        .post("/payments/record", {"invoice_id": inv["id"], "amount": 1, "method": "cash"}, headers={"Idempotency-Key": "x" * 10})
        .status_code
        == 403
    )


@pytest.fixture
def razorpay(monkeypatch):
    """A fake Razorpay API: orders get ids, payments are reported as given in `state`."""
    s = get_settings()
    monkeypatch.setattr(s, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(s, "razorpay_key_secret", "rzp_test_secret")
    state = {"calls": [], "payments": {}}

    def transport(method, path, payload):
        state["calls"].append((method, path, payload))
        if path == "orders":
            return {"id": f"order_rzp{len(state['calls'])}", "amount": payload["amount"], "status": "created"}
        pay_id = path.split("/")[1]
        remote = state["payments"][pay_id]
        if path.endswith("/capture"):
            remote["status"] = "captured"
        return remote

    billing_svc.set_transport(transport)
    yield state
    billing_svc.set_transport(None)


def _rzp_sign(order_id, pay_id, secret="rzp_test_secret"):
    return hmac.new(secret.encode(), f"{order_id}|{pay_id}".encode(), hashlib.sha256).hexdigest()


def test_razorpay_order_checkout_and_verify(as_, world, razorpay):
    admin, resident = as_(world.admin), as_(world.resident)
    inv = admin.ok(
        "post", "/billing/invoices", {"property_id": str(world.p117.id), "description": "Q4 dues", "amount": 1200, "due_date": "2026-10-15"}
    )
    p = resident.ok("post", "/payments", {"invoice_id": inv["id"]}, headers={"Idempotency-Key": "rzp-117-0001"})
    assert razorpay["calls"][0][:2] == ("POST", "orders") and razorpay["calls"][0][2]["amount"] == 120000
    co = p["checkout"]
    assert co["key_id"] == "rzp_test_key" and co["order_id"] == p["provider_order_id"] and co["currency"] == "INR"
    assert resident.post(f"/payments/{p['id']}/simulate", {}).status_code == 404, "no simulation with a live gateway"

    order = p["provider_order_id"]
    body = {"razorpay_order_id": order, "razorpay_payment_id": "pay_1", "razorpay_signature": "forged"}
    assert resident.post(f"/payments/{p['id']}/verify", body).status_code == 401
    # Authorized but not yet captured: GreenPlot captures it, then applies it
    razorpay["payments"]["pay_1"] = {"id": "pay_1", "order_id": order, "amount": 120000, "status": "authorized"}
    body["razorpay_signature"] = _rzp_sign(order, "pay_1")
    out = resident.ok("post", f"/payments/{p['id']}/verify", body)
    assert out["status"] == "succeeded" and out["provider_payment_id"] == "pay_1" and out["receipt_number"]
    assert ("POST", "payments/pay_1/capture", {"amount": 120000, "currency": "INR"}) in razorpay["calls"]
    assert resident.ok("get", "/billing/invoices")["items"][0]["status"] == "paid"
    # Verifying again is harmless
    assert resident.ok("post", f"/payments/{p['id']}/verify", body)["status"] == "succeeded"


def test_razorpay_verify_rejects_wrong_amount(as_, world, razorpay):
    admin, resident = as_(world.admin), as_(world.resident)
    inv = admin.ok(
        "post", "/billing/invoices", {"property_id": str(world.p117.id), "description": "Dues", "amount": 500, "due_date": "2026-10-15"}
    )
    p = resident.ok("post", "/payments", {"invoice_id": inv["id"]}, headers={"Idempotency-Key": "rzp-117-0002"})
    order = p["provider_order_id"]
    razorpay["payments"]["pay_2"] = {"id": "pay_2", "order_id": order, "amount": 100, "status": "captured"}
    body = {"razorpay_order_id": order, "razorpay_payment_id": "pay_2", "razorpay_signature": _rzp_sign(order, "pay_2")}
    assert resident.ok("post", f"/payments/{p['id']}/verify", body)["status"] == "created"
    assert ("GET", "payments/pay_2", None) in razorpay["calls"], "verification asked Razorpay"
    assert resident.ok("get", "/billing/invoices")["items"][0]["status"] == "unpaid"
    flagged = admin.ok("get", "/payments/reconciliation")["needs_refund"]
    assert [(f["payment_id"], f["reason"]) for f in flagged] == [(p["id"], "amount_mismatch")]


def test_jobs_on_a_plot_are_billed_and_close_only_when_paid(as_, world):
    admin, sup, resident = as_(world.admin), as_(world.supervisor), as_(world.resident)
    job = {"title": "Fix tap", "category": "plumbing", "property_id": str(world.p117.id), "charge": 800}
    t = sup.ok("post", "/maintenance", job)
    pay = t["payment"]
    assert pay["amount"] == 800.0 and pay["status"] == "unpaid" and "set_charge" in t["allowed_actions"]
    inv = next(i for i in resident.ok("get", "/billing/invoices")["items"] if i["id"] == pay["invoice_id"])
    assert inv["maintenance_task_id"] == t["id"] and t["number"] in inv["description"]

    # Changing the charge voids a checkout opened for the old amount
    resident.ok("post", "/payments", {"invoice_id": pay["invoice_id"]}, headers={"Idempotency-Key": "job-tap-0001"})
    t = sup.ok("patch", f"/maintenance/{t['id']}", {"charge": 950})
    assert t["payment"]["amount"] == 950.0
    assert resident.ok("get", "/payments", params={"invoice_id": pay["invoice_id"]})["items"][0]["status"] == "failed"
    assert as_(world.resident).patch(f"/maintenance/{t['id']}", {"charge": 1}).status_code in (403, 404)

    # Partly paid: the charge cannot drop below what was paid
    admin.ok(
        "post",
        "/payments/record",
        {"invoice_id": pay["invoice_id"], "amount": 400, "method": "cash"},
        headers={"Idempotency-Key": "cash-tap-01"},
    )
    assert sup.patch(f"/maintenance/{t['id']}", {"charge": 300}).status_code == 422
    assert "550" in sup.ok("get", f"/maintenance/{t['id']}")["payment"]["blocking"]

    # Cancelling an unpaid job drops its bill
    t2 = sup.ok("post", "/maintenance", {**job, "title": "Fix gate"})
    sup.ok("post", f"/maintenance/{t2['id']}/cancel", {"reason": "Duplicate"})
    assert sup.ok("get", f"/maintenance/{t2['id']}")["payment"]["status"] == "waived"


def test_jobs_without_a_plot_are_not_billed(as_, world):
    sup = as_(world.supervisor)
    t = sup.ok("post", "/maintenance", {"title": "Sweep main road", "category": "cleaning"})
    assert t["payment"] is None and "set_charge" not in t["allowed_actions"]
    assert sup.patch(f"/maintenance/{t['id']}", {"charge": 100}).status_code == 422


def test_job_payment_can_be_switched_off(as_, world):
    from app.models import Tenant

    tenant = world.db.get(Tenant, world.admin.tenant_id)
    tenant.settings = {**(tenant.settings or {}), "job_payment_required": False}
    world.db.commit()
    t = as_(world.supervisor).ok("post", "/maintenance", {"title": "Fix tap", "category": "plumbing", "property_id": str(world.p117.id)})
    assert t["payment"] is None


def test_sample_webhook_secret_is_refused_once_live(client, razorpay):
    raw = json.dumps({"id": "evt_forged", "event": "payment.captured", "payload": {}}).encode()
    r = client.post("/api/v1/payments/webhook", content=raw, headers={"X-Razorpay-Signature": sign_payload(raw)})
    assert r.status_code == 401, "whsec-dev is public; it must not verify webhooks with live keys"


def test_zero_bills_and_unconfigured_production_cannot_be_paid_online(as_, world, monkeypatch):
    resident = as_(world.resident)
    t = as_(world.supervisor).ok("post", "/maintenance", {"title": "Fix tap", "category": "plumbing", "property_id": str(world.p117.id)})
    inv_id = as_(world.admin).ok("get", f"/maintenance/{t['id']}")["payment"]["invoice_id"]
    assert resident.post("/payments", {"invoice_id": inv_id}, headers={"Idempotency-Key": "zero-bill-01"}).status_code == 409
    as_(world.supervisor).ok("patch", f"/maintenance/{t['id']}", {"charge": 200})
    monkeypatch.setattr(get_settings(), "environment", "production")
    assert resident.post("/payments", {"invoice_id": inv_id}, headers={"Idempotency-Key": "prod-nokeys-1"}).status_code == 503


def test_waived_bill_voids_open_checkout_and_late_capture_is_flagged(as_, client, world):
    admin, sup, resident = as_(world.admin), as_(world.supervisor), as_(world.resident)
    t = sup.ok("post", "/maintenance", {"title": "Fix tap", "category": "plumbing", "property_id": str(world.p117.id), "charge": 300})
    inv_id = t["payment"]["invoice_id"]
    p = resident.ok("post", "/payments", {"invoice_id": inv_id}, headers={"Idempotency-Key": "late-cap-01"})
    admin.ok("post", f"/billing/invoices/{inv_id}/waive", {})
    assert resident.ok("get", "/payments", params={"invoice_id": inv_id})["items"][0]["status"] == "failed"
    # The owner still completes the old checkout: the money is recorded, the bill stays waived, and it is flagged
    raw = json.dumps(
        {
            "id": "evt_late",
            "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": "pay_late", "order_id": p["provider_order_id"], "amount": 30000}}},
        }
    ).encode()
    client.post("/api/v1/payments/webhook", content=raw, headers={"X-Razorpay-Signature": sign_payload(raw)})
    assert sup.ok("get", f"/maintenance/{t['id']}")["payment"]["status"] == "waived"
    assert [f["reason"] for f in admin.ok("get", "/payments/reconciliation")["needs_refund"]] == ["overpaid"]


def test_cancelling_a_partly_paid_job_drops_the_balance(as_, world):
    admin, sup = as_(world.admin), as_(world.supervisor)
    t = sup.ok("post", "/maintenance", {"title": "Fix tap", "category": "plumbing", "property_id": str(world.p117.id), "charge": 1000})
    admin.ok(
        "post",
        "/payments/record",
        {"invoice_id": t["payment"]["invoice_id"], "amount": 400, "method": "cash"},
        headers={"Idempotency-Key": "partial-cancel-1"},
    )
    sup.ok("post", f"/maintenance/{t['id']}/cancel", {"reason": "Owner fixed it"})
    assert sup.ok("get", f"/maintenance/{t['id']}")["payment"]["status"] == "waived"


def test_job_bill_is_hidden_from_the_worker_and_follows_the_complaint_plot(as_, world):
    sup, staff, resident = as_(world.supervisor), as_(world.staff), as_(world.resident)
    t = sup.ok(
        "post",
        "/maintenance",
        {
            "title": "Fix tap",
            "category": "plumbing",
            "property_id": str(world.p117.id),
            "charge": 500,
            "assigned_staff_id": str(world.staff.id),
        },
    )
    assert staff.ok("get", f"/maintenance/{t['id']}")["payment"] is None
    assert resident.ok("get", f"/maintenance/{t['id']}")["payment"]["amount"] == 500.0
    c = resident.ok("post", "/complaints", {"category": "gate", "title": "Gate stuck", "property_id": str(world.p117.id)})
    r = sup.post(
        "/maintenance", {"title": "Fix gate", "category": "gate_fence", "complaint_id": c["id"], "property_id": str(world.p204.id)}
    )
    assert r.status_code == 422
