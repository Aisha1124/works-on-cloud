from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.models import Order, OrderItem, Product, Risk, Shop


def make_order(**overrides) -> Order:
    data = dict(
        shop_id="s1",
        items=[
            OrderItem(
                product_id="p1",
                name="Kuih lapis",
                variant="10 pcs",
                qty=5,
                unit_price=Decimal("8.50"),
                line_total=Decimal("42.50"),
            )
        ],
        total=Decimal("42.50"),
        customer_name="Mei Ling",
        customer_phone="+6591234567",
        pickup_at=datetime(2026, 10, 17, 10, 0, tzinfo=UTC),
        channel="mcp",
        status="auto_approved",
    )
    data.update(overrides)
    return Order(**data)


def test_shop_defaults():
    shop = Shop(slug="mak-kuih", name="Mak's Kuih")
    assert shop.currency == "SGD"
    assert shop.auto_approve_limit == Decimal("150")
    assert shop.published is False
    assert shop.created_at.tzinfo is not None
    assert len(shop.id) == 12


def test_money_survives_json_round_trip_as_string():
    order = make_order()
    data = order.model_dump(mode="json")
    assert data["total"] == "42.50"
    assert data["items"][0]["unit_price"] == "8.50"
    again = Order.model_validate(data)
    assert again.total == Decimal("42.50")
    assert isinstance(again.total, Decimal)


def test_product_confidence_bounds():
    Product(shop_id="s1", name="Ondeh ondeh", confidence=0.4)
    with pytest.raises(ValidationError):
        Product(shop_id="s1", name="Ondeh ondeh", confidence=1.5)


def test_risk_score_bounds_and_level():
    Risk(score=72, level="high", reasons=["new phone number"])
    with pytest.raises(ValidationError):
        Risk(score=101, level="high")
    with pytest.raises(ValidationError):
        Risk(score=10, level="extreme")


def test_order_rejects_bad_status_and_channel():
    with pytest.raises(ValidationError):
        make_order(status="shipped")
    with pytest.raises(ValidationError):
        make_order(channel="email")
