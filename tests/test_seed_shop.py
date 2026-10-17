"""The container seeds the sample shop at startup (Dockerfile CMD), so it must work on an
empty store and again on a seeded one."""

import importlib.util
from pathlib import Path

from backend.store import LocalJsonStore

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seed_shop.py"


def load_seed():
    spec = importlib.util.spec_from_file_location("seed_shop", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_creates_published_mak_kuih_and_is_repeatable(tmp_path, monkeypatch):
    store = LocalJsonStore(tmp_path)
    seed = load_seed()
    monkeypatch.setattr(seed, "get_store", lambda settings: store)
    seed.main()
    seed.main()

    shop = store.get_shop_by_slug("mak-kuih")
    assert shop is not None and shop.published
    assert "demo" not in shop.name.lower() and "demo" not in shop.id
    # Clearly an example, not a real business.
    assert shop.example is True
    assert shop.phone == "+65 0000 0000"
    assert shop.address == "Tampines, Singapore"
    products = store.list_products(shop.id)
    assert sorted(p.id for p in products) == ["kuih-lapis", "ondeh-ondeh"]
    assert len(store.list_shops()) == 1


def test_seed_never_overwrites_an_existing_shop(tmp_path, monkeypatch):
    store = LocalJsonStore(tmp_path)
    seed = load_seed()
    monkeypatch.setattr(seed, "get_store", lambda settings: store)
    seed.main()
    shop = store.get_shop("mak-kuih")
    # The owner edits things after the first deploy.
    store.save_shop(shop.model_copy(update={"hours": "Daily 8am-8pm", "daily_capacity": 3}))
    lapis = store.get_product("kuih-lapis")
    store.save_product(lapis.model_copy(update={"available": False}))
    store.delete_product("ondeh-ondeh")
    seed.main()  # the next deploy
    assert store.get_shop("mak-kuih").hours == "Daily 8am-8pm"
    assert store.get_shop("mak-kuih").daily_capacity == 3
    assert store.get_product("kuih-lapis").available is False
    assert store.get_product("ondeh-ondeh") is None
