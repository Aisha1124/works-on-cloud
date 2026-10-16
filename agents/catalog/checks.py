"""Which menu items the owner should check before going live, and why.

Gemini's confidence alone isn't reliable, so two kinds of signal are combined:
- read-time reasons stored on the product (Product.check_reasons): Gemini marked the item
  unclear, the printed price isn't a valid number, or the text looks like instructions;
- rules over the whole menu, run again on every request so edits show up straight away:
  missing price, a price far from the rest of its section, duplicate names, and an empty
  pack size where the rest of the section has one. Once the owner has saved an item
  themselves, the two "looks unusual" rules (price, pack size) no longer flag it.

Flags are guidance for the owner, never a blocker. Pure Python, no model calls.
"""

from collections import defaultdict
from decimal import Decimal
from statistics import median

from agents.catalog.normalize import normalise_name
from backend.models import Product

FAR_FACTOR = Decimal(5)  # more than 5x, or less than 1/5 of, the section's usual price
MIN_SECTION_FOR_PRICE = 3  # priced items a section needs before prices are compared
NO_SECTION = ""

MISSING_PRICE = "No price yet. Add one, or customers can't order it."
DUPLICATE = "Another item has the same name. Remove one, or rename it."
NO_PACK = "No pack size, but other items in this section have one (e.g. \"10 pcs\")."


def _main_price(p: Product) -> Decimal | None:
    """The price that represents the item: its single price, or its smallest pack's."""
    if p.variants:
        return min(v.price for v in p.variants)
    return p.base_price


def _far_reason(price: Decimal, usual: Decimal) -> str:
    return (f"S${price:.2f} is far from the other prices in this section (usually about "
            f"S${usual:.2f}). Check for a missing or extra digit.")


def menu_checks(products: list[Product]) -> dict[str, list[str]]:
    """product id -> reasons to check it. Items with nothing to check are left out."""
    reasons: dict[str, list[str]] = defaultdict(list)
    for p in products:
        reasons[p.id].extend(p.check_reasons)
        if p.base_price is None and not p.variants:
            reasons[p.id].append(MISSING_PRICE)

    by_name: dict[str, list[Product]] = defaultdict(list)
    for p in products:
        by_name[normalise_name(p.name)].append(p)
    for same in by_name.values():
        if len(same) > 1:
            for p in same:
                reasons[p.id].append(DUPLICATE)

    by_section: dict[str, list[Product]] = defaultdict(list)
    for p in products:
        by_section[p.category.strip().casefold() or NO_SECTION].append(p)
    for items in by_section.values():
        priced = [(p, price) for p in items if (price := _main_price(p)) is not None]
        if len(priced) >= MIN_SECTION_FOR_PRICE:
            for p, price in priced:
                others = [x for q, x in priced if q.id != p.id]
                usual = Decimal(median(others))
                if p.owner_checked:
                    continue
                if usual > 0 and (price > usual * FAR_FACTOR or price * FAR_FACTOR < usual):
                    reasons[p.id].append(_far_reason(price, usual))
        # Single-price items only: items with variants carry their pack sizes in the labels.
        with_pack = [p for p in items if p.variants or p.unit.strip()]
        if len(items) >= 2 and len(with_pack) * 2 > len(items):
            for p in items:
                if (not p.owner_checked and not p.variants and not p.unit.strip()
                        and p.base_price is not None):
                    reasons[p.id].append(NO_PACK)

    return {pid: _unique(r) for pid, r in reasons.items() if r}


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(i for i in items if i.strip()))
