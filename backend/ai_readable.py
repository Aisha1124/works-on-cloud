"""Shop data for AI crawlers that don't run JavaScript: schema.org JSON-LD for /s/{slug} and
plain-text llms.txt files. Built from the stored menu only; prices are the stored Decimals.
"""

from decimal import Decimal
from typing import Any, Protocol

from agents.commerce.service import MAX_QTY, MIN_QTY
from agents.risk.scorer import parse_hours
from backend.models import Product

CENT = Decimal("0.01")
NO_SECTION = "Other items"
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
EXAMPLE_LINE = "This is an example shop for demonstration."


class ShopLike(Protocol):
    slug: str
    name: str
    tagline: str
    shop_type: str
    address: str
    hours: str
    phone: str
    currency: str
    example: bool


def _price(value: Decimal) -> str:
    return str(value.quantize(CENT))


def prices(product: Product) -> list[tuple[str, Decimal]]:
    """(pack or size label, price) pairs. Empty if the item has no price yet."""
    if product.variants:
        return [(v.label, v.price) for v in product.variants]
    if product.base_price is not None:
        return [(product.unit, product.base_price)]
    return []


def sections(products: list[Product]) -> list[tuple[str, list[Product]]]:
    """Menu sections in menu order (first appearance of each category)."""
    by_section: dict[str, list[Product]] = {}
    for p in products:
        by_section.setdefault(p.category.strip() or NO_SECTION, []).append(p)
    return list(by_section.items())


# --- schema.org JSON-LD ---------------------------------------------------------------------


def _hhmm(minutes: int) -> str:
    minutes %= 24 * 60  # "6pm-2am" closes at 02:00
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def opening_hours_spec(hours_text: str) -> list[dict[str, Any]]:
    """Free-text hours -> OpeningHoursSpecification list, days with the same times grouped.
    Empty if the text can't be read."""
    hours = parse_hours(hours_text) if hours_text.strip() else None
    if hours is None:
        return []
    groups: dict[tuple[int, int], list[str]] = {}
    for day in range(7):
        for opens, closes in hours[day]:
            groups.setdefault((opens, closes), []).append(DAY_NAMES[day])
    return [{"@type": "OpeningHoursSpecification", "dayOfWeek": days,
             "opens": _hhmm(opens), "closes": _hhmm(closes)}
            for (opens, closes), days in groups.items()]


def _menu_item(product: Product, currency: str) -> dict[str, Any]:
    item: dict[str, Any] = {"@type": "MenuItem", "name": product.name}
    if product.name_local:
        item["alternateName"] = product.name_local
    if product.description:
        item["description"] = product.description
    offers = [{"@type": "Offer", **({"name": label} if label else {}), "price": _price(price),
               "priceCurrency": currency, "availability": "https://schema.org/InStock"}
              for label, price in prices(product)]
    if offers:
        item["offers"] = offers
    return item


def is_bakery(shop: ShopLike) -> bool:
    return "bak" in shop.shop_type.lower()


def shop_jsonld(shop: ShopLike, products: list[Product], url: str) -> dict[str, Any]:
    """FoodEstablishment (Bakery for bakers) with its menu: Menu > MenuSection > MenuItem > Offer."""
    data: dict[str, Any] = {"@context": "https://schema.org",
                            "@type": "Bakery" if is_bakery(shop) else "FoodEstablishment",
                            "name": shop.name, "url": url, "currenciesAccepted": shop.currency}
    if shop.tagline:
        data["description"] = shop.tagline
    if shop.phone:
        data["telephone"] = shop.phone
    if shop.address:
        data["address"] = {"@type": "PostalAddress", "streetAddress": shop.address,
                           "addressCountry": "SG"}
    if spec := opening_hours_spec(shop.hours):
        data["openingHoursSpecification"] = spec
    data["hasMenu"] = {
        "@type": "Menu", "name": f"{shop.name} menu", "inLanguage": "en",
        "hasMenuSection": [{"@type": "MenuSection", "name": name,
                            "hasMenuItem": [_menu_item(p, shop.currency) for p in items]}
                           for name, items in sections(products)],
    }
    return data


# --- llms.txt ------------------------------------------------------------------------------


def _money(currency: str, value: Decimal) -> str:
    return f"S${_price(value)}" if currency == "SGD" else f"{currency} {_price(value)}"


def _menu_line(product: Product, currency: str) -> str:
    name = product.name + (f" ({product.name_local})" if product.name_local else "")
    priced = prices(product)
    if not priced:
        text = "price on request"
    else:
        text = ", ".join(f"{label} {_money(currency, price)}" if label else _money(currency, price)
                         for label, price in priced)
    line = f"- {name}: {text}"
    for option in product.options:
        line += f". {option.name}: {' / '.join(option.choices)}"
    return line


def _one_line(text: str) -> str:
    return " ".join(text.split())


def shop_llms_txt(shop: ShopLike, products: list[Product], *, page_url: str, mcp_url: str,
                  ucp_url: str) -> str:
    tagline = _one_line(shop.tagline)
    about = [tagline if tagline[-1:] in ".!?" else f"{tagline}."] if tagline else []
    if shop.example:
        about.append(EXAMPLE_LINE)
    lines = [f"# {_one_line(shop.name)}", ""]
    if about:
        lines += [f"> {' '.join(about)}", ""]
    details = [("Type", shop.shop_type), ("Address", shop.address), ("Phone", shop.phone),
               ("Currency", shop.currency)]
    lines += [f"- {k}: {_one_line(v)}" for k, v in details if v.strip()]
    lines += ["", "## Opening hours", "", _one_line(shop.hours) if shop.hours.strip()
              else "Not given. Ask the shop.", "", "## Menu", ""]
    if not products:
        lines.append("No items available right now.")
    for name, items in sections(products):
        lines += [f"### {_one_line(name)}", ""]
        lines += [_menu_line(p, shop.currency) for p in items]
        lines.append("")
    lines += [
        "## Pickup rules", "",
        "- Pickup only, at the shop. No delivery.",
        "- Pay at pickup. No payment details are collected online.",
        "- The pickup time must be in the future (Singapore time).",
        f"- Quantity per line: {MIN_QTY} to {MAX_QTY}.",
        "- Orders for a pickup outside opening hours, large orders and unusual orders wait for "
        "the owner's approval before they are confirmed.",
        "",
        "## How to order", "",
        f"- People: open the shop page {page_url} and order there. No account needed.",
        f"- AI agents (MCP, streamable HTTP): {mcp_url} . Use shop slug \"{shop.slug}\" with the "
        "get_menu, get_quote and place_pickup_order tools.",
        f"- AI agents (UCP): discovery profile at {ucp_url}",
        "",
    ]
    return "\n".join(lines)


def site_llms_txt(shops: list[tuple[ShopLike, str]], *, base: str, mcp_url: str,
                  ucp_url: str) -> str:
    """/llms.txt: what KampungCart is and every published shop. `shops` = (shop, page_url)."""
    lines = [
        "# KampungCart", "",
        "> Small Singapore shops (home bakers, hawker stalls, heartland shops) with menus that AI "
        "agents can read and order from. Pickup orders, paid at pickup.", "",
        "## Shops", "",
    ]
    if not shops:
        lines.append("No shops are open yet.")
    for shop, page_url in shops:
        about = ", ".join(_one_line(x) for x in (shop.shop_type, shop.address) if x.strip())
        if shop.example:
            about = f"{about}. {EXAMPLE_LINE}" if about else EXAMPLE_LINE
        lines.append(f"- [{_one_line(shop.name)}]({page_url}/llms.txt)"
                     + (f": {about}" if about else ""))
    lines += [
        "", "## How AI agents order", "",
        f"- MCP server (streamable HTTP): {mcp_url} . Start with the find_shops tool.",
        f"- UCP discovery profile: {ucp_url}",
        f"- Each shop page {base}/s/<slug> also carries schema.org JSON-LD with its menu.",
        "",
    ]
    return "\n".join(lines)
