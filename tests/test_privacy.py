"""Customer details are erased 90 days after pickup; the /privacy page gets its contact."""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from backend import privacy
from backend.api.config import Settings
from backend.api.main import create_app, sweep_once
from backend.models import (
    CheckoutBuyer, CheckoutLine, CheckoutSession, Order, OrderItem, Shop, utc_now,
)


def order(shop: Shop, pickup_days_ago: int) -> Order:
    return Order(shop_id=shop.id, total=Decimal("16"), customer_name="Siti Rahman",
                 customer_phone="+6591234567", customer_email="siti@example.sg",
                 note="Ring the bell", pickup_at=utc_now() - timedelta(days=pickup_days_ago),
                 channel="web", status="done",
                 items=[OrderItem(product_id="p", name="Kuih Lapis", qty=1,
                                  unit_price=Decimal("16"), line_total=Decimal("16"))])


def test_details_are_erased_90_days_after_pickup(store):
    shop = store.save_shop(Shop(slug="s", name="S"))
    old = store.save_order(order(shop, 91))
    recent = store.save_order(order(shop, 89))
    assert privacy.erase_old_personal_data(store, shop) == 1
    erased = store.get_order(old.id)
    assert (erased.customer_name, erased.customer_phone, erased.customer_email, erased.note) == (
        "(erased)", "", "", "")
    assert erased.personal_data_erased and erased.total == Decimal("16.00")  # records still add up
    assert erased.items[0].name == "Kuih Lapis"
    assert store.get_order(recent.id).customer_phone == "+6591234567"
    event = store.list_audit_events(shop.id)[0]
    assert event.action == "personal_data_erased" and event.actor == "system"
    assert privacy.erase_old_personal_data(store, shop) == 0  # runs once per order


def test_old_ucp_checkouts_lose_their_buyer(store):
    shop = store.save_shop(Shop(slug="s", name="S"))
    lines = [CheckoutLine(id="li_1", item_id="p", quantity=1)]
    buyer = CheckoutBuyer(first_name="Siti", phone_number="+6591234567", email="s@x.sg")
    old = store.save_checkout(CheckoutSession(shop_id=shop.id, lines=lines, buyer=buyer,
                                              note="hi",
                                              updated_at=utc_now() - timedelta(days=91)))
    new = store.save_checkout(CheckoutSession(shop_id=shop.id, lines=lines, buyer=buyer))
    privacy.erase_old_personal_data(store, shop)
    assert store.get_checkout(old.id).buyer == CheckoutBuyer() and store.get_checkout(old.id).note == ""
    assert store.get_checkout(new.id).buyer == buyer


def test_sweep_erases_too(tmp_path: Path, dist_dir: Path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path / "data", dashboard_dist=dist_dir))
    store = app.state.store
    shop = store.save_shop(Shop(slug="s", name="S"))
    old = store.save_order(order(shop, 100))
    sweep_once(store, app.state.settings)
    assert store.get_order(old.id).personal_data_erased


def test_site_info_for_the_privacy_page(tmp_path: Path, dist_dir: Path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path / "data", dashboard_dist=dist_dir,
                              admin_email="help@kampungcart.example"))
    info = TestClient(app).get("/api/public/site").json()
    assert info == {"admin_email": "help@kampungcart.example", "retention_days": 90}
