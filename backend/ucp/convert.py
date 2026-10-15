"""Translate between our models and UCP JSON. Money: Decimal <-> integer minor units (cents).

No prices are computed here: line totals and totals come from commerce's Quote or the Order.
"""

from decimal import Decimal
from typing import Any

from backend.models import OrderItem, Product, Shop

CENTS = Decimal(100)
VARIANT_SEP = ".v"


def to_minor(amount: Decimal) -> int:
    """S$16.50 -> 1650. Amounts are already rounded to cents by commerce."""
    return int((amount * CENTS).to_integral_value())


def price(amount: Decimal, currency: str) -> dict[str, Any]:
    return {"amount": to_minor(amount), "currency": currency}


# --- Item ids ----------------------------------------------------------------------
# A product with several packs has one UCP variant per pack: "<product id>.v<n>".
# A product with one price has one variant whose id is the product id.


def variant_id(product: Product, index: int | None) -> str:
    return product.id if index is None else f"{product.id}{VARIANT_SEP}{index}"


def parse_item_id(item_id: str) -> tuple[str, int | None]:
    """-> (product id, variant index or None). Unknown shapes come back as a product id."""
    pid, sep, n = item_id.partition(VARIANT_SEP)
    if sep and n.isdigit():
        return pid, int(n)
    return item_id, None


def variant_label(product: Product, index: int | None) -> str | None:
    """The pack label commerce expects, or None when the index doesn't exist."""
    if index is None:
        return None
    if 0 <= index < len(product.variants):
        return product.variants[index].label
    return f"#{index}"  # commerce reports it as an unknown variant


# --- Catalog -------------------------------------------------------------------------


def _variants(product: Product, currency: str) -> list[dict[str, Any]]:
    if product.variants:
        return [{
            "id": variant_id(product, n),
            "title": f"{product.name} ({v.label})",
            "description": {"plain": product.description or f"{product.name}, {v.label}"},
            "price": price(v.price, currency),
            "availability": {"available": product.available},
        } for n, v in enumerate(product.variants)]
    if product.base_price is None:
        return []
    title = f"{product.name} ({product.unit})" if product.unit else product.name
    return [{
        "id": variant_id(product, None),
        "title": title,
        "description": {"plain": product.description or title},
        "price": price(product.base_price, currency),
        "availability": {"available": product.available},
    }]


def orderable(product: Product) -> bool:
    return product.available and (bool(product.variants) or product.base_price is not None)


def product_out(product: Product, shop: Shop) -> dict[str, Any]:
    variants = _variants(product, shop.currency)
    amounts = [v["price"]["amount"] for v in variants]
    return {
        "id": product.id,
        "title": product.name,
        "description": {"plain": product.description or product.name},
        "price_range": {"min": {"amount": min(amounts), "currency": shop.currency},
                        "max": {"amount": max(amounts), "currency": shop.currency}},
        "categories": [product.category] if product.category else [],
        "options": [{"name": o.name, "values": [{"label": c} for c in o.choices]}
                    for o in product.options],
        "variants": variants,
        "kampungcart": {
            "shop": shop.slug, "shop_name": shop.name, "name_local": product.name_local,
            "required_options": {o.name: o.choices for o in product.options if o.choices},
            "options_note": "Send chosen options per checkout line as "
                            "kampungcart.options, e.g. {\"Flavour\": \"Pandan\"}.",
        },
    }


# --- Checkout ------------------------------------------------------------------------


def line_out(line_id: str, item_id: str, item: OrderItem, currency: str) -> dict[str, Any]:
    title = f"{item.name} ({item.variant})" if item.variant else item.name
    if item.options:
        title += " - " + ", ".join(f"{k}: {v}" for k, v in item.options.items())
    return {
        "id": line_id,
        "item": {"id": item_id, "title": title, "price": to_minor(item.unit_price)},
        "quantity": item.qty,
        "totals": [{"type": "subtotal", "amount": to_minor(item.line_total)},
                   {"type": "total", "amount": to_minor(item.line_total)}],
    }


def totals(total: Decimal) -> list[dict[str, Any]]:
    return [{"type": "subtotal", "amount": to_minor(total)},
            {"type": "total", "amount": to_minor(total)}]
