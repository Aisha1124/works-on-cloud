"""Public shop page: menu JSON for the SPA, /s/{slug} with schema.org JSON-LD, llms.txt files
for AI crawlers, and pickup orders from customers (no key, no signup). Customers never see risk details or other orders."""

import hmac
import html
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from agents.approval import service as approval
from agents.commerce import pickup
from agents.commerce import service as commerce
from backend import ai_readable, emails, mailer, notify, owner_session, privacy
from backend.audit import log_event
from backend.api.config import Settings
from backend.api.deps import caller
from backend.api.routes.shops import ShopLinks, shop_links
from backend.external import (
    MAX_ID_LEN, PLATFORM, RATE_LIMIT_MESSAGE, ShopNotFound, published_shop, published_shops,
)
from backend.models import Actor, Channel, Order, OrderStatus, Product, Shop
from backend.timeutil import to_sg
from backend.ucp.profile import base_url

router = APIRouter()



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
    example: bool = False  # the sample shop: shows an "Example shop" label
    min_notice_hours: int = 24
    paused_until: date | None = None
    # "Not taking orders until Mon 26 Oct 2026." while paused, else "".
    ordering_message: str = ""


def public_shop(shop: Shop) -> PublicShop:
    return PublicShop(**shop.model_dump(), ordering_message=pickup.paused_message(shop))


class PublicProduct(Product):
    """A product as anyone may see it: no owner-only check notes."""

    check_reasons: list[str] = Field(default_factory=list, exclude=True)
    owner_checked: bool = Field(default=False, exclude=True)


class PublicShopPage(BaseModel):
    shop: PublicShop
    products: list[PublicProduct]
    links: ShopLinks


def _page(request: Request, slug: str) -> PublicShopPage | None:
    store = request.app.state.store
    try:
        shop = published_shop(store, slug)
    except ShopNotFound:
        return None
    products = [PublicProduct(**p.model_dump()) for p in store.list_products(shop.id)
                if p.available]
    return PublicShopPage(shop=public_shop(shop), products=products,
                          links=shop_links(request.app.state.settings, shop))


@router.get("/api/public/shops/{slug}", response_model=PublicShopPage)
def get_public_shop(request: Request, slug: str) -> PublicShopPage:
    page = _page(request, slug)
    if page is None:
        raise HTTPException(status_code=404, detail="This shop isn't open on KampungCart.")
    return page


# --- Report this shop ---------------------------------------------------------------------

REPORT_REASONS = {
    "wrong_info": "Wrong prices or menu",
    "order_problem": "Problem with an order",
    "not_real": "Not a real shop, or a scam",
    "unsafe": "Unsafe or illegal items",
    "other": "Something else",
}
REPORT_IP_LIMIT, REPORT_IP_WINDOW_S = 3, 3600.0  # per client per hour
REPORT_SHOP_LIMIT, REPORT_SHOP_WINDOW_S = 20, 86400.0  # per shop per day
REPORT_THANKS = "Thank you. We'll look into it."


class ReportIn(BaseModel):
    reason: Literal["wrong_info", "order_problem", "not_real", "unsafe", "other"]
    details: str = Field(default="", max_length=1000)
    email: str = Field(default="", max_length=254)


@router.post("/api/public/shops/{slug}/report")
def report_shop(request: Request, background: BackgroundTasks, slug: str,
                body: ReportIn) -> dict:
    """Anyone can report a shop. Emailed to ADMIN_EMAIL and logged in the platform audit log
    (not the shop's, so the owner never sees who reported them). Limited per client and per
    shop."""
    store, settings = request.app.state.store, request.app.state.settings
    try:
        shop = published_shop(store, slug)
    except ShopNotFound:
        raise HTTPException(status_code=404, detail="This shop isn't open on KampungCart.") from None
    email = ""
    if body.email.strip():
        email = owner_session.normalize_email(body.email) or ""
        if not email:
            raise HTTPException(status_code=400, detail=(
                "That doesn't look like an email address. Leave it empty if you prefer."))
    state = request.app.state
    if not state.report_ip_limiter.allow(caller(request)) or not (
            state.report_shop_limiter.allow(shop.id)):
        raise HTTPException(status_code=429, detail=(
            "We've received a few reports from you already. Please try again later."))
    reason = REPORT_REASONS[body.reason]
    details = body.details.strip()
    sent_to = settings.admin_email.strip()
    if sent_to:
        background.add_task(mailer.send_safely, settings, emails.report_email(
            sent_to, shop, shop_links(settings, shop).public_page, reason, details, email))
    log_event(
        store, shop_id=PLATFORM, actor=Actor.customer, action="shop_reported",
        entity_type="shop", entity_id=shop.id,
        summary=f"Shop {shop.slug} reported: {reason}",
        details={"shop_id": shop.id, "slug": shop.slug, "reason": body.reason,
                 "details": details[:300], "reporter_email": mailer.mask_email(email) if email else "",
                 "emailed_admin": bool(sent_to)},
    )
    return {"message": REPORT_THANKS}


class SiteInfo(BaseModel):
    """For the /privacy page."""

    admin_email: str  # "" when not set
    retention_days: int


@router.get("/api/public/site", response_model=SiteInfo)
def site_info(request: Request) -> SiteInfo:
    return SiteInfo(admin_email=request.app.state.settings.admin_email.strip(),
                    retention_days=privacy.RETENTION_DAYS)


class SlotTime(BaseModel):
    value: str  # "2026-10-20T09:30", Singapore time: what the order form sends
    label: str  # "09:30"


class SlotDay(BaseModel):
    date: str
    label: str  # "Tue 20 Oct"
    times: list[SlotTime]


class PickupSlots(BaseModel):
    days: list[SlotDay]
    # Why there are no days, in plain words ("" when there are some).
    message: str
    min_notice_hours: int


@router.get("/api/public/shops/{slug}/slots", response_model=PickupSlots)
def get_pickup_slots(request: Request, slug: str) -> PickupSlots:
    """The pickup times the shop page offers: inside opening hours, after the shop's notice,
    not on full days, none while paused. Computed here so the browser does no time maths."""
    store = request.app.state.store
    try:
        shop = published_shop(store, slug)
    except ShopNotFound:
        raise HTTPException(status_code=404, detail="This shop isn't open on KampungCart.") from None
    days = pickup.available_days(store, shop)
    message = pickup.paused_message(shop) or (
        "" if days else "No pickup times are free in the next two weeks. Please call the shop.")
    return PickupSlots(days=days, message=message, min_notice_hours=shop.min_notice_hours)


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
    customer_email: str = Field(default="", max_length=254)
    # One per checkout attempt, so a double tap or a retry never orders twice.
    idempotency_key: str = Field(default="", max_length=commerce.MAX_IDEMPOTENCY_KEY_LEN)


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
    shop_name: str
    # confirmed | pending_owner_approval | rejected | ready | done | cancelled
    status: str
    message: str
    rejection_reason: str
    expired: bool  # rejected because the shop didn't respond in time
    items: list[WebOrderLine]
    total: Decimal
    currency: str
    pickup_time: str
    # The customer's private link to this page. Only ever sent to the person who has the token.
    status_url: str
    can_cancel: bool
    cancel_until: str  # ISO time, Singapore
    email_updates_to: str  # masked, e.g. "s***@gmail.com"; "" when no email was given


def _order_out(request: Request, shop: Shop, order: Order) -> WebOrderOut:
    return WebOrderOut(
        order_id=order.id, shop_slug=shop.slug, shop_name=shop.name,
        status=commerce.BUYER_STATUS[order.status], message=commerce.buyer_message(shop, order),
        rejection_reason=(order.rejection_reason
                          if order.status == OrderStatus.rejected and not order.expired else ""),
        expired=order.expired,
        items=[WebOrderLine(**line.model_dump(include=set(WebOrderLine.model_fields)))
               for line in order.items],
        total=order.total, currency=shop.currency, pickup_time=to_sg(order.pickup_at).isoformat(),
        status_url=notify.status_url(request.app.state.settings, order),
        can_cancel=approval.can_cancel(shop, order),
        cancel_until=to_sg(approval.cancel_deadline(shop, order)).isoformat(),
        email_updates_to=mailer.mask_email(order.customer_email) if order.customer_email else "",
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
        order, _ = await commerce.place_order_once(
            store, shop.id, body.idempotency_key, lambda: commerce.place_order(
                store, shop.id, [line.model_dump() for line in body.items], body.customer_name,
                body.customer_phone, body.pickup_time, body.note, Channel.web, "",
                customer_email=body.customer_email, actor=Actor.customer,
                settings=request.app.state.settings))
    except commerce.OrderValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _order_out(request, shop, order)


ORDER_NOT_FOUND = "We can't find that order. Check that you opened the full link."


def _token_order(request: Request, order_id: str, token: str) -> tuple[Shop, Order]:
    """The order behind a status link. A wrong token looks exactly like a missing order."""
    store = request.app.state.store
    order = store.get_order(order_id[:MAX_ID_LEN])
    shop = store.get_shop(order.shop_id) if order else None
    if (order is None or shop is None or not order.status_token or not token
            or not hmac.compare_digest(order.status_token.encode(), token[:100].encode())):
        raise HTTPException(status_code=404, detail=ORDER_NOT_FOUND)
    return shop, order


@router.get("/api/public/orders/{order_id}", response_model=WebOrderOut)
def get_web_order(request: Request, order_id: str, t: str = "") -> WebOrderOut:
    """The customer's status page /o/{id}?t={token}. Held orders past the shop's approval
    timeout are expired first, so the page always shows the latest status."""
    shop, order = _token_order(request, order_id, t)
    commerce.expire_due_for_order(request.app.state.store, request.app.state.settings, order.id)
    return _order_out(request, shop, request.app.state.store.get_order(order.id))


@router.post("/api/public/orders/{order_id}/cancel", response_model=WebOrderOut)
def cancel_web_order(request: Request, background: BackgroundTasks, order_id: str,
                     t: str = "") -> WebOrderOut:
    """The customer cancels from their status page, up to the shop's cutoff before pickup.
    The owner (and the customer, if they left an email) are emailed."""
    store, settings = request.app.state.store, request.app.state.settings
    shop, order = _token_order(request, order_id, t)
    commerce.expire_due_for_order(store, settings, order.id)
    try:
        order = approval.cancel(store, shop, order.id)
    except approval.InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    background.add_task(notify.owner_cancelled, store, settings, order.id)
    background.add_task(notify.customer_update, store, settings, order.id, "cancelled")
    return _order_out(request, shop, order)


def _script_json(data: dict[str, Any]) -> str:
    """JSON that is safe inside <script>: no '<', '>' or '&' can end the element."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _index_html(settings: Settings) -> str | None:
    index = Path(settings.dashboard_dist) / "index.html"
    return index.read_text(encoding="utf-8") if index.is_file() else None


@router.get("/s/{slug}", include_in_schema=False)
def public_shop_html(request: Request, slug: str):
    """The SPA shell, plus a title, JSON-LD and a link to llms.txt, so crawlers and AI agents
    that don't run JavaScript see the menu."""
    shell = _index_html(request.app.state.settings)
    if shell is None:
        return PlainTextResponse("Dashboard not built yet. Run scripts/build.ps1.",
                                 status_code=503)
    page = _page(request, slug)
    if page is not None and "</head>" in shell:
        head = (f"<title>{html.escape(page.shop.name)} · KampungCart</title>"
                f'<script type="application/ld+json">'
                f"{_script_json(ai_readable.shop_jsonld(page.shop, page.products, page.links.public_page))}"
                f"</script>"
                f'<link rel="alternate" type="text/plain" title="llms.txt" '
                f'href="/s/{html.escape(page.shop.slug)}/llms.txt">')
        if "<title>" in shell:
            start, end = shell.index("<title>"), shell.index("</title>") + len("</title>")
            shell = shell[:start] + shell[end:]
        shell = shell.replace("</head>", head + "</head>", 1)
    return HTMLResponse(shell, headers={"Cache-Control": "no-cache"})


TEXT = "text/plain; charset=utf-8"


@router.get("/s/{slug}/llms.txt", include_in_schema=False)
def shop_llms_txt(request: Request, slug: str):
    """The shop in plain text: menu with prices, hours, pickup rules and how to order."""
    page = _page(request, slug)
    if page is None:
        return PlainTextResponse("This shop isn't open on KampungCart.\n", status_code=404,
                                 media_type=TEXT)
    base = base_url(request.app.state.settings)
    return PlainTextResponse(
        ai_readable.shop_llms_txt(page.shop, page.products, page_url=page.links.public_page,
                                  mcp_url=page.links.mcp, ucp_url=f"{base}/.well-known/ucp"),
        media_type=TEXT, headers={"Cache-Control": "no-cache"})


@router.get("/llms.txt", include_in_schema=False)
def site_llms_txt(request: Request):
    """Every published shop, with links to their llms.txt and the MCP/UCP entry points."""
    settings = request.app.state.settings
    shops = [(public_shop(s), shop_links(settings, s).public_page)
             for s in published_shops(request.app.state.store)]
    base = base_url(settings)
    return PlainTextResponse(
        ai_readable.site_llms_txt(shops, base=base, mcp_url=f"{base}/mcp",
                                  ucp_url=f"{base}/.well-known/ucp"),
        media_type=TEXT, headers={"Cache-Control": "no-cache"})
