"""Customer side of an order: private status link, email updates, held orders that expire, and
cancelling. Email goes to the fake mailer (tests/conftest.py); nothing is sent."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agents.approval import service as approval
from agents.commerce import service as commerce
from backend.api.config import Settings
from backend.api.main import create_app, sweep_once
from backend.models import Channel, OrderStatus, Product, Shop, Variant, utc_now
from backend.timeutil import now_sg
from tests.conftest import give_key

KEY = "kc_owner-key"
OWNER = {"X-Owner-Key": KEY}


@pytest.fixture
def app(tmp_path: Path, dist_dir: Path):
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", dashboard_dist=dist_dir,
                        base_url="https://kc.example.sg", gemini_model="")
    return create_app(settings)


@pytest.fixture
def api(app) -> TestClient:
    return TestClient(app, base_url="https://kc.example.sg")


@pytest.fixture
def store(app):
    return app.state.store


@pytest.fixture
def shop(store) -> Shop:
    shop = store.save_shop(Shop(slug="mak-kuih", name="Mak's Kuih", published=True,
                                hours="Daily 8am-8pm", owner_email="owner@example.sg",
                                email_verified=True))
    store.save_product(Product(id="lapis", shop_id=shop.id, name="Kuih Lapis",
                               variants=[Variant(label="20 pcs", price=Decimal("16")),
                                         Variant(label="40 pcs", price=Decimal("30"))]))
    return give_key(store, shop, KEY)


def pickup(days=3, hour=10) -> str:
    return (now_sg() + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def web_order(api, qty=1, variant="20 pcs", **kw):
    body = {"items": [{"product_id": "lapis", "variant": variant, "qty": qty}],
            "customer_name": "Siti Rahman", "customer_phone": "+65 9123 4567",
            "pickup_time": pickup(), "note": "", "customer_email": "Siti@Example.SG"}
    body.update(kw)
    r = api.post("/api/public/shops/mak-kuih/orders", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def held_order(api):
    """S$300 is over the S$150 auto-approve limit, so the owner must decide."""
    body = web_order(api, qty=10, variant="40 pcs")
    assert body["status"] == "pending_owner_approval"
    return body


def token_of(url: str) -> str:
    return url.split("?t=", 1)[1]


def status(api, body):
    return api.get(f"/api/public/orders/{body['order_id']}",
                   params={"t": token_of(body["status_url"])})


def customer_mail(mail):
    return [e for e in mail.sent if e.to == "siti@example.sg"]


# --- status link --------------------------------------------------------------------------


def test_order_returns_a_private_status_link(api, shop, store):
    body = web_order(api)
    order = store.get_order(body["order_id"])
    assert body["status_url"] == f"https://kc.example.sg/o/{order.id}?t={order.status_token}"
    assert body["shop_name"] == "Mak's Kuih" and body["email_updates_to"] == "s***@example.sg"
    r = status(api, body)
    assert r.status_code == 200 and r.json()["order_id"] == order.id
    other = web_order(api)
    wrong = api.get(f"/api/public/orders/{order.id}", params={"t": token_of(other["status_url"])})
    assert wrong.status_code == 404  # another order's token doesn't open this one


def test_email_is_optional_but_must_look_like_one(api, shop, store):
    body = web_order(api, customer_email="")
    assert body["email_updates_to"] == ""
    r = api.post("/api/public/shops/mak-kuih/orders", json={
        "items": [{"product_id": "lapis", "variant": "20 pcs", "qty": 1}],
        "customer_name": "Siti", "customer_phone": "+65 9123 4567", "pickup_time": pickup(),
        "customer_email": "not an email"})
    assert r.status_code == 400 and "customer_email" in r.json()["detail"]


# --- customer emails ----------------------------------------------------------------------


def test_auto_approved_order_emails_the_customer(api, shop, mail):
    web_order(api)  # first order from this phone adds risk; the second is low risk
    body = web_order(api)
    assert body["status"] == "confirmed"
    (email, *_) = [e for e in customer_mail(mail) if body["order_id"] in e.text]
    assert email.subject.startswith("Confirmed: your order from Mak's Kuih")
    assert body["status_url"] in email.text and body["status_url"] in email.html


def test_owner_approve_and_reject_email_the_customer(api, shop, mail):
    first, second = held_order(api), held_order(api)
    assert customer_mail(mail) == []  # held: nothing yet
    r = api.post(f"/api/shops/{shop.id}/orders/{first['order_id']}/approve", headers=OWNER)
    assert r.status_code == 200
    r = api.post(f"/api/shops/{shop.id}/orders/{second['order_id']}/reject", headers=OWNER,
                 json={"reason": "Sold out that day"})
    assert r.status_code == 200
    subjects = [e.subject.split(":")[0] for e in customer_mail(mail)]
    assert subjects == ["Confirmed", "Not accepted"]
    assert "Sold out that day" in customer_mail(mail)[1].text
    assert status(api, first).json()["status"] == "confirmed"
    assert status(api, second).json()["rejection_reason"] == "Sold out that day"


def test_no_email_given_means_no_customer_email(api, shop, mail):
    body = web_order(api, customer_email="", qty=10, variant="40 pcs")
    api.post(f"/api/shops/{shop.id}/orders/{body['order_id']}/approve", headers=OWNER)
    assert customer_mail(mail) == []


# --- held orders expire -------------------------------------------------------------------


def age(store, order_id, hours):
    order = store.get_order(order_id)
    store.save_order(order.model_copy(update={"created_at": utc_now() - timedelta(hours=hours)}))


def test_held_order_expires_after_the_shops_timeout(api, shop, store, mail):
    body = held_order(api)
    age(store, body["order_id"], 23)
    assert status(api, body).json()["status"] == "pending_owner_approval"  # not yet
    age(store, body["order_id"], 25)
    seen = status(api, body).json()  # reading the status page expires it
    assert seen["status"] == "rejected" and seen["expired"] is True
    assert seen["message"] == "The shop didn't respond in time, so this order is cancelled."
    order = store.get_order(body["order_id"])
    assert order.rejection_reason == "The shop didn't respond in time" and order.expired
    (email,) = customer_mail(mail)
    assert email.subject.startswith("Not accepted") and "didn't reply in time" in email.text
    event = next(e for e in store.list_audit_events(shop.id) if e.action == "order_expired")
    assert event.actor == "system"
    # The owner can't approve it any more.
    r = api.post(f"/api/shops/{shop.id}/orders/{body['order_id']}/approve", headers=OWNER)
    assert r.status_code == 409


def test_timeout_is_per_shop_and_expiry_runs_once(api, shop, store, mail):
    store.save_shop(store.get_shop(shop.id).model_copy(update={"approval_timeout_hours": 2}))
    body = held_order(api)
    age(store, body["order_id"], 3)
    sweep_once(store, api.app.state.settings)  # the periodic sweep, no one reading
    asyncio.run(commerce.wait_for_background_tasks())
    sweep_once(store, api.app.state.settings)
    assert store.get_order(body["order_id"]).status == OrderStatus.rejected
    assert len([e for e in store.list_audit_events(shop.id) if e.action == "order_expired"]) == 1
    assert len(customer_mail(mail)) == 1


def test_owner_list_expires_overdue_orders(api, shop, store):
    body = held_order(api)
    age(store, body["order_id"], 30)
    orders = api.get(f"/api/shops/{shop.id}/orders", headers=OWNER).json()
    assert orders[0]["status"] == "rejected" and orders[0]["expired"] is True


def test_decided_order_never_expires(store, shop):
    async def go():
        order = await commerce.place_order(
            store, shop.id, [{"product_id": "lapis", "variant": "40 pcs", "qty": 10}], "Siti",
            "+65 9123 4567", pickup(), channel=Channel.web)
        await commerce.wait_for_background_tasks()
        return order
    order = asyncio.run(go())
    approval.approve(store, shop.id, order.id)
    assert approval.expire_overdue(store, shop, utc_now() + timedelta(days=5)) == []
    assert store.get_order(order.id).status == OrderStatus.approved


# --- cancel -------------------------------------------------------------------------------


def cancel(api, body):
    return api.post(f"/api/public/orders/{body['order_id']}/cancel",
                    params={"t": token_of(body["status_url"])})


def test_customer_cancels_and_both_sides_are_told(api, shop, store, mail):
    body = held_order(api)
    assert body["can_cancel"] is True
    r = cancel(api, body)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled" and r.json()["can_cancel"] is False
    assert store.get_order(body["order_id"]).status == OrderStatus.cancelled
    owner = [e for e in mail.sent if e.to == "owner@example.sg" and "Cancelled" in e.subject]
    assert len(owner) == 1 and "/signin?token=" in owner[0].text
    assert [e.subject.split(":")[0] for e in customer_mail(mail)] == ["Cancelled"]
    event = next(e for e in store.list_audit_events(shop.id) if e.action == "order_cancelled")
    assert event.actor == "customer"
    again = cancel(api, body)
    assert again.status_code == 409 and "already cancelled" in again.json()["detail"]
    # The owner can't approve a cancelled order.
    r = api.post(f"/api/shops/{shop.id}/orders/{body['order_id']}/approve", headers=OWNER)
    assert r.status_code == 409


def test_cancel_closes_at_the_shops_cutoff(api, shop, store):
    soon = (now_sg() + timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M")
    store.save_shop(store.get_shop(shop.id).model_copy(update={"hours": ""}))
    body = web_order(api, pickup_time=soon)
    assert body["can_cancel"] is False  # 10 hours away, cutoff is 12
    r = cancel(api, body)
    assert r.status_code == 409 and "12 hours before pickup" in r.json()["detail"]
    store.save_shop(store.get_shop(shop.id).model_copy(update={"cancel_cutoff_hours": 2}))
    assert cancel(api, body).status_code == 200


def test_cancel_needs_the_token(api, shop):
    body = web_order(api)
    r = api.post(f"/api/public/orders/{body['order_id']}/cancel", params={"t": "nope"})
    assert r.status_code == 404


def test_rejected_order_cannot_be_cancelled(api, shop):
    body = held_order(api)
    api.post(f"/api/shops/{shop.id}/orders/{body['order_id']}/reject", headers=OWNER,
             json={"reason": "No"})
    assert cancel(api, body).status_code == 409
