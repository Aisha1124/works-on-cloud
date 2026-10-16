"""Owner routes added for the dashboard: shop get/list/publish/photos, product CRUD,
and the public shop page with JSON-LD. Gemini is always faked."""

import io
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from agents.catalog import extract as ex
from agents.catalog.schema import CatalogDraft, DraftProduct
from backend.api.config import Settings
from backend.api.main import create_app
from backend.models import Product, Shop, Variant
from tests.conftest import TEST_OWNER_KEY, give_key

KEY = TEST_OWNER_KEY
H = {"X-Owner-Key": KEY}
DIST_HTML = "<!doctype html><html><head><title>KampungCart</title></head><body><div id=root></div></body></html>"


@pytest.fixture
def app(tmp_path: Path, dist_dir: Path):
    (dist_dir / "index.html").write_text(DIST_HTML, encoding="utf-8")
    settings = Settings(
        _env_file=None, data_dir=tmp_path / "data", uploads_dir=tmp_path / "uploads",
        dashboard_dist=dist_dir, owner_key=KEY, gemini_model="test-model",
        base_url="https://kc.example.sg/",
    )
    return create_app(settings)


@pytest.fixture
def api(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def store(app):
    return app.state.store


@pytest.fixture
def draft_shop(store) -> Shop:
    shop = give_key(store, store.save_shop(Shop(slug="sample-bakery-ab12", name="Sample Bakery")))
    store.save_product(Product(shop_id=shop.id, name="Kuih Lapis", category="Kuih",
                               variants=[Variant(label="20 pcs", price=Decimal("16"))],
                               confidence=0.4))
    return shop


def audit_actions(store, shop_id):
    return [e.action for e in store.list_audit_events(shop_id)]


# --- auth ------------------------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("get", "/api/shops/x"),
    ("post", "/api/shops/x/publish"),
    ("post", "/api/shops/x/products"),
    ("put", "/api/shops/x/products/p"),
    ("delete", "/api/shops/x/products/p"),
])
def test_owner_routes_need_key(api, method, path):
    assert getattr(api, method)(path).status_code == 401


# --- shop ------------------------------------------------------------------------------

def test_there_is_no_list_of_all_shops(api, draft_shop):
    r = api.get("/api/shops", headers=H)
    assert r.status_code in (404, 405)
    assert "Sample Bakery" not in r.text


def test_get_shop(api, draft_shop):
    r = api.get(f"/api/shops/{draft_shop.id}", headers=H)
    body = r.json()
    assert body["shop"]["auto_approve_limit"] == "150"
    assert [p["name"] for p in body["products"]] == ["Kuih Lapis"]
    assert body["links"] == {
        "ucp_profile": "https://kc.example.sg/.well-known/ucp",
        "mcp": "https://kc.example.sg/mcp",
        "public_page": "https://kc.example.sg/s/sample-bakery-ab12",
    }
    assert api.get("/api/shops/nope", headers=H).status_code == 401


def test_patch_shop_type(api, store, draft_shop):
    r = api.patch(f"/api/shops/{draft_shop.id}", json={"shop_type": "Home baker"}, headers=H)
    assert r.status_code == 200
    assert store.get_shop(draft_shop.id).shop_type == "Home baker"


def test_publish_makes_clean_unique_stable_slug(api, store, draft_shop):
    store.save_shop(Shop(slug="sample-bakery", name="Someone else"))
    r = api.post(f"/api/shops/{draft_shop.id}/publish", headers=H)
    assert r.status_code == 200
    body = r.json()
    owner = {"X-Owner-Key": body["owner_key"]}  # going live replaces the draft key
    assert body["shop"]["published"] is True
    assert body["shop"]["slug"] == "sample-bakery-2"
    assert body["links"]["public_page"].endswith("/s/sample-bakery-2")
    assert "shop_published" in audit_actions(store, draft_shop.id)

    # Renaming and publishing again keeps the live URL.
    api.patch(f"/api/shops/{draft_shop.id}", json={"name": "New Name"}, headers=owner)
    r = api.post(f"/api/shops/{draft_shop.id}/publish", headers=owner)
    assert r.json()["shop"]["slug"] == "sample-bakery-2"
    assert r.json()["owner_key"] is None  # the key is only shown once
    assert audit_actions(store, draft_shop.id).count("shop_published") == 1


def test_publish_needs_an_orderable_item(api, store):
    shop = give_key(store, store.save_shop(Shop(slug="empty-1", name="Empty")))
    store.save_product(Product(shop_id=shop.id, name="No price"))
    r = api.post(f"/api/shops/{shop.id}/publish", headers=H)
    assert r.status_code == 400
    assert "price" in r.json()["detail"]
    assert store.get_shop(shop.id).published is False


def photo():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40)).save(buf, "JPEG")
    return ("menu.jpg", buf.getvalue(), "image/jpeg")


def test_add_photos_appends_products(api, store, draft_shop, monkeypatch):
    async def fake(images, *, settings=None, client=None):
        return CatalogDraft(products=[DraftProduct(name="Ondeh Ondeh", base_price=Decimal("12.50"),
                                                   unit="10 pcs")])

    monkeypatch.setattr(ex, "extract_catalog_async", fake)
    r = api.post(f"/api/shops/{draft_shop.id}/photos", files=[("images", photo())], headers=H)
    assert r.status_code == 200, r.text
    assert [p["name"] for p in r.json()["products"]] == ["Ondeh Ondeh"]
    names = sorted(p.name for p in store.list_products(draft_shop.id))
    assert names == ["Kuih Lapis", "Ondeh Ondeh"]


def test_add_photos_friendly_error(api, draft_shop, monkeypatch):
    async def fail(images, *, settings=None, client=None):
        raise ex.CatalogExtractionError(ex.BUSY_ERROR)

    monkeypatch.setattr(ex, "extract_catalog_async", fail)
    r = api.post(f"/api/shops/{draft_shop.id}/photos", files=[("images", photo())], headers=H)
    assert r.status_code == 502
    assert r.json()["detail"] == ex.BUSY_ERROR


# --- products --------------------------------------------------------------------------

NEW_ITEM = {"name": " Ondeh Ondeh ", "category": "Kuih", "base_price": "12.50", "unit": "10 pcs",
            "options": [{"name": "Flavour", "choices": ["Pandan", " ", "Gula Melaka"]}]}


def test_product_crud_and_audit(api, store, draft_shop):
    r = api.post(f"/api/shops/{draft_shop.id}/products", json=NEW_ITEM, headers=H)
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["name"] == "Ondeh Ondeh"
    assert item["base_price"] == "12.50"
    assert item["options"][0]["choices"] == ["Pandan", "Gula Melaka"]

    lapis = next(p for p in store.list_products(draft_shop.id) if p.name == "Kuih Lapis")
    r = api.put(f"/api/shops/{draft_shop.id}/products/{lapis.id}", headers=H, json={
        "name": "Kuih Lapis", "category": "Kuih",
        "variants": [{"label": "20 pcs", "price": "16"}, {"label": "40 pcs", "price": "30.00"}],
    })
    assert r.status_code == 200
    assert r.json()["confidence"] == 1.0  # owner checked it
    assert [v["label"] for v in r.json()["variants"]] == ["20 pcs", "40 pcs"]

    r = api.delete(f"/api/shops/{draft_shop.id}/products/{item['id']}", headers=H)
    assert r.status_code == 204
    assert store.get_product(item["id"]) is None
    actions = audit_actions(store, draft_shop.id)
    assert {"product_created", "product_updated", "product_deleted"} <= set(actions)


def test_product_validation_and_ownership(api, store, draft_shop):
    r = api.post(f"/api/shops/{draft_shop.id}/products", json={"name": ""}, headers=H)
    assert r.status_code == 422
    r = api.post(f"/api/shops/{draft_shop.id}/products", json={"name": "X", "base_price": "-1"},
                 headers=H)
    assert r.status_code == 422

    other = store.save_shop(Shop(slug="other", name="Other"))
    theirs = store.save_product(Product(shop_id=other.id, name="Theirs", base_price=Decimal("1")))
    r = api.put(f"/api/shops/{draft_shop.id}/products/{theirs.id}", json={"name": "Mine"},
                headers=H)
    assert r.status_code == 404
    r = api.delete(f"/api/shops/{draft_shop.id}/products/{theirs.id}", headers=H)
    assert r.status_code == 404
    assert store.get_product(theirs.id).name == "Theirs"


# --- public page -----------------------------------------------------------------------

@pytest.fixture
def live_shop(store) -> Shop:
    shop = store.save_shop(Shop(slug="mak-kuih", name="Mak's Kuih", tagline="Fresh daily",
                                address="Blk 201, Tampines", phone="+65 6123 4567",
                                published=True))
    store.save_product(Product(shop_id=shop.id, name="Kuih Lapis </script><b>x", category="Kuih",
                               variants=[Variant(label="20 pcs", price=Decimal("16")),
                                         Variant(label="40 pcs", price=Decimal("30"))]))
    store.save_product(Product(shop_id=shop.id, name="Ondeh", base_price=Decimal("12.5"),
                               unit="10 pcs"))
    store.save_product(Product(shop_id=shop.id, name="Sold out", base_price=Decimal("5"),
                               available=False))
    return shop


def test_public_shop_json(api, live_shop):
    r = api.get("/api/public/shops/mak-kuih")  # no owner key
    assert r.status_code == 200
    body = r.json()
    assert "auto_approve_limit" not in body["shop"]
    assert "published" not in body["shop"]
    assert sorted(p["name"] for p in body["products"]) == ["Kuih Lapis </script><b>x", "Ondeh"]
    assert body["links"]["mcp"] == "https://kc.example.sg/mcp"


def test_public_shop_hides_drafts(api, draft_shop):
    assert api.get(f"/api/public/shops/{draft_shop.slug}").status_code == 404
    assert api.get("/api/public/shops/nope").status_code == 404


def jsonld(html: str) -> dict:
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert m, html
    return json.loads(m.group(1))


def test_public_page_has_jsonld(api, live_shop):
    r = api.get("/s/mak-kuih")
    assert r.status_code == 200
    html = r.text
    assert "<div id=root>" in html
    assert html.count("<title>") == 1
    assert "<title>Mak&#x27;s Kuih · KampungCart</title>" in html
    # The product name can't close the script element early.
    assert "</script><b>" not in html
    data = jsonld(html)
    assert data["@type"] == "Store"
    assert data["url"] == "https://kc.example.sg/s/mak-kuih"
    offers = data["hasOfferCatalog"]["itemListElement"]
    assert [(o["name"], o["price"], o["priceCurrency"]) for o in offers] == [
        ("20 pcs", "16.00", "SGD"), ("40 pcs", "30.00", "SGD"), ("10 pcs", "12.50", "SGD")]
    assert offers[0]["itemOffered"] == {"@type": "Product", "name": "Kuih Lapis </script><b>x",
                                        "category": "Kuih"}


def test_public_page_unknown_slug_is_plain_shell(api, draft_shop):
    for slug in ("nope", draft_shop.slug):
        r = api.get(f"/s/{slug}")
        assert r.status_code == 200
        assert "application/ld+json" not in r.text
        assert "<div id=root>" in r.text
