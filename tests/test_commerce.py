from decimal import Decimal

import pytest

from agents.commerce import service as commerce
from agents.commerce.service import OrderValidationError
from backend.models import Actor, Channel


def quote(store, demo, *items):
    return commerce.get_quote(store, demo.shop.id, list(items))


# --- search -------------------------------------------------------------------------


def test_search_matches_name_and_category_and_hides_unavailable(store, demo):
    assert [p.name for p in commerce.search_products(store, demo.shop.id, "lapis")] == ["Kuih Lapis"]
    assert {p.name for p in commerce.search_products(store, demo.shop.id, "", "kuih")} == {
        "Kuih Lapis", "Ondeh Ondeh"}
    assert commerce.search_products(store, demo.shop.id, "salat") == []
    assert len(commerce.search_products(store, demo.shop.id)) == 3


# --- pricing ------------------------------------------------------------------------


def test_single_pack_product_uses_base_price_and_unit(store, demo):
    q = quote(store, demo, {"product_id": demo.banana.id, "qty": 3})
    [line] = q.items
    assert line.variant == "24 pcs"
    assert line.unit_price == Decimal("24.00")
    assert line.line_total == Decimal("72.00")
    assert q.total == Decimal("72.00")
    assert isinstance(q.total, Decimal)
    assert not q.price_mismatch


def test_single_pack_accepts_its_own_unit_as_variant(store, demo):
    q = quote(store, demo, {"product_id": demo.banana.id, "variant": "24PCS", "qty": 1})
    assert q.items[0].variant == "24 pcs"


def test_multi_variant_product_prices_each_variant(store, demo):
    q = quote(
        store, demo,
        {"product_id": demo.lapis.id, "variant": "20 pcs", "qty": 2},
        {"product_id": demo.lapis.id, "variant": "40pcs", "qty": 1},
        {"product_id": demo.ondeh.id, "options": {"flavour": "pandan"}, "qty": 3},
    )
    assert [(i.variant, i.unit_price, i.line_total) for i in q.items] == [
        ("20 pcs", Decimal("16.00"), Decimal("32.00")),
        ("40 pcs", Decimal("30.00"), Decimal("30.00")),
        ("10 pcs", Decimal("12.50"), Decimal("37.50")),
    ]
    assert q.items[2].options == {"Flavour": "Pandan"}
    assert q.total == Decimal("99.50")


def test_quote_is_logged(store, demo):
    commerce.get_quote(store, demo.shop.id, [{"product_id": demo.banana.id, "qty": 1}],
                       channel=Channel.mcp, agent_name="Gemini Shopper",
                       actor=Actor.shopper_agent)
    [event] = store.list_audit_events(demo.shop.id)
    assert event.action == "quote_created"
    assert event.actor == Actor.shopper_agent
    assert event.summary == "Quoted 1 line(s), S$24.00 for Gemini Shopper"


# --- price mismatch -----------------------------------------------------------------


def test_buyer_prices_are_ignored_and_flagged(store, demo):
    q = quote(store, demo, {"product_id": demo.lapis.id, "variant": "20 pcs", "qty": 2,
                            "unit_price": "1.00"})
    assert q.items[0].unit_price == Decimal("16.00")
    assert q.total == Decimal("32.00")
    assert q.price_mismatch
    assert q.mismatches == ["Kuih Lapis (20 pcs): buyer sent S$1.00, menu price is S$16.00"]


def test_matching_buyer_price_is_not_a_mismatch(store, demo):
    q = quote(store, demo, {"product_id": demo.lapis.id, "variant": "20 pcs", "qty": 1,
                            "unit_price": "16.00"})
    assert not q.price_mismatch


# --- validation ---------------------------------------------------------------------


def errors_for(store, demo, *items):
    with pytest.raises(OrderValidationError) as info:
        quote(store, demo, *items)
    return info.value.errors


def test_variant_required_when_several(store, demo):
    [msg] = errors_for(store, demo, {"product_id": demo.lapis.id, "qty": 1})
    assert msg == "Item 1: Kuih Lapis comes in several sizes. Choose a variant: 20 pcs, 40 pcs."


def test_unknown_variant(store, demo):
    [msg] = errors_for(store, demo, {"product_id": demo.lapis.id, "variant": "30 pcs", "qty": 1})
    assert msg == "Item 1: Kuih Lapis has no variant '30 pcs'. Choose one of: 20 pcs, 40 pcs."


def test_wrong_variant_on_single_pack(store, demo):
    [msg] = errors_for(store, demo, {"product_id": demo.banana.id, "variant": "12 pcs", "qty": 1})
    assert "only comes as 24 pcs" in msg


@pytest.mark.parametrize("options, expected", [
    ({}, "choose Flavour for Ondeh Ondeh: Pandan, Gula Melaka"),
    ({"Flavour": "Durian"}, "'Durian' is not a choice for Flavour"),
    ({"Flavour": "Pandan", "Size": "XL"}, "has no option 'Size'"),
])
def test_bad_options(store, demo, options, expected):
    [msg] = errors_for(store, demo, {"product_id": demo.ondeh.id, "options": options, "qty": 1})
    assert expected in msg


@pytest.mark.parametrize("qty", [0, -1, 501])
def test_qty_limits(store, demo, qty):
    [msg] = errors_for(store, demo, {"product_id": demo.banana.id, "qty": qty})
    assert "qty must be between 1 and 500" in msg


def test_qty_500_is_allowed(store, demo):
    assert quote(store, demo, {"product_id": demo.banana.id, "qty": 500}).total == Decimal("12000.00")


def test_line_limit_and_empty_order(store, demo):
    [msg] = errors_for(store, demo, *[{"product_id": demo.banana.id, "qty": 1}] * 21)
    assert msg == "Too many lines: 21. The limit is 20."
    assert errors_for(store, demo) == ["Add at least one item to the order."]
    assert len(quote(store, demo, *[{"product_id": demo.banana.id, "qty": 1}] * 20).items) == 20


def test_unknown_unavailable_and_other_shop_products(store, demo):
    from backend.models import Product

    other = store.save_product(Product(shop_id="someone-else", name="X", base_price=Decimal("1")))
    msgs = errors_for(
        store, demo,
        {"product_id": "nope", "qty": 1},
        {"product_id": demo.soldout.id, "qty": 1},
        {"product_id": other.id, "qty": 1},
    )
    assert msgs[0].startswith("Item 1: no product with id 'nope' in this shop.")
    assert msgs[1] == "Item 2: Kueh Salat is not available right now."
    assert msgs[2].startswith("Item 3: no product with id")


def test_product_without_price_cannot_be_ordered(store, demo):
    from backend.models import Product

    p = store.save_product(Product(shop_id=demo.shop.id, name="Seasonal Cake"))
    [msg] = errors_for(store, demo, {"product_id": p.id, "qty": 1})
    assert "has no listed price" in msg


def test_malformed_item(store, demo):
    [msg] = errors_for(store, demo, {"qty": "lots"})
    assert msg.startswith("Item 1: needs product_id")
