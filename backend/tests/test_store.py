import json
from decimal import Decimal

import pytest

from app.core.config import get_settings
from app.models import AuditLog, StoreProduct
from app.services import billing
from tests.test_billing import _rzp_sign, razorpay  # noqa: F401 - shared fake gateway fixture

BASE = "/api/v1/public/store"


@pytest.fixture
def plants(db):
    rows = [
        StoreProduct(
            slug="money-plant",
            name="Money Plant",
            category="indoor",
            summary="s",
            description="d",
            care={},
            price=Decimal("249"),
            image="/store/money-plant.svg",
            active=True,
            sort_order=1,
        ),
        StoreProduct(
            slug="areca-palm",
            name="Areca Palm",
            category="indoor",
            summary="s",
            description="d",
            care={},
            price=Decimal("599"),
            stock=3,
            image="/store/areca-palm.svg",
            active=True,
            sort_order=2,
        ),
        StoreProduct(
            slug="retired",
            name="Retired",
            category="outdoor",
            summary="s",
            description="d",
            care={},
            price=Decimal("100"),
            image="/x.svg",
            active=False,
            sort_order=3,
        ),
    ]
    db.add_all(rows)
    db.commit()
    return {p.slug: p for p in rows}


def order_body(**kw):
    body = {
        "items": [{"slug": "money-plant", "quantity": 2}],
        "name": "Kavya Rao",
        "phone": "9876543210",
        "address": "12, 3rd Cross, HMT Layout",
        "area": "Jalahalli",
        "pincode": "560013",
        "payment_method": "cod",
    }
    body.update(kw)
    return body


def place(client, key="order-key-0001", **kw):
    return client.post(f"{BASE}/orders", json=order_body(**kw), headers={"Idempotency-Key": key})


def test_catalogue_lists_only_active_plants(client, plants):
    slugs = [p["slug"] for p in client.get(f"{BASE}/products").json()]
    assert slugs == ["money-plant", "areca-palm"]
    assert client.get(f"{BASE}/products/retired").status_code == 404
    assert client.get(f"{BASE}/products/areca-palm").json()["price"] == 599
    assert client.get(f"{BASE}/config").json()["online"] == "demo"


def test_cash_on_delivery_order_gets_a_bill_and_server_prices(client, plants):
    r = place(client)
    assert r.status_code == 201, r.text
    out = r.json()
    o, token = out["order"], out["token"]
    # 2 x 249 is under the free-delivery threshold, so the delivery fee is added
    assert o["subtotal"] == 498 and o["delivery_fee"] == get_settings().store_delivery_fee and o["total"] == 498 + o["delivery_fee"]
    assert o["status"] == "placed" and o["payment_status"] == "unpaid"
    assert o["number"].startswith("GP-ORD-") and o["bill_number"].startswith("GP-BILL-")
    assert o["items"] == [{"slug": "money-plant", "name": "Money Plant", "unit_price": 249, "quantity": 2, "line_total": 498}]
    # The same request again returns the same order without a new link secret
    again = place(client).json()
    assert again["order"]["id"] == o["id"] and again["token"] is None
    # The order and its bill open only with the secret link
    assert client.get(f"{BASE}/orders/{o['number']}").status_code == 404
    assert client.get(f"{BASE}/orders/{o['number']}", params={"t": "wrong"}).status_code == 404
    assert client.get(f"{BASE}/orders/{o['number']}", params={"t": token}).json()["total"] == o["total"]
    pdf = client.get(f"{BASE}/orders/{o['number']}/bill.pdf", params={"t": token})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    # Nothing to pay online for a cash order
    assert client.post(f"{BASE}/orders/{o['number']}/pay", params={"t": token}).status_code == 409


def test_free_delivery_stock_and_checks(client, plants, db):
    o = place(client, items=[{"slug": "areca-palm", "quantity": 2}]).json()["order"]
    assert o["delivery_fee"] == 0 and o["total"] == 1198
    db.refresh(plants["areca-palm"])
    assert plants["areca-palm"].stock == 1
    r = place(client, key="order-key-0002", items=[{"slug": "areca-palm", "quantity": 2}])
    assert r.status_code == 409 and "Only 1" in r.json()["detail"]
    assert place(client, key="order-key-0003", items=[{"slug": "retired", "quantity": 1}]).status_code == 409
    assert place(client, key="order-key-0004", pincode="110001").status_code == 422, "outside Bangalore"
    assert place(client, key="order-key-0005", items=[]).status_code == 422
    big = place(client, key="order-key-0006", items=[{"slug": "money-plant", "quantity": 20}, {"slug": "areca-palm", "quantity": 1}])
    assert big.status_code == 422 and "Cash on delivery" in big.json()["detail"], "over the COD limit"


def test_online_order_in_demo_mode(client, plants):
    out = place(client, payment_method="online").json()
    o, token = out["order"], out["token"]
    assert o["status"] == "pending_payment"
    num = o["number"]
    assert client.post(f"{BASE}/orders/{num}/simulate", params={"t": token}).status_code == 409, "start the payment first"
    co = client.post(f"{BASE}/orders/{num}/pay", params={"t": token}).json()
    assert co["key_id"] is None and co["amount_paise"] == int(o["total"] * 100)
    assert client.post(f"{BASE}/orders/{num}/pay", params={"t": token}).json()["order_id"] == co["order_id"], "gateway order is reused"
    paid = client.post(f"{BASE}/orders/{num}/simulate", params={"t": token}).json()
    assert paid["payment_status"] == "paid" and paid["status"] == "placed" and paid["provider_payment_id"]


def test_online_payment_is_off_in_production_without_keys(client, plants, monkeypatch):
    monkeypatch.setattr(get_settings(), "environment", "production")
    assert client.get(f"{BASE}/config").json()["online"] is None
    assert place(client, payment_method="online").status_code == 503
    assert place(client, key="order-key-cod").status_code == 201


def test_razorpay_checkout_verify_and_webhook(client, plants, razorpay, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "payment_webhook_secret", "whsec-real-secret")
    out = place(client, payment_method="online").json()
    o, token = out["order"], out["token"]
    num, paise = o["number"], int(o["total"] * 100)
    co = client.post(f"{BASE}/orders/{num}/pay", params={"t": token}).json()
    assert co["key_id"] == "rzp_test_key" and razorpay["calls"][0][2]["notes"] == {"store_order": num}
    assert client.post(f"{BASE}/orders/{num}/simulate", params={"t": token}).status_code == 404, "no simulation when live"
    body = {"razorpay_order_id": co["order_id"], "razorpay_payment_id": "pay_s1", "razorpay_signature": "forged"}
    assert client.post(f"{BASE}/orders/{num}/verify", params={"t": token}, json=body).status_code == 401
    razorpay["payments"]["pay_s1"] = {"id": "pay_s1", "order_id": co["order_id"], "amount": paise - 100, "status": "captured"}
    body["razorpay_signature"] = _rzp_sign(co["order_id"], "pay_s1")
    assert client.post(f"{BASE}/orders/{num}/verify", params={"t": token}, json=body).status_code == 409, "short payment"
    razorpay["payments"]["pay_s1"]["amount"] = paise
    r = client.post(f"{BASE}/orders/{num}/verify", params={"t": token}, json=body).json()
    assert r["payment_status"] == "paid" and r["status"] == "placed"

    # A second order is confirmed by the webhook alone
    out2 = place(client, key="order-key-0002", payment_method="online").json()
    co2 = client.post(f"{BASE}/orders/{out2['order']['number']}/pay", params={"t": out2["token"]}).json()
    event = {
        "id": "evt_store_1",
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_s2", "order_id": co2["order_id"], "amount": paise}}},
    }
    raw = json.dumps(event).encode()
    hook = client.post("/api/v1/payments/webhook", content=raw, headers={"X-Razorpay-Signature": billing.sign_payload(raw)})
    assert hook.json() == {"status": "applied"}
    assert client.get(f"{BASE}/orders/{out2['order']['number']}", params={"t": out2["token"]}).json()["payment_status"] == "paid"


def test_office_manages_orders_and_products(as_, client, world, plants, db):
    o = place(client).json()["order"]
    admin = as_(world.super)
    assert as_(world.admin).get("/store/orders").status_code == 403, "layout admins do not run the store"
    page = admin.ok("get", "/store/orders", params={"status": "open"})
    assert page["total"] == 1 and page["items"][0]["phone"] == "9876543210"
    assert admin.get(f"/store/orders/{o['id']}/bill.pdf").content.startswith(b"%PDF")
    assert admin.patch(f"/store/orders/{o['id']}", {"status": "pending_payment"}).status_code == 422
    admin.ok("patch", f"/store/orders/{o['id']}", {"status": "out_for_delivery"})
    assert admin.patch(f"/store/orders/{o['id']}", {"status": "confirmed"}).status_code == 409, "no going back"
    done = admin.ok("patch", f"/store/orders/{o['id']}", {"status": "delivered"})
    assert done["payment_status"] == "paid" and done["delivered_at"], "cash collected on delivery"

    # Cancelling puts tracked stock back
    o2 = place(client, key="order-key-0002", items=[{"slug": "areca-palm", "quantity": 2}]).json()["order"]
    admin.ok("patch", f"/store/orders/{o2['id']}", {"status": "cancelled", "reason": "Customer asked"})
    db.refresh(plants["areca-palm"])
    assert plants["areca-palm"].stock == 3

    new = admin.ok(
        "post",
        "/store/products",
        {
            "slug": "tulsi",
            "name": "Tulsi",
            "category": "herbs",
            "summary": "Holy basil",
            "description": "A sacred herb",
            "price": 149,
            "image": "/store/tulsi.svg",
        },
    )
    assert admin.post("/store/products", {**new, "slug": "tulsi"}).status_code in (409, 422)
    upd = admin.ok("patch", f"/store/products/{new['id']}", {"price": 129, "stock": 5, "name": None})
    assert upd["price"] == 129 and upd["stock"] == 5 and upd["name"] == "Tulsi"
    admin.ok("patch", f"/store/products/{new['id']}", {"active": False})
    assert client.get(f"{BASE}/products/tulsi").status_code == 404
    assert db.query(AuditLog).filter(AuditLog.action == "store.product_updated").count() == 2
