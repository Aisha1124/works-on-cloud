"""MCP server for external AI shopping agents (MCP Python SDK v2, MCPServer, streamable HTTP).

Each tool is a thin adapter over agents/commerce: find the published shop, call the service
with channel="mcp", and turn known errors into one plain sentence the buyer agent can act on.
Every call, failed or not, is written to the audit log as actor=external_agent.

Statuses are shown in buyer words (confirmed / pending_owner_approval); stored orders, the
dashboard and UCP keep the model statuses.
"""

import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, Field

from agents.approval import service as approval
from agents.commerce import pickup
from agents.commerce import service as commerce
from backend import notify
from backend.api.config import Settings
from backend.external import (
    GENERIC_ERROR, MAX_ID_LEN, MAX_QUERY_LEN, MAX_SLUG_LEN, RATE_LIMIT_MESSAGE, StoreRateLimiter,
    ShopNotFound, area_of, audit_external_call, clean_agent_name, client_key, published_shop,
    published_shops,
)
from backend.models import Channel, OrderStatus, Shop
from backend.store.base import Store
from backend.timeutil import to_sg

log = logging.getLogger(__name__)


INSTRUCTIONS = (
    "KampungCart lists small Singapore shops (home bakers, hawker stalls, heartland shops). "
    "Typical flow: find_shops -> get_menu -> get_quote -> place_pickup_order -> "
    "get_order_status. Prices are in SGD and always come from the shop's menu; any price you "
    "send is ignored. Payment is made at pickup; no payment details are collected. The pickup "
    "time must be inside opening hours, after the shop's minimum notice and on a day that "
    "isn't fully booked; if not, you get the reason and the next available times. Orders for "
    "items not on the menu, custom requests, unusual quantities, large totals or risky orders "
    "are held (pending_owner_approval) until the shop owner decides, so check "
    "get_order_status later. Send an idempotency_key with place_pickup_order so a retry never "
    "orders twice."
)

BUYER_STATUS = commerce.BUYER_STATUS

ShopSlug = Annotated[str, Field(description="Shop slug from find_shops, e.g. 'mak-kuih'.",
                                max_length=MAX_SLUG_LEN)]
AgentName = Annotated[str | None, Field(description="Your name, e.g. 'Gemini Shopper'.",
                                        max_length=80)]


class OrderLineIn(BaseModel):
    name: str | None = Field(
        default=None, max_length=commerce.MAX_ITEM_NAME_LEN,
        description="Menu item name as shown by get_menu, e.g. 'Kuih Lapis' (case and spaces "
                    "don't matter). A name that is not on the menu is sent to the owner to "
                    "price, and the order is held.")
    product_id: str | None = Field(
        default=None, max_length=MAX_ID_LEN,
        description="Product id from get_menu. Use it instead of name when a name is ambiguous.")
    qty: int = Field(description="How many packs or pieces of this item/variant (1-500).")
    variant: str | None = Field(
        default=None, max_length=80,
        description="Size or pack label exactly as listed in the item's variants, e.g. "
                    "'20 pcs'. Leave empty when the item has one size.")
    options: dict[str, str] = Field(
        default_factory=dict,
        description="Choices for the item's options, e.g. {'Flavour': 'Pandan'}. "
                    "Required options must be chosen.")
    request: str = Field(
        default="", max_length=commerce.MAX_REQUEST_LEN,
        description="Optional custom request for this line, e.g. 'write Happy Birthday'. "
                    "Custom requests need the owner's approval.")


Items = Annotated[list[OrderLineIn], Field(description="1-20 order lines.")]


def _items(items: list[OrderLineIn]) -> list[dict[str, Any]]:
    return [i.model_dump() for i in items]


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _shop_summary(shop: Shop) -> dict[str, Any]:
    # The sample shop says so, so agents can tell their users it isn't a real business.
    return {"shop_slug": shop.slug, "name": shop.name, "type": shop.shop_type,
            "area": area_of(shop), **({"example_shop": True} if shop.example else {})}


def _menu_item(p) -> dict[str, Any]:
    return {
        "product_id": p.id, "name": p.name, "name_local": p.name_local, "category": p.category,
        "price": _money(p.base_price) if p.base_price is not None else None,
        "unit": p.unit,
        "variants": [{"label": v.label, "price": _money(v.price)} for v in p.variants],
        "options": [{"name": o.name, "choices": o.choices} for o in p.options],
        "available": p.available,
        "notes": p.description,
    }


def _unpriced_out(unpriced) -> list[dict[str, Any]]:
    return [{"name": u.name, "qty": u.qty, "request": u.request, "price": None}
            for u in unpriced]


def _quote_out(shop: Shop, quote: commerce.Quote) -> dict[str, Any]:
    return {
        "items": [{"product_id": i.product_id, "name": i.name, "variant": i.variant,
                   "options": i.options, "qty": i.qty, "unit_price": _money(i.unit_price),
                   "line_total": _money(i.line_total), "request": i.request}
                  for i in quote.items],
        "unpriced_items": _unpriced_out(quote.unpriced),
        "subtotal": _money(quote.total),
        "currency": quote.currency,
        "needs_owner_approval": bool(quote.review_reasons),
        "approval_reasons": quote.review_reasons,
        "approval_message": (" ".join(commerce.hold_sentences(shop, quote.review_codes))
                             + " The owner would need to approve this order."
                             if quote.review_reasons else ""),
        **_pickup_out(quote),
        **_paused_out(shop),
        "payment": "Pay at pickup",
    }


def _pickup_out(quote: commerce.Quote) -> dict[str, Any]:
    """Only when a pickup time was checked and the shop can't take it."""
    if not quote.pickup_problem:
        return {}
    return {"pickup_ok": False, "pickup_problem": quote.pickup_problem,
            "next_available_pickups": quote.next_pickups}


def _paused_out(shop: Shop) -> dict[str, Any]:
    message = pickup.paused_message(shop)
    return {"ordering_paused_message": f"{shop.name}: {message}"} if message else {}


def _placed_out(settings: Settings, shop: Shop, order, duplicate: bool) -> dict[str, Any]:
    out = {"order_id": order.id, "status": BUYER_STATUS[order.status],
           "subtotal": _money(order.total), "currency": shop.currency,
           "unpriced_items": _unpriced_out(order.unpriced_requests),
           "pickup_time": to_sg(order.pickup_at).isoformat(),
           "message": commerce.buyer_message(shop, order),
           "status_url": notify.status_url(settings, order),
           "status_url_note": ("Give this private link to the buyer: they can check "
                               "the order and cancel it there."),
           "payment": "Pay at pickup"}
    if order.status == OrderStatus.pending_approval:
        # Only the deterministic menu/limit reasons. Risk scoring stays private so it can't
        # be gamed.
        out["approval_reasons"] = order.review_reasons
    if duplicate:
        out["duplicate"] = True
        out["duplicate_note"] = ("This idempotency_key was already used: this is the order it "
                                 "placed. No new order was created.")
    return out


def _error(message: str) -> CallToolResult:
    """An error result whose text is exactly our sentence (no SDK prefix, no internals)."""
    return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)


def create_mcp_server(store: Store, settings: Settings,
                      order_limiter: StoreRateLimiter | None = None) -> MCPServer:
    """A new server bound to this app's store. One per FastAPI app (tests build many)."""
    limiter = order_limiter or StoreRateLimiter(store, "orders", 10, 60.0)
    mcp = MCPServer("KampungCart", instructions=INSTRUCTIONS, version="0.2.0")

    def caller(ctx: Context, given: str | None = None) -> tuple[str, str]:
        """-> (agent_name, rate-limit key). The name comes from the tool argument, else
        the MCP client's own name. It is data only and never followed."""
        name = clean_agent_name(given)
        if not name:
            params = getattr(ctx.session, "client_params", None)
            info = getattr(params, "client_info", None)
            name = clean_agent_name(getattr(info, "name", ""))
        request = ctx.request_context.request
        host = getattr(getattr(request, "client", None), "host", None)
        return name, client_key(getattr(request, "headers", None), host or "in-memory")

    def shop_of_order(order_id: str) -> Shop:
        """The published shop an order belongs to. Unknown ids and orders of unpublished
        shops look the same: not found."""
        order = store.get_order((order_id or "").strip()[:MAX_ID_LEN])
        shop = store.get_shop(order.shop_id) if order else None
        if shop is None or not shop.published:
            raise approval.OrderNotFound(order_id)
        return shop

    async def run(call: str, agent_name: str, resolve: Callable[[], Shop | None],
                  body: Callable[[Shop | None], Awaitable[Any] | Any]) -> Any:
        """Resolve the shop, run the tool body, audit the call, map errors to sentences."""
        shop_id = None
        try:
            shop = resolve()
            shop_id = shop.id if shop else None
            result = body(shop)
            if isinstance(result, Awaitable):
                result = await result
        except (ShopNotFound, commerce.OrderValidationError, approval.OrderNotFound,
                ToolError) as exc:
            audit_external_call(store, shop_id=shop_id, channel=Channel.mcp, call=call,
                                agent_name=agent_name, ok=False, error=str(exc))
            return _error(str(exc))
        except Exception:
            log.exception("MCP tool %s failed", call)
            audit_external_call(store, shop_id=shop_id, channel=Channel.mcp, call=call,
                                agent_name=agent_name, ok=False, error="internal error")
            return _error(GENERIC_ERROR)
        audit_external_call(store, shop_id=shop_id, channel=Channel.mcp, call=call,
                            agent_name=agent_name, ok=True,
                            entity_id=result.get("order_id", "") if isinstance(result, dict) else "")
        return result

    def by_slug(slug: str) -> Callable[[], Shop]:
        return lambda: published_shop(store, slug)

    @mcp.tool(description="List the shops you can order from. Optional query matches the shop "
                          "name, type or area, e.g. 'kuih' or 'Tampines'.")
    async def find_shops(
        ctx: Context,
        query: Annotated[str | None, Field(description="Words to match; empty lists all shops.",
                                           max_length=MAX_QUERY_LEN)] = None,
    ) -> dict[str, Any]:
        agent, _ = caller(ctx)

        def body(_):
            words = (query or "").lower().split()
            shops = [_shop_summary(s) for s in published_shops(store)]
            found = [s for s in shops
                     if all(w in " ".join(s.values()).lower() for w in words)]
            return {"shops": found, "count": len(found)}

        return await run("find_shops", agent, lambda: None, body)

    @mcp.tool(description="Details of one shop: address, opening hours, phone, currency and "
                          "the product categories it sells.")
    async def get_shop(ctx: Context, shop_slug: ShopSlug) -> dict[str, Any]:
        agent, _ = caller(ctx)

        def body(shop: Shop):
            categories = sorted({p.category for p in store.list_products(shop.id)
                                 if p.available and p.category})
            return {**_shop_summary(shop), "tagline": shop.tagline, "address": shop.address,
                    "hours": shop.hours, "phone": shop.phone, "currency": shop.currency,
                    "categories": categories, "payment": "Pay at pickup",
                    "fulfillment": "Pickup at the shop",
                    "min_notice_hours": shop.min_notice_hours,
                    "next_available_pickups": [pickup.iso(s) for s in
                                               pickup.next_slots(store, shop)],
                    **_paused_out(shop)}

        return await run("get_shop", agent, by_slug(shop_slug), body)

    @mcp.tool(description="A shop's menu: every item with its price in SGD, category, "
                          "availability, notes, sizes/packs (variants) and options (e.g. "
                          "flavours). Items with available=false can't be ordered right now.")
    async def get_menu(
        ctx: Context,
        shop_slug: ShopSlug,
        query: Annotated[str, Field(description="Optional words to match, e.g. 'kuih lapis'. "
                                                "Empty returns the whole menu.",
                                    max_length=MAX_QUERY_LEN)] = "",
        category: Annotated[str | None, Field(description="Only this category (from get_shop).",
                                              max_length=60)] = None,
        agent_name: AgentName = None,
    ) -> dict[str, Any]:
        agent, _ = caller(ctx, agent_name)

        def body(shop: Shop):
            found = commerce.search_products(store, shop.id, query, category,
                                             available_only=False)
            return {"shop_slug": shop.slug, "items": [_menu_item(p) for p in found],
                    "count": len(found), "currency": shop.currency, "hours": shop.hours,
                    **_paused_out(shop)}

        return await run("get_menu", agent, by_slug(shop_slug), body)

    @mcp.tool(description="Price items from the shop's menu without ordering. The shop "
                          "computes every price; any price you send is ignored. Also says "
                          "whether the order would need the owner's approval, and why.")
    async def get_quote(
        ctx: Context,
        shop_slug: ShopSlug,
        items: Items,
        pickup_time: Annotated[str | None, Field(
            description="Optional pickup date and time in Singapore time, e.g. "
                        "2026-10-17T10:00. If the shop can't take it (closed, too soon, "
                        "fully booked or paused), the answer says why and lists the next "
                        "available pickup times.",
            max_length=40)] = None,
        agent_name: AgentName = None,
    ) -> dict[str, Any]:
        agent, _ = caller(ctx, agent_name)

        def body(shop: Shop):
            quote = commerce.get_quote(store, shop.id, _items(items), channel=Channel.mcp,
                                       agent_name=agent, pickup_at=pickup_time)
            return _quote_out(shop, quote)

        return await run("get_quote", agent, by_slug(shop_slug), body)

    @mcp.tool(description="Place a pickup order. Payment is at pickup. Returns order_id and "
                          "status: 'confirmed', or 'pending_owner_approval' when the owner must "
                          "approve it first (approval_reasons says why); then check "
                          "get_order_status later.")
    async def place_pickup_order(
        ctx: Context,
        shop_slug: ShopSlug,
        items: Items,
        pickup_time: Annotated[str, Field(description="Pickup date and time in Singapore "
                                                      "time, ISO format, e.g. 2026-10-17T10:00.",
                                          max_length=40)],
        customer_name: Annotated[str, Field(description="Buyer's name (max 80 characters).")],
        customer_phone: Annotated[str, Field(description="Buyer's Singapore phone number, e.g. "
                                                         "+65 9123 4567.", max_length=30)],
        note: Annotated[str, Field(description="Optional note for the shop (max 500 "
                                               "characters).")] = "",
        customer_email: Annotated[str, Field(
            description="Optional buyer email. If given, the buyer is emailed when the order "
                        "is confirmed, rejected, expires or is cancelled.",
            max_length=254)] = "",
        idempotency_key: Annotated[str | None, Field(
            description="Optional. Any unique string for this order, e.g. a UUID. If you send "
                        "the same key again (say, after a timeout), you get the first order "
                        "back instead of a duplicate.",
            max_length=commerce.MAX_IDEMPOTENCY_KEY_LEN)] = None,
        agent_name: AgentName = None,
    ) -> dict[str, Any]:
        agent, key = caller(ctx, agent_name)

        async def body(shop: Shop):
            if not limiter.allow(key):
                raise ToolError(RATE_LIMIT_MESSAGE)
            order, duplicate = await commerce.place_order_once(
                store, shop.id, idempotency_key, lambda: commerce.place_order(
                    store, shop.id, _items(items), customer_name, customer_phone, pickup_time,
                    note, Channel.mcp, agent, customer_email=customer_email,
                    settings=settings))
            return _placed_out(settings, shop, order, duplicate)

        return await run("place_pickup_order", agent, by_slug(shop_slug), body)

    @mcp.tool(description="Current status of an order: confirmed, pending_owner_approval, "
                          "rejected, ready, done or cancelled, with a plain message.")
    async def get_order_status(
        ctx: Context,
        order_id: Annotated[str, Field(description="order_id from place_pickup_order.",
                                       max_length=MAX_ID_LEN)],
        agent_name: AgentName = None,
    ) -> dict[str, Any]:
        agent, _ = caller(ctx, agent_name)

        def body(shop: Shop):
            status = commerce.get_order_status(store, shop.id, order_id, settings)
            return {**status, "status": BUYER_STATUS[OrderStatus(status["status"])],
                    "shop_slug": shop.slug}

        return await run("get_order_status", agent, lambda: shop_of_order(order_id), body)

    return mcp
