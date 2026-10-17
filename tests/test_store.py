"""Every Store method, run against both backends: LocalJsonStore, and FirestoreStore on the
Firestore emulator. The Firestore runs are skipped unless FIRESTORE_EMULATOR_HOST is set
(start it with scripts/firestore_emulator.ps1). Each Firestore test uses its own project id, so
tests never see each other's data."""

import os
import threading
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.api.config import Settings
from backend.models import (
    AuditEvent, CheckoutBuyer, CheckoutLine, CheckoutSession, Order, OrderItem, OrderStatus,
    Product, Shop, Variant,
)
from backend.store import FirestoreStore, LocalJsonStore, get_store

EMULATOR = os.environ.get("FIRESTORE_EMULATOR_HOST")


@pytest.fixture(params=["local", "firestore"])
def make_store(request, tmp_path):
    """-> a function that opens the same store again (to check data survives a restart)."""
    if request.param == "local":
        return lambda: LocalJsonStore(tmp_path / "data")
    if not EMULATOR:
        pytest.skip("Firestore emulator not running (set FIRESTORE_EMULATOR_HOST)")
    project = f"kc-test-{uuid.uuid4().hex[:10]}"
    return lambda: FirestoreStore(project)


@pytest.fixture
def store(make_store):
    return make_store()


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


# --- shops ------------------------------------------------------------------------------------


def test_shop_save_get_slug_and_persist(store, make_store):
    shop = store.save_shop(Shop(slug="ah-hock", name="Ah Hock Kopi", owner_email="ah@hock.sg",
                                paused_until=datetime(2026, 11, 1).date(), daily_capacity=5))
    assert store.get_shop(shop.id) == shop
    assert store.get_shop_by_slug("ah-hock") == shop
    assert store.get_shop_by_slug("nope") is None
    assert store.get_shop("missing") is None
    assert make_store().get_shop(shop.id) == shop  # survives a restart / redeploy


def test_list_shops_keeps_insertion_order_and_finds_by_email(store):
    a = store.save_shop(Shop(slug="a", name="A", owner_email="o@x.sg"))
    b = store.save_shop(Shop(slug="b", name="B"))
    c = store.save_shop(Shop(slug="c", name="C", owner_email="o@x.sg"))
    store.save_shop(a.model_copy(update={"name": "A2"}))  # an update keeps its place
    assert [s.slug for s in store.list_shops()] == ["a", "b", "c"]
    assert [s.id for s in store.find_shops_by_owner_email("o@x.sg")] == [a.id, c.id]
    assert store.find_shops_by_owner_email("") == [] and b.owner_email == ""


def test_owner_key_hashes(store):
    assert store.get_owner_key_hash("s1") is None
    store.set_owner_key_hash("s1", "hash-1")
    store.set_owner_key_hash("s1", "hash-2")  # one key per shop: replaced
    assert store.get_owner_key_hash("s1") == "hash-2"
    assert store.find_shop_by_owner_key_hash("hash-2") == "s1"
    assert store.find_shop_by_owner_key_hash("hash-1") is None


# --- secrets, claims, rate limits -------------------------------------------------------------


def test_secrets_put_get_pop_once(store):
    store.put_secret("sessions", "h1", {"shop_id": "s1", "expires_at": "2026-11-01T00:00:00+00:00"})
    assert store.get_secret("sessions", "h1")["shop_id"] == "s1"
    assert store.pop_secret("sessions", "h1")["shop_id"] == "s1"
    assert store.pop_secret("sessions", "h1") is None
    assert store.get_secret("sessions", "h1") is None


def test_pop_secret_is_single_use_under_concurrency(store):
    store.put_secret("link_tokens", "t1", {"shop_id": "s1"})
    results = []
    threads = [threading.Thread(target=lambda: results.append(store.pop_secret("link_tokens", "t1")))
               for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [r for r in results if r] == [{"shop_id": "s1"}]


def test_claim_creates_once(store):
    assert store.claim("idempotency_keys", "k", {"order_id": ""}) is None
    assert store.claim("idempotency_keys", "k", {"order_id": "other"}) == {"order_id": ""}
    store.put_secret("idempotency_keys", "k", {"order_id": "o1"})
    assert store.claim("idempotency_keys", "k", {"order_id": ""}) == {"order_id": "o1"}


def test_rate_limit_window_starts_at_first_hit(store):
    assert [store.take_rate("k", 2, 60, 1000 + i) for i in range(3)] == [True, True, False]
    assert store.take_rate("k", 2, 60, 1059, consume=False) is False  # still blocked
    assert store.take_rate("other", 2, 60, 1001) is True  # keys are separate
    assert store.take_rate("k", 2, 60, 1060) is True  # new window
    assert store.take_rate("k", 2, 60, 1061, consume=False) is True  # peeking counts nothing
    assert store.take_rate("k", 2, 60, 1061) is True
    assert store.take_rate("k", 2, 60, 1062) is False


def test_store_rate_limits_are_shared_between_instances(make_store):
    from backend.external import StoreRateLimiter

    clock = iter(range(100, 200)).__next__
    first = StoreRateLimiter(make_store(), "orders", 2, 60, clock=clock)
    second = StoreRateLimiter(make_store(), "orders", 2, 60, clock=clock)
    assert first.allow("203.0.113.7") and second.allow("203.0.113.7")
    assert not first.allow("203.0.113.7") and second.blocked("203.0.113.7")


def test_rate_limit_keys_are_stored_hashed(tmp_path):
    from backend.external import StoreRateLimiter

    StoreRateLimiter(LocalJsonStore(tmp_path / "d"), "orders", 2, 60).allow("203.0.113.7")
    assert "203.0.113.7" not in (tmp_path / "d" / "rate_limits.json").read_text(encoding="utf-8")


# --- products -------------------------------------------------------------------------------


def test_products_filtered_by_shop_in_menu_order_and_deleted(store):
    p1 = store.save_product(Product(
        shop_id="a", name="Kuih lapis", name_local="九层糕",
        variants=[Variant(label="10 pcs", price=Decimal("8.50"))],
    ))
    p2 = store.save_product(Product(shop_id="a", name="Ang ku kueh", base_price=Decimal("1.2")))
    store.save_product(Product(shop_id="b", name="Other"))
    store.save_product(p1.model_copy(update={"name": "Kuih Lapis"}))  # edit keeps its place
    assert [p.id for p in store.list_products("a")] == [p1.id, p2.id]
    assert store.get_product(p1.id).variants[0].price == Decimal("8.50")
    assert store.get_product(p1.id).name_local == "九层糕"
    assert store.get_product(p2.id).base_price == Decimal("1.2")

    assert store.delete_product(p1.id) is True
    assert store.delete_product(p1.id) is False
    assert [p.id for p in store.list_products("a")] == [p2.id]


# --- orders ---------------------------------------------------------------------------------


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
    assert store.get_order(new.id).total == Decimal("3.60")


def test_orders_with_the_same_time_are_newest_inserted_first(store):
    t0 = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
    first = store.save_order(_order("s", "auto_approved", t0))
    second = store.save_order(_order("s", "auto_approved", t0))
    assert [o.id for o in store.list_orders("s")] == [second.id, first.id]


def test_transition_order_only_from_the_expected_status(store):
    order = store.save_order(_order("s", "pending_approval", datetime(2026, 10, 15, tzinfo=UTC)))
    done = store.transition_order(order.id, {OrderStatus.pending_approval},
                                  {"status": OrderStatus.rejected, "rejection_reason": "No"})
    assert done.status == OrderStatus.rejected and done.rejection_reason == "No"
    assert store.get_order(order.id) == done
    assert store.transition_order(order.id, {OrderStatus.pending_approval},
                                  {"status": OrderStatus.approved}) is None
    assert store.get_order(order.id).status == OrderStatus.rejected
    assert store.transition_order("missing", {OrderStatus.pending_approval}, {}) is None


def test_transition_order_has_one_winner_under_concurrency(store):
    order = store.save_order(_order("s", "pending_approval", datetime(2026, 10, 15, tzinfo=UTC)))
    results = []

    def decide(status):
        results.append(store.transition_order(order.id, {OrderStatus.pending_approval},
                                              {"status": status}))

    threads = [threading.Thread(target=decide, args=(s,)) for s in
               [OrderStatus.approved, OrderStatus.rejected] * 3]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    winners = [r for r in results if r is not None]
    assert len(winners) == 1 and store.get_order(order.id).status == winners[0].status


# --- checkouts and audit --------------------------------------------------------------------


def test_checkouts(store):
    lines = [CheckoutLine(id="li_1", item_id="p.v0", quantity=2, options={"Flavour": "Pandan"})]
    c = store.save_checkout(CheckoutSession(shop_id="s", lines=lines,
                                            buyer=CheckoutBuyer(first_name="Siti")))
    store.save_checkout(CheckoutSession(shop_id="other", lines=lines))
    assert store.get_checkout(c.id) == c
    assert store.get_checkout("missing") is None
    assert [x.id for x in store.list_checkouts("s")] == [c.id]


def test_audit_newest_first_with_paging(store):
    t0 = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
    events = [store.add_audit_event(AuditEvent(
        shop_id="s", at=t0 + timedelta(seconds=i // 2, microseconds=0 if i % 3 else 500),
        actor="system", action=f"a{i}", entity_type="shop", entity_id="s", summary=f"e{i}",
        details={"n": i, "nested": {"ok": True}})) for i in range(6)]
    store.add_audit_event(AuditEvent(shop_id="other", actor="system", action="x",
                                     entity_type="shop", entity_id="o", summary="x"))
    got = store.list_audit_events("s")
    expected = sorted(range(6), key=lambda i: (events[i].at, i), reverse=True)
    assert [e.action for e in got] == [f"a{i}" for i in expected]
    assert got[0].details["nested"] == {"ok": True}
    assert [e.action for e in store.list_audit_events("s", limit=2, offset=1)] == [
        f"a{i}" for i in expected[1:3]]


def test_get_store_picks_backend(tmp_path):
    local = get_store(Settings(_env_file=None, data_dir=tmp_path))
    assert isinstance(local, LocalJsonStore)
    fs = get_store(Settings(_env_file=None, store_backend="firestore", gcp_project_id="p",
                            firestore_database="kc-db"))
    assert isinstance(fs, FirestoreStore)
    assert (fs.project_id, fs.database) == ("p", "kc-db")
