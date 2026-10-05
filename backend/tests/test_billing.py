"""Billing & dues (requirements §19)."""

import json

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
