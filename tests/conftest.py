from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agents import gemini
from agents.shopper import assistant
from backend import mailer
from backend.api.config import Settings
from backend.api.main import create_app
from backend.models import Product, ProductOption, Shop, Variant
from backend.owner_auth import hash_owner_key
from backend.store import LocalJsonStore
from backend.timeutil import SGT


@pytest.fixture(autouse=True)
def no_live_gemini(monkeypatch):
    """Tests never reach the real Gemini API (free tier: 20 calls a day).
    Code that would build a real client gets GeminiNotConfigured instead; tests that need
    Gemini pass a fake client (tests/gemini_fake.py)."""

    def refuse(settings):
        raise gemini.GeminiNotConfigured("live Gemini is disabled in tests")

    monkeypatch.setattr(gemini, "make_client", refuse)
    # The shop assistant's ADK model too (tests/test_shop_assistant.py passes a fake one).
    monkeypatch.setattr(assistant, "make_model", refuse)


TEST_OWNER_KEY = "kc_test-owner-key"


def give_key(store, shop: Shop, key: str = TEST_OWNER_KEY) -> Shop:
    """Make `key` this shop's owner key (only the hash is stored)."""
    store.set_owner_key_hash(shop.id, hash_owner_key(key))
    return shop


class FakeMailer:
    """Records emails instead of sending them. `fail` makes every send raise."""

    def __init__(self):
        self.sent = []
        self.fail = False

    async def send(self, email):
        if self.fail:
            raise RuntimeError("Resend HTTP 500: simulated outage")
        self.sent.append(email)


@pytest.fixture(autouse=True)
def mail(monkeypatch) -> FakeMailer:
    """Tests never send real email (even if .env has RESEND_API_KEY)."""
    fake = FakeMailer()
    monkeypatch.setattr(mailer, "get_mailer", lambda settings: fake)
    return fake


@pytest.fixture
def store(tmp_path: Path) -> LocalJsonStore:
    return LocalJsonStore(tmp_path / "data")


@pytest.fixture
def dist_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('hi')", encoding="utf-8")
    return dist


@pytest.fixture
def client(tmp_path: Path, dist_dir: Path) -> TestClient:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", dashboard_dist=dist_dir)
    return TestClient(create_app(settings))


# --- A demo shop for commerce, risk and approval tests --------------------------------

# Thursday 15 Oct 2026, 10:00 in Singapore. Pickup is Saturday 10:00 unless a test says otherwise.
NOW = datetime(2026, 10, 15, 10, 0, tzinfo=SGT)
SATURDAY_10AM = datetime(2026, 10, 17, 10, 0, tzinfo=SGT)
GOOD_PHONE = "+65 9123 4567"


@dataclass
class DemoShop:
    shop: Shop
    lapis: Product  # several packs (variants)
    banana: Product  # one pack: base_price + unit
    ondeh: Product  # one pack with a flavour option
    soldout: Product


@pytest.fixture
def demo(store) -> DemoShop:
    shop = store.save_shop(Shop(slug="mak-kuih", name="Mak's Kuih", hours="Tue-Sun 9am-6pm"))
    lapis = store.save_product(Product(
        shop_id=shop.id, name="Kuih Lapis", category="Kuih",
        variants=[Variant(label="20 pcs", price=Decimal("16")),
                  Variant(label="40 pcs", price=Decimal("30"))],
    ))
    banana = store.save_product(Product(
        shop_id=shop.id, name="Mini Banana Cake", category="Cakes",
        base_price=Decimal("24"), unit="24 pcs",
    ))
    ondeh = store.save_product(Product(
        shop_id=shop.id, name="Ondeh Ondeh", category="Kuih", base_price=Decimal("12.50"),
        unit="10 pcs", options=[ProductOption(name="Flavour", choices=["Pandan", "Gula Melaka"])],
    ))
    soldout = store.save_product(Product(
        shop_id=shop.id, name="Kueh Salat", base_price=Decimal("20"), unit="1 tray",
        available=False,
    ))
    return DemoShop(shop, lapis, banana, ondeh, soldout)


@pytest.fixture
def gemini_settings() -> Settings:
    """Settings with a model name but no key: only an explicitly passed fake client is used."""
    return Settings(_env_file=None, gemini_model="test-model")
