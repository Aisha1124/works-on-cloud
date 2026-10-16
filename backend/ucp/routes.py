"""UCP REST binding: discovery profile, catalog search/lookup and checkout sessions.

A thin layer over agents/commerce (channel="ucp"): prices come from commerce.build_quote /
get_quote and orders from commerce.place_order. Every request is audited as external_agent.
What is and isn't implemented: docs/architecture/UCP_IMPLEMENTATION.md.
"""

import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.commerce import service as commerce
from backend.api.config import Settings
from backend.external import (
    GENERIC_ERROR, MAX_ID_LEN, MAX_QUERY_LEN, RATE_LIMIT_MESSAGE, ShopNotFound,
    audit_external_call, clean_agent_name, client_key, published_shop, published_shops,
)
from backend.models import (
    Channel, CheckoutBuyer, CheckoutLine, CheckoutSession, OrderStatus, Shop, utc_now,
)
from backend.store.base import Store
from backend.ucp import convert
from backend.ucp.profile import (
    API_PREFIX, CATALOG_LOOKUP, CATALOG_SEARCH, CHECKOUT, PAY_AT_PICKUP_ID,
    PAY_AT_PICKUP_SCHEMA, PAY_AT_PICKUP_SCHEMA_PATH, base_url, business_profile, envelope,
)

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 64 * 1024
COMPLETED = {OrderStatus.auto_approved, OrderStatus.approved, OrderStatus.ready,
             OrderStatus.done}


class UcpError(Exception):
    """A protocol-level error: HTTP status + {code, content}. content is safe to show."""

    def __init__(self, status: int, code: str, content: str):
        super().__init__(content)
        self.status, self.code, self.content = status, code, content


# --- Request bodies (unknown fields are ignored, as UCP allows extensions) ---------------


class _In(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ItemRef(_In):
    id: str = Field(min_length=1, max_length=MAX_ID_LEN + 8)


class LineVendor(_In):
    options: dict[str, str] = Field(default_factory=dict, max_length=10)


class LineIn(_In):
    id: str | None = Field(default=None, max_length=40)
    item: ItemRef
    quantity: int
    kampungcart: LineVendor | None = None


class BuyerIn(_In):
    first_name: str = Field(default="", max_length=commerce.MAX_NAME_LEN)
    last_name: str = Field(default="", max_length=commerce.MAX_NAME_LEN)
    email: str = Field(default="", max_length=254)
    phone_number: str = Field(default="", max_length=30)


class CheckoutVendor(_In):
    pickup_at: str = Field(default="", max_length=40)
    note: str = Field(default="", max_length=commerce.MAX_NOTE_LEN)
    agent_name: str = Field(default="", max_length=80)


class CheckoutIn(_In):
    line_items: list[LineIn] = Field(min_length=1, max_length=commerce.MAX_LINES)
    buyer: BuyerIn | None = None
    kampungcart: CheckoutVendor | None = None


class InstrumentIn(_In):
    handler_id: str = Field(default="", max_length=100)


class PaymentIn(_In):
    instruments: list[InstrumentIn] = Field(default_factory=list, max_length=5)


class CompleteIn(_In):
    payment: PaymentIn | None = None


class SearchFilters(_In):
    categories: list[str] = Field(default_factory=list, max_length=10)
    shop: str | None = Field(default=None, max_length=60)


class Pagination(_In):
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=20)


class SearchIn(_In):
    query: str = Field(default="", max_length=MAX_QUERY_LEN)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    pagination: Pagination = Field(default_factory=Pagination)


class LookupIn(_In):
    ids: list[str] = Field(min_length=1, max_length=50)


class ProductIn(_In):
    id: str = Field(min_length=1, max_length=MAX_ID_LEN + 8)


async def read_body(request: Request, model: type[_In], *, optional: bool = False) -> Any:
    """Parse and validate the JSON body. Size-capped; errors are plain sentences."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise UcpError(413, "request_too_large", f"Request body is over {MAX_BODY_BYTES} bytes.")
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_BODY_BYTES:
            raise UcpError(413, "request_too_large",
                           f"Request body is over {MAX_BODY_BYTES} bytes.")
    if not raw.strip():
        if optional:
            return model()
        raise UcpError(400, "invalid_request", "Send a JSON request body.")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise UcpError(400, "invalid_request", "The request body is not valid JSON.") from None
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = []
        for err in exc.errors()[:5]:
            where = ".".join(str(p) for p in err["loc"]) or "body"
            problems.append(f"{where}: {err['msg']}")
        raise UcpError(400, "invalid_request", "; ".join(problems) + ".") from None


# --- Helpers ---------------------------------------------------------------------------

_PROFILE_RE = re.compile(r'profile\s*=\s*"([^"]{1,500})"')


def header_agent_name(request: Request) -> str:
    """The host of the UCP-Agent profile URL, e.g. 'shopper.example.com'. Data only."""
    match = _PROFILE_RE.search(request.headers.get("ucp-agent", ""))
    return clean_agent_name(urlsplit(match.group(1)).hostname or "") if match else ""


def message(type_: str, code: str, content: str, path: str | None = None,
            severity: str | None = "recoverable") -> dict[str, Any]:
    msg: dict[str, Any] = {"type": type_, "code": code, "content": content}
    if path:
        msg["path"] = path
    if severity and type_ == "error":
        msg["severity"] = severity
    return msg


def business_error(settings: Settings, capability: str, messages: list[dict]) -> dict:
    """HTTP 200 + ucp.status = error: the request was understood, the business said no."""
    return {"ucp": envelope(settings, capability, status="error"), "messages": messages}


def _commerce_items(store: Store, lines: list[CheckoutLine]) -> list[dict[str, Any]]:
    items = []
    for line in lines:
        pid, index = convert.parse_item_id(line.item_id)
        product = store.get_product(pid)
        variant = convert.variant_label(product, index) if product else None
        items.append({"product_id": pid, "variant": variant, "options": line.options,
                      "qty": line.quantity})
    return items


def _shop_for_items(store: Store, item_ids: list[str]) -> Shop:
    """The one published shop all items belong to."""
    shop_ids, missing = set(), []
    for item_id in item_ids:
        product = store.get_product(convert.parse_item_id(item_id)[0])
        shop = store.get_shop(product.shop_id) if product else None
        if shop is None or not shop.published:
            missing.append(item_id)
        else:
            shop_ids.add(shop.id)
    if missing:
        raise commerce.OrderValidationError(
            [f"No item with id '{i}'. Use catalog search to find item ids." for i in missing])
    if len(shop_ids) > 1:
        raise commerce.OrderValidationError(
            ["A checkout can only contain items from one shop. Make one checkout per shop."])
    return store.get_shop(shop_ids.pop())


def _lines(body: CheckoutIn) -> list[CheckoutLine]:
    return [CheckoutLine(id=line.id or f"li_{n}", item_id=line.item.id, quantity=line.quantity,
                         options=(line.kampungcart.options if line.kampungcart else {}))
            for n, line in enumerate(body.line_items, start=1)]


def _missing(session: CheckoutSession) -> list[dict[str, Any]]:
    out = []
    if not (session.buyer.first_name.strip() or session.buyer.last_name.strip()):
        out.append(message("error", "missing", "Buyer name is required for pickup.",
                           "$.buyer.first_name"))
    if not session.buyer.phone_number.strip():
        out.append(message("error", "missing", "Buyer phone number is required.",
                           "$.buyer.phone_number"))
    if not session.pickup_at.strip():
        out.append(message("error", "missing", "Pickup time is required, in Singapore time, "
                           "e.g. 2026-10-17T10:00.", "$.kampungcart.pickup_at"))
    else:
        try:
            datetime.fromisoformat(session.pickup_at.strip())
        except ValueError:
            out.append(message("error", "invalid", "pickup_at must be a date and time like "
                               "2026-10-17T10:00 (Singapore time).", "$.kampungcart.pickup_at"))
    return out


def _apply(session: CheckoutSession, body: CheckoutIn, agent: str) -> None:
    session.lines = _lines(body)
    session.buyer = CheckoutBuyer(**body.buyer.model_dump()) if body.buyer else CheckoutBuyer()
    vendor = body.kampungcart or CheckoutVendor()
    session.pickup_at, session.note = vendor.pickup_at.strip(), vendor.note.strip()
    session.agent_name = clean_agent_name(vendor.agent_name) or agent or session.agent_name
    session.updated_at = utc_now()


# --- Router ----------------------------------------------------------------------------


def ucp_router() -> APIRouter:
    router = APIRouter()

    async def respond(request: Request, call: str, agent: str,
                      fn: Callable[[dict], Awaitable[tuple[str | None, Any]]]) -> JSONResponse:
        """Run a route body -> (shop_id, response). Audits the call; never leaks internals."""
        store: Store = request.app.state.store
        holder = {"shop_id": None, "agent": agent}
        try:
            shop_id, result = await fn(holder)
        except UcpError as exc:
            audit_external_call(store, shop_id=holder["shop_id"], channel=Channel.ucp,
                                call=call, agent_name=holder["agent"], ok=False,
                                error=exc.content)
            headers = {"Retry-After": "60"} if exc.status == 429 else None
            return JSONResponse({"code": exc.code, "content": exc.content},
                                status_code=exc.status, headers=headers)
        except Exception:
            log.exception("UCP %s failed", call)
            audit_external_call(store, shop_id=holder["shop_id"], channel=Channel.ucp,
                                call=call, agent_name=holder["agent"], ok=False,
                                error="internal error")
            return JSONResponse({"code": "internal_error", "content": GENERIC_ERROR},
                                status_code=500)
        status_code = 200
        if isinstance(result, tuple):
            result, status_code = result
        failed = isinstance(result, dict) and result.get("ucp", {}).get("status") == "error"
        errors = [m["content"] for m in result.get("messages", []) if m.get("type") == "error"]
        audit_external_call(store, shop_id=shop_id or holder["shop_id"], channel=Channel.ucp,
                            call=call, agent_name=holder["agent"], ok=not failed,
                            error=" ".join(errors) if failed else "",
                            entity_id=result.get("id", "") if isinstance(result, dict) else "")
        return JSONResponse(result, status_code=status_code)

    # --- Discovery ---

    @router.get("/.well-known/ucp", include_in_schema=False)
    async def profile(request: Request):
        async def body(_):
            return None, business_profile(request.app.state.settings)

        response = await respond(request, "ucp.profile", header_agent_name(request), body)
        response.headers["Access-Control-Allow-Origin"] = "*"  # public discovery doc only
        return response

    @router.get(PAY_AT_PICKUP_SCHEMA_PATH, include_in_schema=False)
    def pay_at_pickup_schema():
        return JSONResponse(PAY_AT_PICKUP_SCHEMA)

    # --- Catalog ---

    @router.post(f"{API_PREFIX}/catalog/search")
    async def catalog_search(request: Request):
        async def body(h):
            store, settings = request.app.state.store, request.app.state.settings
            q = await read_body(request, SearchIn, optional=True)
            if q.filters.shop:
                try:
                    shops = [published_shop(store, q.filters.shop)]
                except ShopNotFound as exc:
                    return None, business_error(settings, CATALOG_SEARCH,
                                                [message("error", "not_found", str(exc),
                                                         "$.filters.shop", "unrecoverable")])
                h["shop_id"] = shops[0].id
            else:
                shops = published_shops(store)
            wanted = {c.strip().lower() for c in q.filters.categories if c.strip()}
            found = [convert.product_out(p, shop) for shop in shops
                     for p in commerce.search_products(store, shop.id, q.query)
                     if convert.orderable(p) and (not wanted or p.category.lower() in wanted)]
            start = int(q.pagination.cursor) if (q.pagination.cursor or "").isdigit() else 0
            page = found[start:start + q.pagination.limit]
            more = start + len(page) < len(found)
            return h["shop_id"], {
                "ucp": envelope(settings, CATALOG_SEARCH),
                "products": page,
                "pagination": {"cursor": str(start + len(page)) if more else None,
                               "has_next_page": more, "total_count": len(found)},
            }

        return await respond(request, "catalog.search", header_agent_name(request), body)

    def _lookup_one(store: Store, item_id: str) -> tuple[Shop, Any] | None:
        product = store.get_product(convert.parse_item_id(item_id.strip())[0])
        shop = store.get_shop(product.shop_id) if product else None
        if shop is None or not shop.published or not convert.orderable(product):
            return None
        return shop, product

    @router.post(f"{API_PREFIX}/catalog/lookup")
    async def catalog_lookup(request: Request):
        async def body(h):
            store, settings = request.app.state.store, request.app.state.settings
            q = await read_body(request, LookupIn)
            products, messages, seen = [], [], set()
            for item_id in q.ids:
                hit = _lookup_one(store, item_id[:MAX_ID_LEN + 8])
                if hit is None:
                    messages.append(message("info", "not_found", item_id[:MAX_ID_LEN + 8]))
                elif hit[1].id not in seen:
                    seen.add(hit[1].id)
                    products.append(convert.product_out(hit[1], hit[0]))
            out = {"ucp": envelope(settings, CATALOG_LOOKUP), "products": products}
            if messages:
                out["messages"] = messages
            return None, out

        return await respond(request, "catalog.lookup", header_agent_name(request), body)

    @router.post(f"{API_PREFIX}/catalog/product")
    async def catalog_product(request: Request):
        async def body(h):
            store, settings = request.app.state.store, request.app.state.settings
            q = await read_body(request, ProductIn)
            hit = _lookup_one(store, q.id)
            if hit is None:
                return None, business_error(settings, CATALOG_LOOKUP, [message(
                    "error", "not_found", f"Product not found: {q.id}", None, "unrecoverable")])
            return hit[0].id, {"ucp": envelope(settings, CATALOG_LOOKUP),
                               "product": convert.product_out(hit[1], hit[0])}

        return await respond(request, "catalog.product", header_agent_name(request), body)

    # --- Checkout ---

    def render(request: Request, session: CheckoutSession,
               extra: list[dict] | None = None) -> dict[str, Any]:
        """The UCP Checkout object for a session. Prices come from the order once placed,
        before that from a fresh commerce quote (the catalog may have changed)."""
        store, settings = request.app.state.store, request.app.state.settings
        shop = store.get_shop(session.shop_id)
        currency = shop.currency if shop else "SGD"
        messages: list[dict] = []
        order = store.get_order(session.order_id) if session.order_id else None
        line_items: list[dict] = []
        total = None
        if order is not None:
            line_items = [convert.line_out(line.id, line.item_id, item, currency)
                          for line, item in zip(session.lines, order.items, strict=False)]
            total = order.total
            if order.status in COMPLETED:
                status = "completed"
            elif order.status == OrderStatus.pending_approval:
                status = "complete_in_progress"
                messages.append(message("info", "held_for_approval",
                                        commerce.buyer_message(shop, order)))
            else:
                status = "canceled"
                why = f": {order.rejection_reason}" if order.rejection_reason else "."
                messages.append(message("error", "rejected_by_shop",
                                        f"The shop owner could not accept this order{why}",
                                        None, "unrecoverable"))
        else:
            try:
                quote, _ = commerce.build_quote(store, session.shop_id,
                                                _commerce_items(store, session.lines))
                line_items = [convert.line_out(line.id, line.item_id, item, currency)
                              for line, item in zip(session.lines, quote.items, strict=True)]
                total = quote.total
                problems = _missing(session)
            except commerce.OrderValidationError as exc:
                line_items = [{"id": line.id, "item": {"id": line.item_id},
                               "quantity": line.quantity, "totals": []}
                              for line in session.lines]
                problems = [message("error", "invalid", e, "$.line_items") for e in exc.errors]
            messages += problems
            if session.canceled:
                status = "canceled"
            else:
                status = "incomplete" if problems else "ready_for_complete"
        out: dict[str, Any] = {
            "ucp": envelope(settings, CHECKOUT),
            "id": session.id,
            "status": status,
            "currency": currency,
            "line_items": line_items,
            "totals": convert.totals(total) if total is not None else [],
            "links": [],
            "buyer": session.buyer.model_dump(),
            "kampungcart": {
                "shop": {"slug": shop.slug, "name": shop.name, "address": shop.address,
                         "hours": shop.hours, "phone": shop.phone} if shop else None,
                "pickup_at": session.pickup_at, "note": session.note,
                "payment": "Pay at pickup",
                "order_id": order.id if order else None,
                "order_status": order.status.value if order else None,
            },
        }
        if order is not None and status == "completed":
            out["order"] = {"id": order.id, "permalink_url": (
                f"{base_url(settings)}{API_PREFIX}/checkout-sessions/{session.id}")}
        messages += extra or []
        if messages:
            out["messages"] = messages
        return out

    def load(request: Request, checkout_id: str, h: dict) -> CheckoutSession:
        session = request.app.state.store.get_checkout(checkout_id[:40])
        if session is None:
            raise UcpError(404, "not_found", f"No checkout session '{checkout_id[:40]}'.")
        h["shop_id"] = session.shop_id
        h["agent"] = session.agent_name or h["agent"]  # the name it gave at create
        return session

    @router.post(f"{API_PREFIX}/checkout-sessions")
    async def create_checkout(request: Request):
        async def body(h):
            store, settings = request.app.state.store, request.app.state.settings
            q = await read_body(request, CheckoutIn)
            if q.kampungcart and q.kampungcart.agent_name:
                h["agent"] = clean_agent_name(q.kampungcart.agent_name)
            try:
                shop = _shop_for_items(store, [line.item.id for line in q.line_items])
                h["shop_id"] = shop.id
                session = CheckoutSession(shop_id=shop.id, lines=[])
                _apply(session, q, h["agent"])
                # Prices and validates the items; logs quote_created as external_agent.
                commerce.get_quote(store, shop.id, _commerce_items(store, session.lines),
                                   channel=Channel.ucp, agent_name=session.agent_name)
            except commerce.OrderValidationError as exc:
                return h["shop_id"], business_error(settings, CHECKOUT, [
                    message("error", "invalid", e, "$.line_items", "unrecoverable")
                    for e in exc.errors])
            store.save_checkout(session)
            return shop.id, (render(request, session), 201)

        return await respond(request, "checkout.create", header_agent_name(request), body)

    @router.get(f"{API_PREFIX}/checkout-sessions/{{checkout_id}}")
    async def get_checkout(request: Request, checkout_id: str):
        async def body(h):
            session = load(request, checkout_id, h)
            return session.shop_id, render(request, session)

        return await respond(request, "checkout.get", header_agent_name(request), body)

    @router.put(f"{API_PREFIX}/checkout-sessions/{{checkout_id}}")
    async def update_checkout(request: Request, checkout_id: str):
        async def body(h):
            store = request.app.state.store
            session = load(request, checkout_id, h)
            q = await read_body(request, CheckoutIn)
            if session.order_id or session.canceled:
                return session.shop_id, render(request, session, [message(
                    "error", "invalid_state", "This checkout is already finished and can't "
                    "be changed. Start a new checkout.", None, "unrecoverable")])
            updated = session.model_copy(deep=True)
            _apply(updated, q, h["agent"])
            try:
                if _shop_for_items(store, [line.item_id for line in updated.lines]).id != (
                        session.shop_id):
                    raise commerce.OrderValidationError(
                        ["A checkout can't move to another shop. Start a new checkout."])
                commerce.get_quote(store, session.shop_id, _commerce_items(store, updated.lines),
                                   channel=Channel.ucp, agent_name=updated.agent_name)
            except commerce.OrderValidationError as exc:
                # Rejected as a whole: the checkout stays as it was.
                return session.shop_id, render(request, session, [
                    message("error", "invalid", e, "$.line_items") for e in exc.errors])
            store.save_checkout(updated)
            return session.shop_id, render(request, updated)

        return await respond(request, "checkout.update", header_agent_name(request), body)

    @router.post(f"{API_PREFIX}/checkout-sessions/{{checkout_id}}/complete")
    async def complete_checkout(request: Request, checkout_id: str):
        async def body(h):
            store, settings = request.app.state.store, request.app.state.settings
            session = load(request, checkout_id, h)
            q = await read_body(request, CompleteIn, optional=True)
            if session.order_id or session.canceled:
                return session.shop_id, render(request, session)  # repeat: same answer
            if q.payment and q.payment.instruments and not any(
                    i.handler_id == PAY_AT_PICKUP_ID for i in q.payment.instruments):
                return session.shop_id, render(request, session, [message(
                    "error", "payment_failed", "This shop only takes payment at pickup. Use "
                    f"payment handler '{PAY_AT_PICKUP_ID}', or send no payment.",
                    "$.payment")])
            current = render(request, session)
            if current["status"] != "ready_for_complete":
                return session.shop_id, current
            if not request.app.state.order_limiter.allow(
                    client_key(request.headers, request.client.host if request.client else None)):
                raise UcpError(429, "rate_limited", RATE_LIMIT_MESSAGE)
            buyer = session.buyer
            try:
                order = await commerce.place_order(
                    store, session.shop_id, _commerce_items(store, session.lines),
                    f"{buyer.first_name} {buyer.last_name}".strip(), buyer.phone_number,
                    session.pickup_at, session.note, Channel.ucp, session.agent_name,
                    settings=settings)
            except commerce.OrderValidationError as exc:
                return session.shop_id, render(request, session, [
                    message("error", "invalid", e) for e in exc.errors])
            session.order_id = order.id
            session.updated_at = utc_now()
            store.save_checkout(session)
            return session.shop_id, render(request, session)

        return await respond(request, "checkout.complete", header_agent_name(request), body)

    @router.post(f"{API_PREFIX}/checkout-sessions/{{checkout_id}}/cancel")
    async def cancel_checkout(request: Request, checkout_id: str):
        async def body(h):
            store = request.app.state.store
            session = load(request, checkout_id, h)
            if session.order_id:
                return session.shop_id, render(request, session, [message(
                    "error", "invalid_state", "The order is already placed and can't be "
                    "canceled here. Please contact the shop.", None, "unrecoverable")])
            session.canceled = True
            session.updated_at = utc_now()
            store.save_checkout(session)
            return session.shop_id, render(request, session)

        return await respond(request, "checkout.cancel", header_agent_name(request), body)

    return router
