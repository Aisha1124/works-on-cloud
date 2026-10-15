"""MCP server for external AI shopping agents (MCP Python SDK v2, MCPServer, streamable HTTP).

Each tool is a thin adapter over agents/commerce: find the published shop by slug, call the
service with channel="mcp", and turn known errors into one plain sentence the buyer agent can
act on. Every call, failed or not, is written to the audit log as actor=external_agent.
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
from agents.commerce import service as commerce
from backend.api.config import Settings
from backend.external import (
    GENERIC_ERROR, MAX_ID_LEN, MAX_QUERY_LEN, RATE_LIMIT_MESSAGE, RateLimiter, ShopNotFound,
    area_of, audit_external_call, clean_agent_name, client_key, published_shop, published_shops,
)
from backend.models import Channel, OrderStatus, Shop
from backend.store.base import Store
from backend.timeutil import to_sg

log = logging.getLogger(__name__)

HELD_MESSAGE = "Held for owner approval"

INSTRUCTIONS = (
    "KampungCart lists small Singapore shops (home bakers, hawker stalls, heartland shops). "
    "Typical flow: find_shops -> get_shop -> search_products -> get_quote -> place_order -> "
    "get_order_status. Prices are in SGD and always come from the shop's menu. Payment is "
    "made at pickup; no payment details are collected. Orders that are large or look risky "
    "are held until the shop owner approves them, so check get_order_status later."
)


class OrderLineIn(BaseModel):
    product_id: str = Field(description="Product id from search_products.", max_length=MAX_ID_LEN)
    qty: int = Field(description="How many packs or pieces of this product/variant (1-500).")
    variant: str | None = Field(
        default=None, max_length=80,
        description="Size or pack label exactly as listed in the product's variants, e.g. "
                    "'20 pcs'. Leave empty when the product has no variants.")
    options: dict[str, str] = Field(
        default_factory=dict,
        description="Choices for the product's options, e.g. {'Flavour': 'Pandan'}. "
                    "Required options must be chosen.")


def _items(items: list[OrderLineIn]) -> list[dict[str, Any]]:
    return [i.model_dump() for i in items]


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _shop_summary(shop: Shop) -> dict[str, Any]:
    return {"slug": shop.slug, "name": shop.name, "type": shop.shop_type, "area": area_of(shop)}


def _product_out(p) -> dict[str, Any]:
    return {
        "product_id": p.id, "name": p.name, "name_local": p.name_local, "category": p.category,
        "price": _money(p.base_price) if p.base_price is not None else None,
        "unit": p.unit,
        "variants": [{"label": v.label, "price": _money(v.price)} for v in p.variants],
        "options": [{"name": o.name, "choices": o.choices} for o in p.options],
        "description": p.description,
    }


def _quote_out(quote: commerce.Quote) -> dict[str, Any]:
    return {
        "items": [{"product_id": i.product_id, "name": i.name, "variant": i.variant,
                   "options": i.options, "qty": i.qty, "unit_price": _money(i.unit_price),
                   "line_total": _money(i.line_total)} for i in quote.items],
        "total": _money(quote.total),
        "currency": quote.currency,
        "payment": "Pay at pickup",
    }


def _error(message: str) -> CallToolResult:
    """An error result whose text is exactly our sentence (no SDK prefix, no internals)."""
    return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)


def create_mcp_server(store: Store, settings: Settings,
                      order_limiter: RateLimiter | None = None) -> MCPServer:
    """A new server bound to this app's store. One per FastAPI app (tests build many)."""
    limiter = order_limiter or RateLimiter(10, 60.0)
    mcp = MCPServer("KampungCart", instructions=INSTRUCTIONS, version="0.1.0")

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

    async def run(call: str, agent_name: str, slug: str | None,
                  body: Callable[[Shop | None], Awaitable[Any] | Any]) -> Any:
        """Resolve the shop, run the tool body, audit the call, map errors to sentences."""
        shop_id = None
        try:
            shop = published_shop(store, slug) if slug is not None else None
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

        return await run("find_shops", agent, None, body)

    @mcp.tool(description="Details of one shop: address, opening hours, phone, currency and "
                          "the product categories it sells.")
    async def get_shop(
        ctx: Context,
        slug: Annotated[str, Field(description="Shop slug from find_shops.", max_length=60)],
    ) -> dict[str, Any]:
        agent, _ = caller(ctx)

        def body(shop: Shop):
            categories = sorted({p.category for p in store.list_products(shop.id)
                                 if p.available and p.category})
            return {**_shop_summary(shop), "tagline": shop.tagline, "address": shop.address,
                    "hours": shop.hours, "phone": shop.phone, "currency": shop.currency,
                    "categories": categories, "payment": "Pay at pickup",
                    "fulfillment": "Pickup at the shop"}

        return await run("get_shop", agent, slug, body)

    @mcp.tool(description="Search a shop's available products. Returns product ids, prices, "
                          "variants (sizes/packs) and options (e.g. flavours) needed to order.")
    async def search_products(
        ctx: Context,
        slug: Annotated[str, Field(description="Shop slug from find_shops.", max_length=60)],
        query: Annotated[str, Field(description="Words to match, e.g. 'kuih lapis'. Empty "
                                                "returns everything.", max_length=MAX_QUERY_LEN)] = "",
        category: Annotated[str | None, Field(description="Only this category (from get_shop).",
                                              max_length=60)] = None,
    ) -> dict[str, Any]:
        agent, _ = caller(ctx)

        def body(shop: Shop):
            found = commerce.search_products(store, shop.id, query, category)
            return {"products": [_product_out(p) for p in found], "count": len(found),
                    "currency": shop.currency}

        return await run("search_products", agent, slug, body)

    @mcp.tool(description="Price a list of items from the shop's menu without ordering. "
                          "Totals are computed by the shop, never by the agent.")
    async def get_quote(
        ctx: Context,
        slug: Annotated[str, Field(description="Shop slug from find_shops.", max_length=60)],
        items: Annotated[list[OrderLineIn], Field(description="1-20 order lines.")],
        agent_name: Annotated[str | None, Field(description="Your name, e.g. 'Gemini Shopper'.",
                                                max_length=80)] = None,
    ) -> dict[str, Any]:
        agent, _ = caller(ctx, agent_name)

        def body(shop: Shop):
            quote = commerce.get_quote(store, shop.id, _items(items), channel=Channel.mcp,
                                       agent_name=agent)
            return _quote_out(quote)

        return await run("get_quote", agent, slug, body)

    @mcp.tool(description="Place a pickup order. Payment is at pickup. Returns order_id, status "
                          "and a message. Status 'pending_approval' means the order is held "
                          "for the shop owner; check get_order_status later.")
    async def place_order(
        ctx: Context,
        slug: Annotated[str, Field(description="Shop slug from find_shops.", max_length=60)],
        items: Annotated[list[OrderLineIn], Field(description="1-20 order lines.")],
        customer_name: Annotated[str, Field(description="Buyer's name (max 80 characters).")],
        customer_phone: Annotated[str, Field(description="Buyer's Singapore phone number, e.g. "
                                                         "+65 9123 4567.", max_length=30)],
        pickup_at: Annotated[str, Field(description="Pickup date and time in Singapore time, "
                                                    "ISO format, e.g. 2026-10-17T10:00.",
                                        max_length=40)],
        note: Annotated[str, Field(description="Optional note for the shop (max 500 "
                                               "characters).")] = "",
        agent_name: Annotated[str | None, Field(description="Your name, e.g. 'Gemini Shopper'.",
                                                max_length=80)] = None,
    ) -> dict[str, Any]:
        agent, key = caller(ctx, agent_name)

        async def body(shop: Shop):
            if not limiter.allow(key):
                raise ToolError(RATE_LIMIT_MESSAGE)
            order = await commerce.place_order(
                store, shop.id, _items(items), customer_name, customer_phone, pickup_at, note,
                Channel.mcp, agent, settings=settings)
            held = order.status == OrderStatus.pending_approval
            return {"order_id": order.id, "status": order.status.value,
                    "total": _money(order.total), "currency": shop.currency,
                    "pickup_at": to_sg(order.pickup_at).isoformat(),
                    "message": HELD_MESSAGE if held else commerce.STATUS_MESSAGES[order.status],
                    "payment": "Pay at pickup"}

        return await run("place_order", agent, slug, body)

    @mcp.tool(description="Current status of an order: auto_approved, pending_approval, "
                          "approved, rejected, ready or done, with a plain message.")
    async def get_order_status(
        ctx: Context,
        slug: Annotated[str, Field(description="Shop slug the order was placed with.",
                                   max_length=60)],
        order_id: Annotated[str, Field(description="order_id from place_order.",
                                       max_length=MAX_ID_LEN)],
    ) -> dict[str, Any]:
        agent, _ = caller(ctx)
        return await run("get_order_status", agent, slug,
                         lambda shop: commerce.get_order_status(store, shop.id, order_id))

    return mcp
