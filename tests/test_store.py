from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.api.config import Settings
from backend.models import Order, OrderItem, OrderStatus, Product, Shop, Variant
from backend.store import FirestoreStore, LocalJsonStore, get_store


def _order(shop_id: str, status: str, created_at: datetime) -> Order:
    return Order(
        shop_id=shop_id,
        items=[
            OrderItem(
                product_id="p1", name="Kaya puff", qty=2,
                unit_price=Decimal("1.80"), line_total=Decimal("3.60"),
            )
        ],
        total=Decimal("3.60"),
        customer_name="Ravi",
        customer_phone="+6588887777",
        pickup_at=created_at + timedelta(days=1),
        channel="ucp",
        status=status,
        created_at=created_at,
    )


def test_shop_save_get_slug_and_persist(store, tmp_path):
    shop = store.save_shop(Shop(slug="ah-hock", name="Ah Hock Kopi"))
    assert store.get_shop(shop.id) == shop
    assert store.get_shop_by_slug("ah-hock") == shop
    assert store.get_shop_by_slug("nope") is None
    assert store.get_shop("missing") is None

    reopened = LocalJsonStore(tmp_path / "data")
    assert reopened.get_shop(shop.id) == shop


def test_products_filtered_by_shop_and_deleted(store):
    p1 = store.save_product(Product(
        shop_id="a", name="Kuih lapis", name_local="九层糕",
        variants=[Variant(label="10 pcs", price=Decimal("8.50"))],
    ))
    store.save_product(Product(shop_id="b", name="Other"))
    assert [p.id for p in store.list_products("a")] == [p1.id]
    assert store.get_product(p1.id).variants[0].price == Decimal("8.50")
    assert store.get_product(p1.id).name_local == "九层糕"

    assert store.delete_product(p1.id) is True
    assert store.delete_product(p1.id) is False
    assert store.list_products("a") == []


def test_orders_newest_first_and_status_filter(store):
    t0 = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
    old = store.save_order(_order("s", "auto_approved", t0))
    new = store.save_order(_order("s", "pending_approval", t0 + timedelta(hours=1)))
    store.save_order(_order("other", "pending_approval", t0))

    assert [o.id for o in store.list_orders("s")] == [new.id, old.id]
    held = store.list_orders("s", status=OrderStatus.pending_approval)
    assert [o.id for o in held] == [new.id]

    new.status = OrderStatus.approved
    store.save_order(new)
    assert store.get_order(new.id).status == OrderStatus.approved


def test_get_store_picks_backend(tmp_path):
    local = get_store(Settings(_env_file=None, data_dir=tmp_path))
    assert isinstance(local, LocalJsonStore)

    fs = get_store(Settings(_env_file=None, store_backend="firestore"))
    assert isinstance(fs, FirestoreStore)
    with pytest.raises(NotImplementedError):
        fs.list_shops()
