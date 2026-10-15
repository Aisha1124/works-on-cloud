"""Commerce: search, quote, place order, order status. Shared by MCP, UCP and the dashboard.

Plain Python, no HTTP or MCP code. Prices always come from the catalog and are computed here
with Decimal; prices a buyer sends are ignored (and flagged when they differ).

Errors a buyer agent should see are raised as OrderValidationError (a list of plain messages)
or approval.OrderNotFound.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from agents.approval import service as approval
from agents.risk import scorer as risk
from backend.api.config import Settings, get_settings
from backend.audit import log_event
from backend.models import Actor, Channel, Order, OrderItem, OrderStatus, Product
from backend.store.base import Store
from backend.timeutil import now_sg, to_sg

MAX_LINES = 20
MIN_QTY, MAX_QTY = 1, 500
MAX_NAME_LEN = 80
MAX_NOTE_LEN = 500
CENT = Decimal("0.01")

STATUS_MESSAGES = {
    OrderStatus.auto_approved: "Order confirmed. See you at pickup.",
    OrderStatus.pending_approval: "Waiting for the shop owner to approve this order.",
    OrderStatus.approved: "The shop owner approved this order. See you at pickup.",
    OrderStatus.rejected: "The shop owner could not accept this order.",
    OrderStatus.ready: "Order is ready for pickup.",
    OrderStatus.done: "Order collected. Thank you!",
}


class OrderValidationError(ValueError):
    """One or more problems with the order. str(exc) is safe to show a buyer agent."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(" ".join(errors))


class QuoteItemIn(BaseModel):
    product_id: str
    variant: str | None = None
    options: dict[str, str] = Field(default_factory=dict)
    qty: int
    unit_price: Decimal | None = None  # what the buyer thinks it costs; never used for money


class Quote(BaseModel):
    items: list[OrderItem]
    total: Decimal
    currency: str = "SGD"
    price_mismatch: bool = False
    mismatches: list[str] = Field(default_factory=list)


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT)


def _norm(text: str) -> str:
    return "".join((text or "").lower().split())


def _default_actor(channel: Channel) -> Actor:
    return Actor.owner if channel == Channel.dashboard else Actor.external_agent


# --- Search -------------------------------------------------------------------------


def search_products(
    store: Store, shop_id: str, query: str = "", category: str | None = None
) -> list[Product]:
    """Available products whose name, local name, category or description contain `query`."""
    words = (query or "").lower().split()
    found = []
    for p in store.list_products(shop_id):
        if not p.available:
            continue
        if category and p.category.lower() != category.lower():
            continue
        haystack = " ".join([p.name, p.name_local, p.category, p.description]).lower()
        if all(w in haystack for w in words):
            found.append(p)
    return found


# --- Quote --------------------------------------------------------------------------


def _parse_items(items: list[Any]) -> list[QuoteItemIn]:
    if not isinstance(items, list) or not items:
        raise OrderValidationError(["Add at least one item to the order."])
    if len(items) > MAX_LINES:
        raise OrderValidationError([f"Too many lines: {len(items)}. The limit is {MAX_LINES}."])
    parsed, errors = [], []
    for n, raw in enumerate(items, start=1):
        try:
            parsed.append(raw if isinstance(raw, QuoteItemIn) else QuoteItemIn.model_validate(raw))
        except (ValidationError, InvalidOperation):
            errors.append(f"Item {n}: needs product_id (text) and qty (whole number); "
                          "variant and options are optional.")
    if errors:
        raise OrderValidationError(errors)
    return parsed


def _resolve_line(product: Product, item: QuoteItemIn, n: int,
                  errors: list[str]) -> tuple[str | None, Decimal] | None:
    """-> (variant label, unit price) from the catalog, or None after adding an error."""
    if product.variants:
        labels = [v.label for v in product.variants]
        if item.variant is None or not item.variant.strip():
            if len(product.variants) == 1:
                return product.variants[0].label, product.variants[0].price
            errors.append(f"Item {n}: {product.name} comes in several sizes. "
                          f"Choose a variant: {', '.join(labels)}.")
            return None
        for v in product.variants:
            if _norm(v.label) == _norm(item.variant):
                return v.label, v.price
        errors.append(f"Item {n}: {product.name} has no variant '{item.variant}'. "
                      f"Choose one of: {', '.join(labels)}.")
        return None
    if product.base_price is None:
        errors.append(f"Item {n}: {product.name} has no listed price, so it can't be ordered "
                      "online. Please contact the shop.")
        return None
    unit = product.unit or None
    if item.variant and item.variant.strip() and _norm(item.variant) != _norm(product.unit):
        errors.append(f"Item {n}: {product.name} only comes as "
                      f"{product.unit or 'a single size'}; leave variant empty.")
        return None
    return unit, product.base_price


def _resolve_options(product: Product, item: QuoteItemIn, n: int,
                     errors: list[str]) -> dict[str, str] | None:
    chosen: dict[str, str] = {}
    by_name = {_norm(o.name): o for o in product.options}
    ok = True
    for name, value in item.options.items():
        opt = by_name.get(_norm(name))
        if opt is None:
            known = ", ".join(o.name for o in product.options) or "none"
            errors.append(f"Item {n}: {product.name} has no option '{name}'. Options: {known}.")
            ok = False
            continue
        match = next((c for c in opt.choices if _norm(c) == _norm(value)), None)
        if match is None:
            errors.append(f"Item {n}: '{value}' is not a choice for {opt.name}. "
                          f"Choose one of: {', '.join(opt.choices)}.")
            ok = False
            continue
        chosen[opt.name] = match
    for opt in product.options:
        if opt.choices and opt.name not in chosen and _norm(opt.name) not in {
            _norm(k) for k in item.options
        }:
            errors.append(f"Item {n}: choose {opt.name} for {product.name}: "
                          f"{', '.join(opt.choices)}.")
            ok = False
    return chosen if ok else None


def build_quote(store: Store, shop_id: str, items: list[Any]) -> tuple[Quote, list[Product]]:
    """Validate the items and price them from the catalog. No audit event.

    -> (quote, products in line order). Raises OrderValidationError.
    """
    parsed = _parse_items(items)
    errors: list[str] = []
    lines: list[OrderItem] = []
    products: list[Product] = []
    mismatches: list[str] = []
    for n, item in enumerate(parsed, start=1):
        product = store.get_product(item.product_id)
        if product is None or product.shop_id != shop_id:
            errors.append(f"Item {n}: no product with id '{item.product_id}' in this shop. "
                          "Use search_products to find product ids.")
            continue
        if not product.available:
            errors.append(f"Item {n}: {product.name} is not available right now.")
            continue
        if not MIN_QTY <= item.qty <= MAX_QTY:
            errors.append(f"Item {n}: qty must be between {MIN_QTY} and {MAX_QTY} "
                          f"(got {item.qty}).")
            continue
        resolved = _resolve_line(product, item, n, errors)
        options = _resolve_options(product, item, n, errors)
        if resolved is None or options is None:
            continue
        variant, unit_price = resolved
        if item.unit_price is not None and item.unit_price != unit_price:
            mismatches.append(f"{product.name}{f' ({variant})' if variant else ''}: buyer sent "
                              f"S${item.unit_price}, menu price is S${unit_price:.2f}")
        lines.append(OrderItem(
            product_id=product.id, name=product.name, variant=variant, options=options,
            qty=item.qty, unit_price=_money(unit_price),
            line_total=_money(unit_price * item.qty),
        ))
        products.append(product)
    if errors:
        raise OrderValidationError(errors)
    total = _money(sum((line.line_total for line in lines), Decimal("0")))
    shop = store.get_shop(shop_id)
    return Quote(items=lines, total=total, currency=shop.currency if shop else "SGD",
                 price_mismatch=bool(mismatches), mismatches=mismatches), products


def _require_shop(store: Store, shop_id: str):
    shop = store.get_shop(shop_id)
    if shop is None:
        raise OrderValidationError([f"No shop with id '{shop_id}'."])
    return shop


def _log_quote(store: Store, shop_id: str, quote: Quote, actor: Actor, agent_name: str,
               channel: Channel) -> None:
    by = f" for {agent_name}" if agent_name else ""
    log_event(
        store, shop_id=shop_id, actor=actor, action="quote_created",
        entity_type="quote", entity_id=shop_id,
        summary=f"Quoted {len(quote.items)} line(s), S${quote.total:.2f}{by}",
        details={"total": str(quote.total), "lines": len(quote.items), "channel": channel.value,
                 "agent_name": agent_name, "price_mismatch": quote.price_mismatch,
                 "mismatches": quote.mismatches},
    )


def get_quote(
    store: Store, shop_id: str, items: list[Any], *,
    channel: Channel = Channel.mcp, agent_name: str = "", actor: Actor | None = None,
) -> Quote:
    _require_shop(store, shop_id)
    quote, _ = build_quote(store, shop_id, items)
    _log_quote(store, shop_id, quote, actor or _default_actor(Channel(channel)),
               agent_name, Channel(channel))
    return quote


# --- Orders -------------------------------------------------------------------------


def _parse_pickup(pickup_at: datetime | str) -> datetime:
    if isinstance(pickup_at, str):
        try:
            pickup_at = datetime.fromisoformat(pickup_at.strip())
        except ValueError:
            raise OrderValidationError([
                "pickup_at must be a date and time like 2026-10-17T10:00 (Singapore time)."
            ]) from None
    return to_sg(pickup_at)


async def place_order(
    store: Store,
    shop_id: str,
    items: list[Any],
    customer_name: str,
    customer_phone: str,
    pickup_at: datetime | str,
    note: str = "",
    channel: Channel | str = Channel.mcp,
    agent_name: str = "",
    *,
    actor: Actor | None = None,
    settings: Settings | None = None,
    gemini_client=None,
    now: datetime | None = None,
) -> Order:
    """Quote -> risk check -> approval decision -> save. Every step is in the audit log.

    Raises OrderValidationError for bad input. Never fails because of Gemini.
    """
    settings = settings or get_settings()
    channel = Channel(channel)
    actor = actor or _default_actor(channel)
    now = to_sg(now) if now else now_sg()
    shop = _require_shop(store, shop_id)

    errors = []
    customer_name = " ".join((customer_name or "").split())
    if not customer_name:
        errors.append("customer_name is required.")
    elif len(customer_name) > MAX_NAME_LEN:
        errors.append(f"customer_name is too long (max {MAX_NAME_LEN} characters).")
    if not (customer_phone or "").strip():
        errors.append("customer_phone is required.")
    note = (note or "").strip()
    if len(note) > MAX_NOTE_LEN:
        errors.append(f"note is too long (max {MAX_NOTE_LEN} characters).")
    pickup = _parse_pickup(pickup_at)
    if pickup <= now:
        errors.append("pickup_at must be in the future (Singapore time).")
    if errors:
        raise OrderValidationError(errors)

    quote, products = build_quote(store, shop_id, items)
    _log_quote(store, shop_id, quote, actor, agent_name, channel)

    phone = risk.normalize_sg_phone(customer_phone) or customer_phone.strip()
    previous = store.list_orders(shop_id)
    order = Order(
        shop_id=shop_id, items=quote.items, total=quote.total,
        customer_name=customer_name, customer_phone=phone, pickup_at=pickup, note=note,
        channel=channel, agent_name=agent_name, status=OrderStatus.pending_approval,
    )
    by = f" via {agent_name}" if agent_name else ""
    log_event(
        store, shop_id=shop_id, actor=actor, action="order_received",
        entity_type="order", entity_id=order.id,
        summary=f"Order {order.id} received{by} ({channel.value}), S${order.total:.2f}",
        details={"channel": channel.value, "agent_name": agent_name,
                 "items": len(order.items), "total": str(order.total)},
    )

    facts = risk.OrderFacts(
        shop=shop, lines=[(p, line.qty) for p, line in zip(products, quote.items, strict=True)],
        total=quote.total, phone=customer_phone, agent_name=agent_name, pickup_at=pickup,
        note=note, price_mismatch=quote.price_mismatch, previous_orders=previous, now=now,
    )
    order.risk, source = await risk.assess(facts, settings, gemini_client)
    log_event(
        store, shop_id=shop_id, actor=Actor.risk_agent, action="risk_scored",
        entity_type="order", entity_id=order.id,
        summary=f"Risk {order.risk.level.value.upper()} {order.risk.score}/100",
        details={"score": order.risk.score, "level": order.risk.level.value,
                 "reasons": order.risk.reasons, "explanation": order.risk.explanation,
                 "explanation_source": source, "mismatches": quote.mismatches},
    )

    order.status, why = approval.decide(shop, order.risk, order.total)
    store.save_order(order)
    held = order.status == OrderStatus.pending_approval
    log_event(
        store, shop_id=shop_id, actor=Actor.system,
        action="order_held" if held else "order_auto_approved",
        entity_type="order", entity_id=order.id,
        summary=(f"{'Held' if held else 'Auto-approved'} order {order.id} "
                 f"(S${order.total:.2f}, risk {order.risk.level.value.upper()} "
                 f"{order.risk.score}): {why}"),
        details={"why": why},
    )
    return order


def get_order_status(store: Store, shop_id: str, order_id: str) -> dict[str, Any]:
    """What a buyer agent may see. No risk details, so the scoring can't be gamed."""
    order = approval.get_shop_order(store, shop_id, order_id)
    shop = store.get_shop(shop_id)
    return {
        "order_id": order.id,
        "status": order.status.value,
        "message": STATUS_MESSAGES[order.status],
        "rejection_reason": order.rejection_reason,
        "items": [line.model_dump(mode="json") for line in order.items],
        "total": str(order.total),
        "currency": shop.currency if shop else "SGD",
        "pickup_at": to_sg(order.pickup_at).isoformat(),
        "customer_name": order.customer_name,
    }
