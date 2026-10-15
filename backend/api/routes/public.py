"""Public, read-only shop page: JSON for the SPA, and /s/{slug} with schema.org JSON-LD."""

import html
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from backend.api.config import Settings
from backend.api.routes.shops import ShopLinks, shop_links
from backend.external import ShopNotFound, published_shop
from backend.models import Product, Shop

router = APIRouter()

CENT = Decimal("0.01")


class PublicShop(BaseModel):
    """What anyone may see. No owner settings (auto-approve limit)."""

    slug: str
    name: str
    tagline: str
    shop_type: str
    address: str
    hours: str
    phone: str
    currency: str


class PublicShopPage(BaseModel):
    shop: PublicShop
    products: list[Product]
    links: ShopLinks


def _page(request: Request, slug: str) -> PublicShopPage | None:
    store = request.app.state.store
    try:
        shop = published_shop(store, slug)
    except ShopNotFound:
        return None
    products = [p for p in store.list_products(shop.id) if p.available]
    return PublicShopPage(shop=PublicShop(**shop.model_dump()), products=products,
                          links=shop_links(request.app.state.settings, shop))


@router.get("/api/public/shops/{slug}", response_model=PublicShopPage)
def get_public_shop(request: Request, slug: str) -> PublicShopPage:
    page = _page(request, slug)
    if page is None:
        raise HTTPException(status_code=404, detail="This shop isn't open on KampungCart.")
    return page


def _price(value: Decimal) -> str:
    return str(value.quantize(CENT))


def _offers(product: Product, currency: str) -> list[dict[str, Any]]:
    item = {"@type": "Product", "name": product.name}
    if product.name_local:
        item["alternateName"] = product.name_local
    if product.category:
        item["category"] = product.category
    if product.description:
        item["description"] = product.description
    priced = ([(v.label, v.price) for v in product.variants] if product.variants
              else [(product.unit, product.base_price)] if product.base_price is not None else [])
    return [{
        "@type": "Offer",
        **({"name": label} if label else {}),
        "price": _price(price),
        "priceCurrency": currency,
        "availability": "https://schema.org/InStock",
        "itemOffered": item,
    } for label, price in priced]


def shop_jsonld(shop: Shop | PublicShop, products: list[Product], url: str) -> dict[str, Any]:
    data: dict[str, Any] = {"@context": "https://schema.org", "@type": "Store",
                            "name": shop.name, "url": url}
    if shop.tagline:
        data["description"] = shop.tagline
    if shop.phone:
        data["telephone"] = shop.phone
    if shop.address:
        data["address"] = {"@type": "PostalAddress", "streetAddress": shop.address,
                           "addressCountry": "SG"}
    offers = [o for p in products for o in _offers(p, shop.currency)]
    data["hasOfferCatalog"] = {"@type": "OfferCatalog", "name": "Menu",
                               "itemListElement": offers}
    return data


def _script_json(data: dict[str, Any]) -> str:
    """JSON that is safe inside <script>: no '<', '>' or '&' can end the element."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _index_html(settings: Settings) -> str | None:
    index = Path(settings.dashboard_dist) / "index.html"
    return index.read_text(encoding="utf-8") if index.is_file() else None


@router.get("/s/{slug}", include_in_schema=False)
def public_shop_html(request: Request, slug: str):
    """The SPA shell, plus JSON-LD and a title so crawlers and AI agents see the menu."""
    shell = _index_html(request.app.state.settings)
    if shell is None:
        return PlainTextResponse("Dashboard not built yet. Run scripts/build.ps1.",
                                 status_code=503)
    page = _page(request, slug)
    if page is not None and "</head>" in shell:
        head = (f"<title>{html.escape(page.shop.name)} · KampungCart</title>"
                f'<script type="application/ld+json">'
                f"{_script_json(shop_jsonld(page.shop, page.products, page.links.public_page))}"
                f"</script>")
        if "<title>" in shell:
            start, end = shell.index("<title>"), shell.index("</title>") + len("</title>")
            shell = shell[:start] + shell[end:]
        shell = shell.replace("</head>", head + "</head>", 1)
    return HTMLResponse(shell, headers={"Cache-Control": "no-cache"})
