"""Subscription plans and the referral reward."""

from datetime import date, timedelta

from app.models import Tenant
from app.services import jobs, subscriptions


def _cleaning_plan(admin, **kw):
    return admin.ok(
        "post",
        "/billing/plans",
        {"name": "Plot cleaning", "basis": "per_plot", "rate": 1000, "frequency_months": 1, "subscribable": True, **kw},
    )


def test_resident_subscribes_quarterly_at_a_discount_and_is_billed_on_schedule(as_, world, db):
    admin, resident = as_(world.admin), as_(world.resident)
    plan = _cleaning_plan(admin)
    admin.ok("post", "/billing/plans", {"name": "Corpus", "basis": "fixed", "rate": 5000})  # not offered as a subscription

    opts = resident.ok("get", "/subscriptions/options")
    assert {(o["frequency"], o["price"], o["saving"]) for o in opts} == {("Monthly", 950.0, 50.0), ("Quarterly", 2700.0, 300.0)}
    assert all(o["property_label"] == "Plot 117" for o in opts)

    start = date.today()
    sub = resident.ok("post", "/subscriptions", {"property_id": str(world.p117.id), "plan_id": plan["id"], "frequency_months": 3})
    assert sub["status"] == "active" and sub["discount_pct"] == 10.0 and sub["price"] == 2700.0
    assert sub["next_billing_date"] == str(subscriptions.add_months(start, 3))
    invoices = resident.ok("get", "/billing/invoices")["items"]
    assert len(invoices) == 1 and invoices[0]["amount"] == 2700.0 and invoices[0]["subscription_id"] == sub["id"]
    assert "Quarterly subscription" in invoices[0]["description"]

    # one subscription per plot and plan; residents can't touch other plots or set their own discount
    body = {"property_id": str(world.p117.id), "plan_id": plan["id"], "frequency_months": 1}
    assert resident.post("/subscriptions", body).status_code == 409
    assert resident.post("/subscriptions", {**body, "property_id": str(world.p204.id)}).status_code == 404
    assert resident.post("/subscriptions", {**body, "discount_pct": 50}).status_code == 403
    assert resident.post("/subscriptions", {**body, "frequency_months": 2}).status_code == 422

    # plan-wide runs leave the subscribed plot to its subscription
    out = admin.ok("post", "/billing/generate", {"plan_id": plan["id"], "period_start": str(start.replace(day=1))})
    assert [i["property_label"] for i in out["invoices"]] == ["Plot 204"]
    assert "GV-117: billed by its subscription" in out["skipped"]

    # the worker raises the next quarter when it starts, once
    later = subscriptions.add_months(start, 3)
    assert len(subscriptions.bill_due(db, today=later)) == 1
    assert subscriptions.bill_due(db, today=later) == []
    db.commit()
    assert resident.ok("get", "/billing/invoices")["total"] == 2

    cancelled = resident.ok("post", f"/subscriptions/{sub['id']}/cancel")
    assert cancelled["status"] == "cancelled"
    assert subscriptions.bill_due(db, today=later + timedelta(days=200)) == []
    assert as_(world.resident2).ok("get", "/subscriptions") == []
    assert as_(world.admin_b).post(f"/subscriptions/{sub['id']}/cancel").status_code == 404


def test_admin_can_set_discount_and_tenant_can_change_defaults(as_, world, db):
    admin = as_(world.admin)
    plan = _cleaning_plan(admin, frequency_months=3, rate=3000)  # plan priced per quarter
    tenant = db.get(Tenant, world.ta.id)
    tenant.settings = {**(tenant.settings or {}), "subscription_discounts": {"1": 0, "3": 15}}
    db.commit()
    opts = admin.ok("get", "/subscriptions/options", params={"property_id": str(world.p204.id)})
    assert {(o["frequency"], o["price"]) for o in opts} == {("Monthly", 1000.0), ("Quarterly", 2550.0)}
    sub = admin.ok(
        "post", "/subscriptions", {"property_id": str(world.p204.id), "plan_id": plan["id"], "frequency_months": 1, "discount_pct": 20}
    )
    assert sub["price"] == 800.0
    assert len(admin.ok("get", "/subscriptions")) == 1


def test_referral_reward_settles_the_referrers_dues(as_, world, db):
    admin, resident = as_(world.admin), as_(world.resident)
    ref = resident.ok("post", "/referrals", {"neighbour_name": "Kiran Neighbour", "neighbour_phone": "+91 98450 12345"})
    assert ref["status"] == "pending" and ref["neighbour_phone"] == "9845012345" and ref["property_label"] == "Plot 117"
    dup = {"neighbour_name": "Kiran again", "neighbour_phone": "09845012345"}
    assert resident.post("/referrals", dup).status_code == 409
    assert admin.post("/referrals", dup).status_code == 403
    assert as_(world.resident2).ok("get", "/referrals")["items"] == []

    inv = admin.ok(
        "post", "/billing/invoices", {"property_id": str(world.p117.id), "description": "Dues", "amount": 300, "due_date": "2026-11-01"}
    )
    assert admin.post(f"/referrals/{ref['id']}/convert", {"property_id": str(world.p117.id)}).status_code == 422
    assert resident.post(f"/referrals/{ref['id']}/convert", {"property_id": str(world.p204.id)}).status_code == 403
    done = admin.ok("post", f"/referrals/{ref['id']}/convert", {"property_id": str(world.p204.id)})
    assert done["status"] == "converted" and done["reward_amount"] == 500.0 and done["reward_remaining"] == 200.0

    paid = resident.ok("get", "/billing/invoices")["items"][0]
    assert paid["id"] == inv["id"] and paid["status"] == "paid"
    pay = resident.ok("get", "/payments")["items"][0]
    assert pay["method"] == "referral_credit" and pay["amount"] == 300.0 and pay["receipt_number"]

    # the rest of the reward comes off the next dues, raised later
    admin.ok(
        "post", "/billing/invoices", {"property_id": str(world.p117.id), "description": "Next", "amount": 450, "due_date": "2026-12-01"}
    )
    assert jobs.run_all(db)["referral_credits_applied"] == 1
    mine = resident.ok("get", "/referrals")
    assert mine["credit_remaining"] == 0 and mine["reward_amount"] == 500.0
    nxt = [i for i in resident.ok("get", "/billing/invoices")["items"] if i["description"] == "Next"][0]
    assert nxt["status"] == "partial" and nxt["amount_paid"] == 200.0
    assert admin.ok("get", "/payments/reconciliation")["invoice_mismatches"] == []

    # one reward per neighbour plot; closed referrals stay closed
    other = resident.ok("post", "/referrals", {"neighbour_name": "Meena", "neighbour_phone": "9845000000"})
    assert admin.post(f"/referrals/{other['id']}/convert", {"property_id": str(world.p204.id)}).status_code == 409
    assert admin.ok("post", f"/referrals/{other['id']}/decline")["status"] == "declined"
    assert admin.post(f"/referrals/{ref['id']}/decline").status_code == 409
    assert {r["status"] for r in admin.ok("get", "/referrals")["items"]} == {"converted", "declined"}
