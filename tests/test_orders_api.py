import asyncio
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agents.commerce import service as commerce
from backend.api.config import Settings
from backend.api.main import create_app
from backend.models import Product, Shop, Variant
from tests.conftest import GOOD_PHONE, NOW, SATURDAY_10AM, TEST_OWNER_KEY, give_key

KEY = TEST_OWNER_KEY
H = {"X-Owner-Key": KEY}


@pytest.fixture
def app(tmp_path: Path, dist_dir: Path):
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", dashboard_dist=dist_dir,
                        owner_key=KEY, gemini_model="test-model")
    return create_app(settings)


@pytest.fixture
def api(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def shop_orders(app):
    """A shop with one auto-approved and two held orders."""
    store, settings = app.state.store, app.state.settings
    shop = give_key(store, store.save_shop(Shop(slug="mak", name="Mak's Kuih")))
    lapis = store.save_product(Product(shop_id=shop.id, name="Kuih Lapis",
                                       variants=[Variant(label="20 pcs", price=Decimal("16"))]))

    def order(phone):
        return asyncio.run(commerce.place_order(
            store, shop.id, [{"product_id": lapis.id, "qty": 2}], "Siti", phone, SATURDAY_10AM,
            settings=settings, now=NOW))

    ok, held1, held2 = order(GOOD_PHONE), order("12345"), order("999")
    return shop, ok, held1, held2


def url(shop, path=""):
    return f"/api/shops/{shop.id}{path}"


def test_owner_key_required_everywhere(api, shop_orders):
    shop, ok, held, _ = shop_orders
    calls = [
        ("get", url(shop, "/orders")), ("get", url(shop, f"/orders/{ok.id}")),
        ("post", url(shop, f"/orders/{held.id}/approve")),
        ("post", url(shop, f"/orders/{held.id}/reject")),
        ("get", url(shop, "/audit")), ("patch", url(shop)),
    ]
    for method, path in calls:
        assert api.request(method, path).status_code == 401, path
        assert api.request(method, path, headers={"X-Owner-Key": "nope"}).status_code == 401


def test_list_orders_and_filter_by_status(api, shop_orders):
    shop, ok, held1, held2 = shop_orders
    r = api.get(url(shop, "/orders"), headers=H)
    assert r.status_code == 200
    assert [o["id"] for o in r.json()] == [held2.id, held1.id, ok.id]  # newest first
    r = api.get(url(shop, "/orders"), params={"status": "pending_approval"}, headers=H)
    assert {o["id"] for o in r.json()} == {held1.id, held2.id}
    assert r.json()[0]["risk"]["level"] in ("medium", "high")
    assert r.json()[0]["total"] == "32.00"
    assert api.get(url(shop, "/orders"), params={"status": "shipped"}, headers=H).status_code == 422


def test_get_order_and_404s(api, shop_orders):
    shop, ok, _, _ = shop_orders
    r = api.get(url(shop, f"/orders/{ok.id}"), headers=H)
    assert r.status_code == 200
    assert r.json()["status"] == "auto_approved"
    assert api.get(url(shop, "/orders/missing"), headers=H).status_code == 404
    # A key only opens its own shop: an unknown shop id is a 401, like any other shop.
    assert api.get(f"/api/shops/nope/orders/{ok.id}", headers=H).status_code == 401


def test_approve_and_reject(api, shop_orders):
    shop, ok, held1, held2 = shop_orders
    r = api.post(url(shop, f"/orders/{held1.id}/approve"), headers=H)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    r = api.post(url(shop, f"/orders/{held2.id}/reject"), json={"reason": "Fake number"},
                 headers=H)
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["rejection_reason"]) == ("rejected", "Fake number")

    # Only pending orders can change.
    for path in [f"/orders/{held1.id}/approve", f"/orders/{held2.id}/approve",
                 f"/orders/{ok.id}/reject"]:
        r = api.post(url(shop, path), headers=H)
        assert r.status_code == 409
        assert "Only orders waiting for approval" in r.json()["detail"]
    assert api.post(url(shop, "/orders/missing/approve"), headers=H).status_code == 404


def test_reject_without_body(api, shop_orders):
    shop, _, held, _ = shop_orders
    r = api.post(url(shop, f"/orders/{held.id}/reject"), headers=H)
    assert r.status_code == 200
    assert r.json()["rejection_reason"] == ""


def test_audit_newest_first_and_paginated(api, shop_orders):
    shop, _, _, held2 = shop_orders
    r = api.get(url(shop, "/audit"), headers=H)
    body = r.json()
    assert (body["limit"], body["offset"]) == (50, 0)
    events = body["events"]
    assert len(events) == 12  # 3 orders x 4 steps
    assert events[0]["action"] == "order_held"
    assert events[0]["entity_id"] == held2.id

    page1 = api.get(url(shop, "/audit"), params={"limit": 5}, headers=H).json()["events"]
    page2 = api.get(url(shop, "/audit"), params={"limit": 5, "offset": 5},
                    headers=H).json()["events"]
    assert [e["id"] for e in page1 + page2] == [e["id"] for e in events[:10]]
    assert api.get(url(shop, "/audit"), params={"limit": 0}, headers=H).status_code == 422
    assert api.get(url(shop, "/audit"), params={"limit": 201}, headers=H).status_code == 422


def test_patch_shop_settings(api, app, shop_orders):
    shop = shop_orders[0]
    r = api.patch(url(shop), json={"auto_approve_limit": "200", "hours": "Tue-Sun 9am-6pm"},
                  headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["auto_approve_limit"] == "200"
    saved = app.state.store.get_shop(shop.id)
    assert saved.auto_approve_limit == Decimal("200")
    assert saved.hours == "Tue-Sun 9am-6pm"
    assert saved.name == "Mak's Kuih"  # untouched

    [event] = [e for e in app.state.store.list_audit_events(shop.id)
               if e.action == "shop_settings_updated"]
    assert event.summary == "Owner changed hours, auto approve limit"
    assert event.details["before"]["auto_approve_limit"] == "150"


@pytest.mark.parametrize("body", [{}, {"auto_approve_limit": "-1"}, {"name": ""},
                                  {"auto_approve_limit": "abc"}])
def test_patch_shop_settings_rejects_bad_input(api, shop_orders, body):
    r = api.patch(url(shop_orders[0]), json=body, headers=H)
    assert r.status_code in (400, 422)


def test_shop_colour_defaults_to_chili(app, shop_orders):
    assert shop_orders[0].theme_colour == "chili"
    # Shops saved before the setting existed load with the default.
    assert Shop.model_validate({"slug": "old", "name": "Old"}).theme_colour == "chili"


def test_patch_shop_colour(api, app, shop_orders):
    shop = shop_orders[0]
    r = api.patch(url(shop), json={"theme_colour": "pandan"}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["theme_colour"] == "pandan"
    assert app.state.store.get_shop(shop.id).theme_colour == "pandan"


@pytest.mark.parametrize("colour", ["purple", "#2F7D4F", "PANDAN", "", "chili; x", 3])
def test_patch_shop_colour_only_presets(api, app, shop_orders, colour):
    shop = shop_orders[0]
    r = api.patch(url(shop), json={"theme_colour": colour}, headers=H)
    assert r.status_code == 422
    assert app.state.store.get_shop(shop.id).theme_colour == "chili"


def test_public_shop_page_has_the_colour(api, app, shop_orders):
    store = app.state.store
    shop = store.save_shop(shop_orders[0].model_copy(update={"published": True}))
    assert api.get(f"/api/public/shops/{shop.slug}").json()["shop"]["theme_colour"] == "chili"
    api.patch(url(shop), json={"theme_colour": "laut"}, headers=H)
    assert api.get(f"/api/public/shops/{shop.slug}").json()["shop"]["theme_colour"] == "laut"


def test_patch_unknown_shop(api):
    assert api.patch("/api/shops/nope", json={"hours": "9am-5pm"}, headers=H).status_code == 401


def test_api_routes_are_not_swallowed_by_dashboard(api, shop_orders):
    shop = shop_orders[0]
    r = api.get(url(shop, "/orders"), headers=H)
    assert r.headers["content-type"].startswith("application/json")
