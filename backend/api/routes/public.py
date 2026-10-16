"""Public shop page: menu JSON for the SPA, /s/{slug} with schema.org JSON-LD, and pickup
orders from customers (no key, no signup). Customers never see risk details or other orders."""

import html
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from agents.commerce import service as commerce
from backend.api.config import Settings
from backend.api.deps import caller
from backend.api.routes.shops import ShopLinks, shop_links
from backend.external import MAX_ID_LEN, RATE_LIMIT_MESSAGE, ShopNotFound, published_shop
from backend.models import Actor, Channel, Order, OrderStatus, Product, Shop
from backend.timeutil import to_sg

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


# --- Customer orders ----------------------------------------------------------------


class WebLine(BaseModel):
    product_id: str = Field(max_length=MAX_ID_LEN)
    variant: str | None = Field(default=None, max_length=80)
    options: dict[str, str] = Field(default_factory=dict, max_length=10)
    qty: int


class WebOrderIn(BaseModel):
    items: list[WebLine] = Field(min_length=1, max_length=commerce.MAX_LINES)
    customer_name: str = Field(max_length=commerce.MAX_NAME_LEN)
    customer_phone: str = Field(max_length=30)
    pickup_time: str = Field(max_length=40)
    note: str = Field(default="", max_length=commerce.MAX_NOTE_LEN)


class WebOrderLine(BaseModel):
    name: str
    variant: str | None
    options: dict[str, str]
    qty: int
    unit_price: Decimal
    line_total: Decimal


class WebOrderOut(BaseModel):
    """What the customer sees: buyer status words and a plain message. No phone number,
    no risk score."""

    order_id: str
    shop_slug: str
    status: str  # confirmed | pending_owner_approval | rejected | ready | done
    message: str
    rejection_reason: str
    items: list[WebOrderLine]
    total: Decimal
    currency: str
    pickup_time: str


def _order_out(shop: Shop, order: Order) -> WebOrderOut:
    return WebOrderOut(
        order_id=order.id, shop_slug=shop.slug, status=commerce.BUYER_STATUS[order.status],
        message=commerce.buyer_message(shop, order),
        rejection_reason=order.rejection_reason if order.status == OrderStatus.rejected else "",
        items=[WebOrderLine(**line.model_dump(include=set(WebOrderLine.model_fields)))
               for line in order.items],
        total=order.total, currency=shop.currency, pickup_time=to_sg(order.pickup_at).isoformat(),
    )


class WebQuoteIn(BaseModel):
    items: list[WebLine] = Field(min_length=1, max_length=commerce.MAX_LINES)


class WebQuoteOut(BaseModel):
    items: list[WebOrderLine]
    total: Decimal
    currency: str


@router.post("/api/public/shops/{slug}/quote", response_model=WebQuoteOut)
def quote_web_cart(request: Request, slug: str, body: WebQuoteIn) -> WebQuoteOut:
    """Price the cart on the shop page. Prices and the total always come from here (Python,
    Decimal); the page never adds up money. Not audited: it changes nothing."""
    store = request.app.state.store
    try:
        shop = published_shop(store, slug)
    except ShopNotFound:
        raise HTTPException(status_code=404, detail="This shop isn't open on KampungCart.") from None
    try:
        quote, _ = commerce.build_quote(store, shop.id, [line.model_dump() for line in body.items])
    except commerce.OrderValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return WebQuoteOut(
        items=[WebOrderLine(**line.model_dump(include=set(WebOrderLine.model_fields)))
               for line in quote.items],
        total=quote.total, currency=shop.currency)


@router.post("/api/public/shops/{slug}/orders", response_model=WebOrderOut, status_code=201)
async def place_web_order(request: Request, slug: str, body: WebOrderIn) -> WebOrderOut:
    """A customer's pickup order from the shop page. Same checks as agent orders: menu prices,
    risk score and owner approval for anything unusual. Limited per client."""
    store = request.app.state.store
    try:
        shop = published_shop(store, slug)
    except ShopNotFound:
        raise HTTPException(status_code=404, detail="This shop isn't open on KampungCart.") from None
    if not request.app.state.order_limiter.allow(caller(request)):
        raise HTTPException(status_code=429, detail=RATE_LIMIT_MESSAGE)
    try:
        order = await commerce.place_order(
            store, shop.id, [line.model_dump() for line in body.items], body.customer_name,
            body.customer_phone, body.pickup_time, body.note, Channel.web, "",
            actor=Actor.customer, settings=request.app.state.settings)
    except commerce.OrderValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _order_out(shop, order)


@router.get("/api/public/orders/{order_id}", response_model=WebOrderOut)
def get_web_order(request: Request, order_id: str) -> WebOrderOut:
    """Status of one order, for the customer who placed it (the id is only shown to them)."""
    store = request.app.state.store
    order = store.get_order(order_id[:MAX_ID_LEN])
    shop = store.get_shop(order.shop_id) if order else None
    if order is None or shop is None or not shop.published:
        raise HTTPException(status_code=404, detail="We can't find that order.")
    return _order_out(shop, order)


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
