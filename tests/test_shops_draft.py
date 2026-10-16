import io
import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from agents.catalog import extract as ex
from agents.catalog.schema import CatalogDraft, DraftProduct
from backend.api.config import Settings
from backend.api.main import create_app
from backend.models import Actor, Variant

KEY = "kc_unused"  # drafts need no key; any header is ignored


@pytest.fixture
def app(tmp_path: Path, dist_dir: Path):
    settings = Settings(
        _env_file=None, data_dir=tmp_path / "data", uploads_dir=tmp_path / "uploads",
        dashboard_dist=dist_dir, owner_key=KEY, gemini_model="test-model",
    )
    return create_app(settings)


@pytest.fixture
def api(app) -> TestClient:
    return TestClient(app)


def photo() -> tuple[str, bytes, str]:
    buf = io.BytesIO()
    Image.new("RGB", (40, 40)).save(buf, "JPEG")
    return ("menu.jpg", buf.getvalue(), "image/jpeg")


DRAFT = CatalogDraft(
    shop_name_guess="Sample Bakery",
    categories=["Mini Cake Platters"],
    products=[
        DraftProduct(name="Mini Banana Cake", category="Mini Cake Platters",
                     base_price=Decimal("24"), unit="24 pcs"),
        DraftProduct(name="Kuih Lapis", variants=[Variant(label="20 pcs", price=Decimal("16"))]),
    ],
    warnings=["Kuih Lapis: blurry"],
)


@pytest.fixture
def fake_extract(monkeypatch):
    calls = []

    async def fake(images, *, settings=None, client=None, preprocessed=False):
        calls.append(images)
        return DRAFT

    monkeypatch.setattr(ex, "extract_catalog_async", fake)
    return calls


def test_draft_needs_no_key_and_returns_a_draft_key_for_that_shop_only(api, app, fake_extract):
    r = api.post("/api/shops/draft", files=[("images", photo())])
    assert r.status_code == 200, r.text
    body = r.json()
    key, shop_id = body["draft_key"], body["shop"]["id"]
    assert key.startswith("kc_") and len(key) > 40
    # Only the hash is stored, and never on the shop itself.
    store = app.state.store
    assert store.get_owner_key_hash(shop_id) != key
    assert key not in json.dumps(store.get_shop(shop_id).model_dump(mode="json"))
    assert api.get(f"/api/shops/{shop_id}", headers={"X-Owner-Key": key}).status_code == 200
    other = api.post("/api/shops/draft", files=[("images", photo())]).json()["shop"]["id"]
    assert api.get(f"/api/shops/{other}", headers={"X-Owner-Key": key}).status_code == 401


def test_new_drafts_are_rate_limited_per_client(api, fake_extract):
    codes = [api.post("/api/shops/draft", files=[("images", photo())]).status_code
             for _ in range(6)]
    assert codes == [200] * 5 + [429]
    assert len(fake_extract) == 5


@pytest.mark.parametrize("count", [0, 6])
def test_draft_needs_one_to_five_images(api, fake_extract, count):
    r = api.post("/api/shops/draft", files=[("images", photo()) for _ in range(count)],
                 data={} if count else {"x": "1"}, headers={"X-Owner-Key": KEY})
    assert r.status_code == 400
    assert "1 to 5" in r.json()["detail"]


def test_draft_creates_shop_products_images_and_audit(api, app, fake_extract, tmp_path):
    r = api.post("/api/shops/draft", files=[("images", photo()), ("images", photo())],
                 headers={"X-Owner-Key": KEY})
    assert r.status_code == 200, r.text
    body = r.json()

    shop = body["shop"]
    assert shop["name"] == "Sample Bakery"
    assert shop["slug"].startswith("sample-bakery-")
    assert shop["published"] is False
    assert [p["name"] for p in body["products"]] == ["Mini Banana Cake", "Kuih Lapis"]
    assert body["products"][0]["base_price"] == "24"
    assert body["warnings"] == ["Kuih Lapis: blurry"]
    assert len(fake_extract[0]) == 2

    store = app.state.store
    assert len(store.list_products(shop["id"])) == 2
    assert len(list((tmp_path / "uploads" / shop["id"]).glob("*.jpg"))) == 2

    [event] = store.list_audit_events(shop["id"])
    assert event.actor == Actor.catalog_agent
    assert event.action == "catalog_extracted"
    assert event.summary == "Read 2 items from 2 photo(s)"
    assert event.details["model"] == "test-model"


def test_draft_extraction_failure_is_friendly(api, monkeypatch):
    async def boom(images, **kwargs):
        raise ex.CatalogExtractionError()

    monkeypatch.setattr(ex, "extract_catalog_async", boom)
    r = api.post("/api/shops/draft", files=[("images", photo())], headers={"X-Owner-Key": KEY})
    assert r.status_code == 502
    assert r.json() == {"detail": ex.FRIENDLY_ERROR}


def test_draft_bad_image_is_400(api):
    r = api.post("/api/shops/draft", files=[("images", ("menu.jpg", b"not an image", "image/jpeg"))],
                 headers={"X-Owner-Key": KEY})
    assert r.status_code == 400
    assert "doesn't look like a photo" in r.json()["detail"]
