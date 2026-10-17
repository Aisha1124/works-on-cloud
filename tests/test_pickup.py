"""Pickup times: opening hours, minimum notice, daily capacity, pause; the weekly hours table;
the owner settings API and the shop page's slot list."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agents.commerce import pickup
from agents.risk.scorer import parse_hours
from backend.api.config import Settings
from backend.api.main import create_app
from backend.models import Order, OrderItem, OrderStatus, Product, Shop, Variant
from backend.timeutil import SGT
from tests.conftest import NOW, give_key

KEY = "kc_owner-key"
OWNER = {"X-Owner-Key": KEY}


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """October 2026 in Singapore. NOW is Thu 15 Oct 10:00."""
    return datetime(2026, 10, day, hour, minute, tzinfo=SGT)


def order_on(shop: Shop, when: datetime, status=OrderStatus.auto_approved) -> Order:
    return Order(shop_id=shop.id, total=Decimal("16"), customer_name="A",
                 customer_phone="+6591234567", pickup_at=when, channel="web", status=status,
                 items=[OrderItem(product_id="p", name="x", qty=1, unit_price=Decimal("16"),
                                  line_total=Decimal("16"))])


@pytest.fixture
def shop(store) -> Shop:
    return store.save_shop(Shop(slug="mak-kuih", name="Mak's Kuih", hours="Tue-Sun 9am-6pm"))


# --- pickup_problem -------------------------------------------------------------------------


def test_a_good_time_has_no_problem(store, shop):
    assert pickup.pickup_problem(store, shop, at(17, 10), NOW) is None


@pytest.mark.parametrize("when, words", [
    (at(15, 9), "must be in the future"),
    (at(16, 9, 30), "needs 24 hours' notice, so the earliest pickup is Fri 16 Oct 10:00"),
    (at(19, 10), "closed at Mon 19 Oct 10:00. Opening hours: Tue-Sun 9am-6pm"),
    (at(17, 18), "closed at Sat 17 Oct 18:00"),  # closing time itself is closed
])
def test_problems_in_plain_words(store, shop, when, words):
    assert words in pickup.pickup_problem(store, shop, when, NOW)


def test_minimum_notice_is_per_shop(store, shop):
    shop = shop.model_copy(update={"min_notice_hours": 2})
    assert pickup.pickup_problem(store, shop, at(15, 12), NOW) is None
    assert "needs 2 hours' notice" in pickup.pickup_problem(store, shop, at(15, 11), NOW)


def test_full_day(store, shop):
    shop = store.save_shop(shop.model_copy(update={"daily_capacity": 2}))
    store.save_order(order_on(shop, at(17, 10)))
    store.save_order(order_on(shop, at(17, 11), OrderStatus.rejected))  # doesn't count
    store.save_order(order_on(shop, at(17, 12), OrderStatus.cancelled))  # doesn't count
    assert pickup.pickup_problem(store, shop, at(17, 15), NOW) is None
    store.save_order(order_on(shop, at(17, 13), OrderStatus.pending_approval))
    assert "fully booked on Sat 17 Oct 2026" in pickup.pickup_problem(store, shop, at(17, 15), NOW)
    assert pickup.pickup_problem(store, shop, at(18, 15), NOW) is None


def test_pause_blocks_everything_until_the_date(store, shop):
    shop = shop.model_copy(update={"paused_until": date(2026, 10, 20)})
    problem = pickup.pickup_problem(store, shop, at(22, 10), NOW)
    assert problem == "Mak's Kuih is not taking orders until Tue 20 Oct 2026."
    assert pickup.next_slots(store, shop, NOW) == []
    assert pickup.available_days(store, shop, NOW) == []
    # On the date itself the pause is over.
    on_the_day = at(20, 8)
    assert pickup.paused_message(shop, on_the_day) == ""
    assert pickup.pickup_problem(store, shop, at(21, 10), on_the_day) is None


def test_unreadable_hours_mean_9_to_6_daily(store):
    shop = Shop(slug="x", name="X", hours="WhatsApp us to order")
    assert pickup.pickup_problem(store, shop, at(19, 10), NOW) is None  # a Monday
    assert "Opening hours: 9am-6pm daily" in pickup.pickup_problem(store, shop, at(19, 19), NOW)


def test_overnight_hours(store):
    supper = Shop(slug="s", name="Supper", hours="Daily 6pm-2am")
    assert pickup.pickup_problem(store, supper, at(17, 1, 30), NOW) is None
    assert pickup.pickup_problem(store, supper, at(17, 3), NOW) is not None


# --- next_slots and available_days ----------------------------------------------------------


def test_next_slots_start_at_the_requested_time(store, shop):
    assert [pickup.iso(s) for s in pickup.next_slots(store, shop, NOW, after=at(19, 10))] == [
        "2026-10-20T09:00", "2026-10-20T09:30", "2026-10-20T10:00"]


def test_next_slots_without_a_time_start_after_the_notice(store, shop):
    assert [pickup.iso(s) for s in pickup.next_slots(store, shop, NOW)] == [
        "2026-10-16T10:00", "2026-10-16T10:30", "2026-10-16T11:00"]


def test_next_slots_skip_full_days(store, shop):
    shop = store.save_shop(shop.model_copy(update={"daily_capacity": 1}))
    store.save_order(order_on(shop, at(16, 12)))
    assert pickup.iso(pickup.next_slots(store, shop, NOW)[0]) == "2026-10-17T09:00"


def test_available_days_for_the_shop_page(store, shop):
    days = pickup.available_days(store, shop, NOW, days=3)
    assert [d["label"] for d in days] == ["Fri 16 Oct", "Sat 17 Oct", "Sun 18 Oct"]
    assert days[0]["times"][0] == {"value": "2026-10-16T10:00", "label": "10:00"}
    assert days[0]["times"][-1]["label"] == "17:30"  # last slot before 6pm
    assert days[1]["times"][0]["label"] == "09:00" and len(days[1]["times"]) == 18
    shop = shop.model_copy(update={"daily_capacity": 1})
    store.save_order(order_on(shop, at(17, 10)))
    labels = [d["label"] for d in pickup.available_days(store, shop, NOW, days=3)]
    assert labels == ["Fri 16 Oct", "Sun 18 Oct", "Tue 20 Oct"]  # Sat full, Mon closed


# --- weekly hours table -----------------------------------------------------------------------


def table(**days):
    base = [{"day": d, "closed": False, "open": "09:00", "close": "18:00"} for d in range(7)]
    for name, spec in days.items():
        base[pickup.DAY_ABBR.index(name.title())] = {**base[0], "day": pickup.DAY_ABBR.index(
            name.title()), **spec}
    return base


@pytest.mark.parametrize("rows, text", [
    (table(), "Mon-Sun 9am-6pm"),
    (table(mon={"closed": True}), "Mon closed; Tue-Sun 9am-6pm"),
    (table(sat={"open": "08:30", "close": "13:00"}, sun={"closed": True}),
     "Mon-Fri 9am-6pm; Sat 8:30am-1pm; Sun closed"),
    (table(fri={"open": "18:00", "close": "02:00"}), "Mon-Thu 9am-6pm; Fri 6pm-2am; Sat-Sun 9am-6pm"),
    (table(wed={"open": "00:00", "close": "12:00"}), "Mon-Tue 9am-6pm; Wed 12am-12pm; Thu-Sun 9am-6pm"),
])
def test_week_table_round_trips_through_the_hours_text(rows, text):
    assert pickup.format_week(rows) == text
    assert parse_hours(text) is not None
    back = pickup.week_table(Shop(slug="x", name="X", hours=text))
    assert back == rows


# --- owner settings API -----------------------------------------------------------------------


@pytest.fixture
def app(tmp_path: Path, dist_dir: Path):
    return create_app(Settings(_env_file=None, data_dir=tmp_path / "data", dashboard_dist=dist_dir,
                               gemini_model=""))


@pytest.fixture
def api(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def live(app) -> Shop:
    store = app.state.store
    shop = store.save_shop(Shop(slug="mak-kuih", name="Mak's Kuih", hours="Tue-Sun 9am-6pm",
                                published=True))
    store.save_product(Product(id="lapis", shop_id=shop.id, name="Kuih Lapis",
                               variants=[Variant(label="20 pcs", price=Decimal("16"))]))
    return give_key(store, shop, KEY)


def test_shop_detail_has_the_weekly_table(api, live):
    detail = api.get(f"/api/shops/{live.id}", headers=OWNER).json()
    assert detail["hours_readable"] is True
    assert detail["opening_hours"][0] == {"day": 0, "closed": True, "open": "09:00",
                                          "close": "18:00"}
    assert detail["opening_hours"][1] == {"day": 1, "closed": False, "open": "09:00",
                                          "close": "18:00"}


def test_owner_saves_every_ordering_setting(api, app, live):
    r = api.patch(f"/api/shops/{live.id}", headers=OWNER, json={
        "opening_hours": table(sun={"closed": True}), "min_notice_hours": 48,
        "daily_capacity": 10, "approval_timeout_hours": 12, "cancel_cutoff_hours": 6,
        "auto_approve_limit": "200", "paused_until": "2026-12-01"})
    assert r.status_code == 200, r.text
    shop = app.state.store.get_shop(live.id)
    assert shop.hours == "Mon-Sat 9am-6pm; Sun closed"
    assert (shop.min_notice_hours, shop.daily_capacity, shop.approval_timeout_hours,
            shop.cancel_cutoff_hours) == (48, 10, 12, 6)
    assert shop.auto_approve_limit == Decimal("200") and shop.paused_until == date(2026, 12, 1)
    event = app.state.store.list_audit_events(live.id)[0]
    assert event.action == "shop_settings_updated" and "paused until" in event.summary
    # null clears the pause and the capacity; 0 capacity also means no limit.
    api.patch(f"/api/shops/{live.id}", headers=OWNER,
              json={"paused_until": None, "daily_capacity": 0})
    shop = app.state.store.get_shop(live.id)
    assert shop.paused_until is None and shop.daily_capacity is None


@pytest.mark.parametrize("body, words", [
    ({"opening_hours": table(**{d: {"closed": True} for d in
                                ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]})},
     "Open at least one day"),
    ({"opening_hours": table(mon={"open": "09:00", "close": "09:00"})}, "can't be the same"),
    ({"min_notice_hours": -1}, "min notice hours"),
    ({"approval_timeout_hours": 0}, "approval timeout hours"),
])
def test_bad_settings_are_refused(api, live, body, words):
    r = api.patch(f"/api/shops/{live.id}", headers=OWNER, json=body)
    assert r.status_code in (400, 422)
    assert words in (r.json()["detail"] if isinstance(r.json()["detail"], str)
                     else " ".join(" ".join(map(str, e["loc"])).replace("_", " ")
                                   for e in r.json()["detail"]))


def test_settings_need_the_owner(api, live):
    assert api.patch(f"/api/shops/{live.id}", json={"min_notice_hours": 1}).status_code == 401


# --- shop page --------------------------------------------------------------------------------


def test_shop_page_slots_and_pause(api, app, live):
    slots = api.get("/api/public/shops/mak-kuih/slots").json()
    assert slots["message"] == "" and slots["min_notice_hours"] == 24
    assert len(slots["days"]) == 14
    first = slots["days"][0]["times"][0]["value"]
    assert pickup.pickup_problem(app.state.store, live, datetime.fromisoformat(first)) is None

    until = date.today() + timedelta(days=10)
    app.state.store.save_shop(live.model_copy(update={"paused_until": until}))
    slots = api.get("/api/public/shops/mak-kuih/slots").json()
    assert slots["days"] == [] and slots["message"].startswith("Not taking orders until")
    page = api.get("/api/public/shops/mak-kuih").json()
    assert page["shop"]["ordering_message"] == slots["message"]
    text = api.get("/s/mak-kuih/llms.txt").text
    assert slots["message"] in text
    assert f"Mak's Kuih" in api.get("/llms.txt").text and slots["message"] in api.get("/llms.txt").text


def test_shop_page_order_is_idempotent(api, app, live):
    slot = api.get("/api/public/shops/mak-kuih/slots").json()["days"][1]["times"][0]["value"]
    body = {"items": [{"product_id": "lapis", "variant": "20 pcs", "qty": 1}],
            "customer_name": "Siti", "customer_phone": "+65 9123 4567", "pickup_time": slot,
            "idempotency_key": "tab-1"}
    first = api.post("/api/public/shops/mak-kuih/orders", json=body).json()
    again = api.post("/api/public/shops/mak-kuih/orders", json=body).json()
    assert first["order_id"] == again["order_id"]
    assert len(app.state.store.list_orders(live.id)) == 1
