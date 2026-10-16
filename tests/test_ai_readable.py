"""AI-readable shop pages: schema.org JSON-LD on /s/{slug} and plain-text llms.txt files,
server-rendered so crawlers that don't run JavaScript can read the menu."""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import ai_readable
from backend.api.config import Settings
from backend.api.main import create_app
from backend.models import Product, ProductOption, Shop, Variant

BASE = "https://kc.example.sg"


@pytest.fixture
def app(tmp_path: Path, dist_dir: Path):
    (dist_dir / "index.html").write_text(
        "<!doctype html><html><head><title>KampungCart</title></head><body><div id=root></div>"
        "</body></html>", encoding="utf-8")
    return create_app(Settings(_env_file=None, data_dir=tmp_path / "data",
                               dashboard_dist=dist_dir, base_url=BASE))


@pytest.fixture
def api(app) -> TestClient:
    return TestClient(app, base_url=BASE)


@pytest.fixture
def store(app):
    return app.state.store


@pytest.fixture
def bakery(store) -> Shop:
    shop = store.save_shop(Shop(slug="mak-kuih", name="Mak's Kuih", shop_type="Home baker",
                                address="Tampines, Singapore", phone="+65 0000 0000",
                                hours="Tue-Sun 9am-6pm", published=True, example=True))
    store.save_product(Product(shop_id=shop.id, name="Kuih Lapis", name_local="九层糕",
                               category="Kuih",
                               variants=[Variant(label="20 pcs", price=Decimal("16")),
                                         Variant(label="40 pcs", price=Decimal("30"))]))
    store.save_product(Product(shop_id=shop.id, name="Ondeh Ondeh", category="Kuih",
                               base_price=Decimal("12.5"), unit="10 pcs",
                               options=[ProductOption(name="Flavour",
                                                      choices=["Pandan", "Gula Melaka"])]))
    store.save_product(Product(shop_id=shop.id, name="Pandan Chiffon", category="Cakes",
                               base_price=Decimal("18")))
    store.save_product(Product(shop_id=shop.id, name="Sold out tart", category="Cakes",
                               base_price=Decimal("9"), available=False))
    return shop


@pytest.fixture
def hawker(store) -> Shop:
    shop = store.save_shop(Shop(slug="ah-hock", name="Ah Hock Noodles", shop_type="Hawker stall",
                                hours="Mon-Fri 7am-2pm, Sat 7am-12pm, Sun closed",
                                published=True))
    store.save_product(Product(shop_id=shop.id, name="Fishball Noodles", base_price=Decimal("4")))
    return shop


@pytest.fixture
def draft(store) -> Shop:
    return store.save_shop(Shop(slug="secret-draft", name="Secret Draft"))


def jsonld(html: str) -> dict:
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert m, html
    return json.loads(m.group(1))  # valid JSON, or this raises


def stored_prices(store, shop) -> list[tuple[str, str, str]]:
    """(item, pack label, price) for every available item, straight from the store."""
    out = []
    for p in store.list_products(shop.id):
        if p.available:
            out += [(p.name, label, f"{price:.2f}") for label, price in ai_readable.prices(p)]
    return out


def test_jsonld_matches_the_stored_menu(api, store, bakery):
    html = api.get("/s/mak-kuih").text
    data = jsonld(html)
    assert data["@context"] == "https://schema.org"
    assert data["@type"] == "Bakery"
    assert data["name"] == "Mak's Kuih"
    assert data["telephone"] == "+65 0000 0000"
    assert data["address"] == {"@type": "PostalAddress", "streetAddress": "Tampines, Singapore",
                               "addressCountry": "SG"}
    menu = data["hasMenu"]
    assert menu["@type"] == "Menu"
    assert [s["@type"] for s in menu["hasMenuSection"]] == ["MenuSection", "MenuSection"]
    from_page = [(item["name"], o.get("name", ""), o["price"])
                 for s in menu["hasMenuSection"] for item in s["hasMenuItem"]
                 for o in item["offers"]]
    assert from_page == stored_prices(store, bakery)
    assert "Sold out tart" not in html
    for s in menu["hasMenuSection"]:
        for item in s["hasMenuItem"]:
            assert item["@type"] == "MenuItem"
            assert all(o["@type"] == "Offer" and o["priceCurrency"] == "SGD"
                       for o in item["offers"])


def test_jsonld_opening_hours(api, bakery, hawker):
    spec = jsonld(api.get("/s/mak-kuih").text)["openingHoursSpecification"]
    assert spec == [{"@type": "OpeningHoursSpecification",
                     "dayOfWeek": ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
                                   "Sunday"], "opens": "09:00", "closes": "18:00"}]
    data = jsonld(api.get("/s/ah-hock").text)
    assert data["@type"] == "FoodEstablishment"
    assert [(s["dayOfWeek"], s["opens"], s["closes"])
            for s in data["openingHoursSpecification"]] == [
        (["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "07:00", "14:00"),
        (["Saturday"], "07:00", "12:00")]


def test_unreadable_hours_are_left_out():
    assert ai_readable.opening_hours_spec("whenever we feel like it") == []
    assert ai_readable.opening_hours_spec("") == []


def test_shop_page_links_llms_txt_in_head(api, bakery):
    html = api.get("/s/mak-kuih").text
    head = html[:html.index("</head>")]
    assert ('<link rel="alternate" type="text/plain" title="llms.txt" '
            'href="/s/mak-kuih/llms.txt">') in head
    assert '<script type="application/ld+json">' in head
    assert html.count("<title>") == 1


def test_shop_llms_txt_prices_match_the_stored_menu(api, store, bakery):
    r = api.get("/s/mak-kuih/llms.txt")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/plain; charset=utf-8"
    text = r.text
    assert text.startswith("# Mak's Kuih\n")
    assert "This is an example shop for demonstration." in text
    for name, label, price in stored_prices(store, bakery):
        line = next(ln for ln in text.splitlines() if ln.startswith(f"- {name}"))
        assert (f"{label} S${price}" if label else f"S${price}") in line
    assert "- Kuih Lapis (九层糕): 20 pcs S$16.00, 40 pcs S$30.00" in text
    assert "- Ondeh Ondeh: 10 pcs S$12.50. Flavour: Pandan / Gula Melaka" in text
    assert "Sold out tart" not in text
    assert "Tue-Sun 9am-6pm" in text
    assert "## Pickup rules" in text and "Pay at pickup" in text
    assert f"{BASE}/s/mak-kuih" in text and f"{BASE}/mcp" in text
    assert f"{BASE}/.well-known/ucp" in text


def test_llms_txt_example_line_only_for_the_example_shop(api, bakery, hawker):
    assert "example shop" not in api.get("/s/ah-hock/llms.txt").text


def test_site_llms_txt_lists_published_shops_only(api, bakery, hawker, draft):
    r = api.get("/llms.txt")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/plain; charset=utf-8"
    assert f"[Mak's Kuih]({BASE}/s/mak-kuih/llms.txt)" in r.text
    assert f"[Ah Hock Noodles]({BASE}/s/ah-hock/llms.txt)" in r.text
    assert "Secret Draft" not in r.text and "secret-draft" not in r.text
    assert f"{BASE}/mcp" in r.text


def test_llms_txt_unknown_or_draft_shop_is_404(api, draft):
    assert api.get("/s/nope/llms.txt").status_code == 404
    assert api.get("/s/secret-draft/llms.txt").status_code == 404
