"""Commerce: search, quote, place order, order status. Shared by MCP, UCP and the dashboard.

Plain Python, no HTTP or MCP code. Prices always come from the catalog and are computed here
with Decimal; prices a buyer sends are ignored (and flagged when they differ).

Errors a buyer agent should see are raised as OrderValidationError (a list of plain messages)
or approval.OrderNotFound.
"""

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from agents.approval import service as approval
from agents.commerce import pickup
from agents.risk import scorer as risk
from backend.api.config import Settings, get_settings
from backend import emails, mailer, notify, owner_session
from backend.audit import log_event
from backend.external import mask_phone
from backend.models import (
    Actor, Channel, Order, OrderItem, OrderStatus, Product, Risk, Shop, UnpricedRequest,
)
from backend.store.base import Store
from backend.timeutil import now_sg, to_sg

log = logging.getLogger(__name__)

MAX_LINES = 20
MIN_QTY, MAX_QTY = 1, 500
MAX_NAME_LEN = 80
MAX_NOTE_LEN = 500
MAX_ITEM_NAME_LEN = 120
MAX_REQUEST_LEN = 200
CENT = Decimal("0.01")

STATUS_MESSAGES = {
    OrderStatus.auto_approved: "Order confirmed. See you at pickup.",
    OrderStatus.pending_approval: "Waiting for the shop owner to approve this order.",
    OrderStatus.approved: "The shop owner approved this order. See you at pickup.",
    OrderStatus.rejected: "The shop owner could not accept this order.",
    OrderStatus.ready: "Order is ready for pickup.",
    OrderStatus.done: "Order collected. Thank you!",
    OrderStatus.cancelled: "This order was cancelled by the customer.",
}
EXPIRED_MESSAGE = "The shop didn't respond in time, so this order is cancelled."

# Model status -> what a buyer (agent or customer) sees. Stored orders, the dashboard and UCP
# keep the model statuses.
BUYER_STATUS = {
    OrderStatus.auto_approved: "confirmed",
    OrderStatus.approved: "confirmed",
    OrderStatus.pending_approval: "pending_owner_approval",
    OrderStatus.rejected: "rejected",
    OrderStatus.ready: "ready",
    OrderStatus.done: "done",
    OrderStatus.cancelled: "cancelled",
}

# Review code -> plain sentence for the customer when their order is held. "risk" covers holds
# from the risk score alone and says nothing about how scoring works.
HOLD_SENTENCES = {
    "not_on_menu": "Some items aren't on the shop's menu, so the owner needs to price them.",
    "custom_request": "Your order has a custom request that the owner needs to confirm.",
    "unusual_qty": "This is a bigger quantity than the shop usually makes.",
    "over_limit": "Orders over S${limit:.2f} need the owner's OK.",
    "risk": "The owner checks some orders personally before confirming them.",
}
SENT_TO_OWNER = "Your order has been sent to the owner for approval."


class OrderValidationError(ValueError):
    """One or more problems with the order. str(exc) is safe to show a buyer agent."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(" ".join(errors))


class PickupUnavailable(OrderValidationError):
    """The shop can't take a pickup at that time. Carries the next valid times so an agent
    can suggest one."""

    def __init__(self, reason: str, next_slots: list[datetime]):
        self.reason = reason
        self.next_slots = next_slots
        times = ", ".join(pickup.iso(s) for s in next_slots)
        tail = (f" Next available pickup times (Singapore): {times}." if times
                else " There are no free pickup times in the next weeks.")
        super().__init__([reason + tail])


class QuoteItemIn(BaseModel):
    product_id: str
    variant: str | None = None
    options: dict[str, str] = Field(default_factory=dict)
    qty: int
    unit_price: Decimal | None = None  # what the buyer thinks it costs; never used for money
    request: str = ""  # custom request for this line (untrusted text)


class Quote(BaseModel):
    items: list[OrderItem]
    total: Decimal
    currency: str = "SGD"
    price_mismatch: bool = False
    mismatches: list[str] = Field(default_factory=list)
    unpriced: list[UnpricedRequest] = Field(default_factory=list)  # not on the menu, no price
    review_reasons: list[str] = Field(default_factory=list)  # why the owner must approve
    review_codes: list[str] = Field(default_factory=list)  # HOLD_SENTENCES keys, same order
    # Only when a pickup time was given and the shop can't take it.
    pickup_problem: str = ""
    next_pickups: list[str] = Field(default_factory=list)  # ISO, Singapore time


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT)


def _norm(text: str) -> str:
    return "".join((text or "").lower().split())


def _default_actor(channel: Channel) -> Actor:
    if channel == Channel.dashboard:
        return Actor.owner
    return Actor.customer if channel == Channel.web else Actor.external_agent


# --- Search -------------------------------------------------------------------------


def search_products(
    store: Store, shop_id: str, query: str = "", category: str | None = None,
    *, available_only: bool = True,
) -> list[Product]:
    """Products whose name, local name, category or description contain `query`.
    Unavailable products are skipped unless available_only is False."""
    words = (query or "").lower().split()
    found = []
    for p in store.list_products(shop_id):
        if available_only and not p.available:
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
            errors.append(f"Item {n}: needs name or product_id (text) and qty (whole number); "
                          "variant, options and request are optional.")
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
                          "Use get_menu (MCP) or catalog search (UCP) to find product ids.")
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
            line_total=_money(unit_price * item.qty), request=_clean_request(item.request),
        ))
        products.append(product)
    if errors:
        raise OrderValidationError(errors)
    total = _money(sum((line.line_total for line in lines), Decimal("0")))
    shop = store.get_shop(shop_id)
    return Quote(items=lines, total=total, currency=shop.currency if shop else "SGD",
                 price_mismatch=bool(mismatches), mismatches=mismatches), products


def _clean_request(text: Any) -> str:
    return " ".join(str(text or "").split())[:MAX_REQUEST_LEN]


def resolve_named_items(store: Store, shop_id: str,
                        items: list[Any]) -> tuple[list[Any], list[UnpricedRequest]]:
    """Turn {name, qty, ...} lines into product_id lines by exact menu name (English or local,
    ignoring case and spaces). -> (lines for build_quote, lines not on the menu).

    Lines that already have a product_id pass through unchanged, so an unknown id is still an
    error. A name that is not on the menu becomes an UnpricedRequest for the owner to price.
    Raises OrderValidationError.
    """
    if not isinstance(items, list) or not items:
        raise OrderValidationError(["Add at least one item to the order."])
    if len(items) > MAX_LINES:
        raise OrderValidationError([f"Too many lines: {len(items)}. The limit is {MAX_LINES}."])
    menu: list[Product] | None = None
    resolved: list[Any] = []
    unpriced: list[UnpricedRequest] = []
    errors: list[str] = []
    for n, raw in enumerate(items, start=1):
        name = " ".join(str(raw.get("name") or "").split()) if isinstance(raw, dict) else ""
        if not name or raw.get("product_id"):
            resolved.append(raw)
            continue
        if len(name) > MAX_ITEM_NAME_LEN:
            errors.append(f"Item {n}: name is too long (max {MAX_ITEM_NAME_LEN} characters).")
            continue
        menu = menu if menu is not None else store.list_products(shop_id)
        matches = [p for p in menu if _norm(name) in {_norm(p.name), _norm(p.name_local)}]
        if len(matches) > 1:
            errors.append(f"Item {n}: '{name}' matches {len(matches)} menu items. "
                          "Use product_id from get_menu.")
        elif matches:
            resolved.append({**raw, "product_id": matches[0].id})
        else:
            qty = raw.get("qty")
            if isinstance(qty, bool) or not isinstance(qty, int) or not MIN_QTY <= qty <= MAX_QTY:
                errors.append(f"Item {n}: qty must be a whole number between {MIN_QTY} and "
                              f"{MAX_QTY}.")
                continue
            unpriced.append(UnpricedRequest(name=name, qty=qty,
                                            request=_clean_request(raw.get("request"))))
    if errors:
        raise OrderValidationError(errors)
    return resolved, unpriced


def _quote_with_unpriced(store: Store, shop_id: str,
                         items: list[Any]) -> tuple[Quote, list[Product]]:
    """build_quote for menu lines, plus the lines that are not on the menu (no price)."""
    resolved, unpriced = resolve_named_items(store, shop_id, items)
    if resolved:
        quote, products = build_quote(store, shop_id, resolved)
    else:  # only off-menu lines: nothing to price yet
        shop = store.get_shop(shop_id)
        quote, products = Quote(items=[], total=_money(Decimal("0")),
                                currency=shop.currency if shop else "SGD"), []
    quote.unpriced = unpriced
    return quote, products


def review_checks(shop: Shop, quote: Quote, products: list[Product]) -> list[tuple[str, str]]:
    """Deterministic reasons the owner must approve the order, whatever the risk score, as
    (code, owner-facing text): items not on the menu, custom requests, unusual quantities and a
    total above the shop's auto-approve limit. Codes are HOLD_SENTENCES keys. (Pickups outside
    opening hours are refused before this, see pickup.py.)"""
    checks = [("not_on_menu", f"{u.qty} x '{u.name}' is not on the menu; the owner will price it")
              for u in quote.unpriced]
    checks += [("custom_request", f"Custom request for {line.name}; the owner must confirm it")
               for line in quote.items if line.request]
    for product, line in zip(products, quote.items, strict=True):
        biggest = risk.unusual_qty(product, line.qty)
        if biggest is not None:
            checks.append(("unusual_qty",
                           f"Quantity {line.qty} x {line.name} is above this shop's usual "
                           f"maximum (3x its largest pack of {biggest})"))
    if quote.total > shop.auto_approve_limit:
        checks.append(("over_limit", f"Total S${quote.total:.2f} is above the "
                                     f"S${shop.auto_approve_limit:.2f} auto-approve limit"))
    return checks


def owner_review_reasons(shop: Shop, quote: Quote, products: list[Product]) -> list[str]:
    """The owner-facing text of review_checks."""
    return [text for _, text in review_checks(shop, quote, products)]


def _review(shop: Shop, quote: Quote, products: list[Product]) -> None:
    checks = review_checks(shop, quote, products)
    quote.review_codes = [code for code, _ in checks]
    quote.review_reasons = [text for _, text in checks]


def hold_sentences(shop: Shop | None, codes: list[str]) -> list[str]:
    """Plain customer sentences for these review codes, once each, in order. No codes means
    the hold came from the risk score alone."""
    limit = shop.auto_approve_limit if shop else Decimal("150")
    out: list[str] = []
    for code in codes or ["risk"]:
        sentence = HOLD_SENTENCES.get(code, HOLD_SENTENCES["risk"]).format(limit=limit)
        if sentence not in out:
            out.append(sentence)
    return out


def hold_message(shop: Shop | None, codes: list[str]) -> str:
    """e.g. 'Orders over S$150.00 need the owner's OK. Your order has been sent to the owner
    for approval.'"""
    return " ".join([*hold_sentences(shop, codes), SENT_TO_OWNER])


def buyer_message(shop: Shop | None, order: Order) -> str:
    """The plain message a buyer agent sees for this order's current status."""
    if order.status == OrderStatus.pending_approval:
        return hold_message(shop, order.review_codes)
    if order.expired:
        return EXPIRED_MESSAGE
    return STATUS_MESSAGES[order.status]


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
                 "mismatches": quote.mismatches, "not_on_menu": len(quote.unpriced),
                 "review_reasons": quote.review_reasons},
    )


def get_quote(
    store: Store, shop_id: str, items: list[Any], *,
    channel: Channel = Channel.mcp, agent_name: str = "", actor: Actor | None = None,
    pickup_at: datetime | str | None = None,
    now: datetime | None = None,
) -> Quote:
    """Price the items from the menu and say whether the owner would have to approve them.
    Lines may name menu items instead of giving product ids; off-menu names are unpriced.
    With a pickup time, also says if the shop can't take it and which times it can."""
    shop = _require_shop(store, shop_id)
    pickup_time = _parse_pickup(pickup_at) if pickup_at else None
    quote, products = _quote_with_unpriced(store, shop_id, items)
    _review(shop, quote, products)
    if pickup_time is not None:
        problem = pickup.pickup_problem(store, shop, pickup_time, now)
        if problem:
            quote.pickup_problem = problem
            quote.next_pickups = [pickup.iso(s) for s in
                                  pickup.next_slots(store, shop, now, after=pickup_time)]
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
    customer_email: str = "",
    actor: Actor | None = None,
    settings: Settings | None = None,
    gemini_client=None,
    now: datetime | None = None,
) -> Order:
    """Quote -> risk check -> approval decision -> save. Every step is in the audit log.

    Returns as soon as the order is saved, with the rule reasons as the risk explanation. The
    Gemini sentence is fetched in the background and replaces it on the saved order (audit
    action risk_explained). Raises OrderValidationError for bad input. Never waits for or
    fails because of Gemini.
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
    email = ""
    if (customer_email or "").strip():
        email = owner_session.normalize_email(customer_email) or ""
        if not email:
            errors.append("customer_email doesn't look like an email address. Leave it empty "
                          "if you don't want email updates.")
    note = (note or "").strip()
    if len(note) > MAX_NOTE_LEN:
        errors.append(f"note is too long (max {MAX_NOTE_LEN} characters).")
    pickup_time = _parse_pickup(pickup_at)
    if errors:
        raise OrderValidationError(errors)
    problem = pickup.pickup_problem(store, shop, pickup_time, now)
    if problem:
        raise PickupUnavailable(problem, pickup.next_slots(store, shop, now, after=pickup_time))

    quote, products = _quote_with_unpriced(store, shop_id, items)
    _review(shop, quote, products)
    _log_quote(store, shop_id, quote, actor, agent_name, channel)

    phone = risk.normalize_sg_phone(customer_phone) or customer_phone.strip()
    previous = store.list_orders(shop_id)
    order = Order(
        shop_id=shop_id, items=quote.items, total=quote.total,
        customer_name=customer_name, customer_phone=phone, customer_email=email,
        pickup_at=pickup_time, note=note,
        channel=channel, agent_name=agent_name, status=OrderStatus.pending_approval,
        unpriced_requests=quote.unpriced, review_reasons=quote.review_reasons,
        review_codes=quote.review_codes, status_token=notify.new_status_token(),
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
        total=quote.total, phone=customer_phone, agent_name=agent_name, pickup_at=pickup_time,
        note=note, price_mismatch=quote.price_mismatch, previous_orders=previous, now=now,
        unpriced=len(quote.unpriced),
    )
    order.risk = risk.assess(facts)
    log_event(
        store, shop_id=shop_id, actor=Actor.risk_agent, action="risk_scored",
        entity_type="order", entity_id=order.id,
        summary=f"Risk {order.risk.level.value.upper()} {order.risk.score}/100",
        details={"score": order.risk.score, "level": order.risk.level.value,
                 "reasons": order.risk.reasons, "explanation": order.risk.explanation,
                 "explanation_source": "rules", "mismatches": quote.mismatches},
    )

    order.status, why = approval.decide(shop, order.risk, order.total, order.review_reasons)
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
    if order.risk.reasons and settings.gemini_model:
        _start_background(_explain_later(
            store, order.id, order.risk.model_copy(), note, settings, gemini_client))
    _start_background(_email_owner(store, order.id, settings))
    if not held:
        _start_background(notify.customer_update(store, settings, order.id, "confirmed"))
    return order


# --- Duplicate protection ---------------------------------------------------------------

IDEMPOTENCY = "idempotency_keys"
MAX_IDEMPOTENCY_KEY_LEN = 100
IN_FLIGHT = ("An order with this idempotency_key is still being placed. Check again in a few "
             "seconds; don't send it with a new key.")


async def place_order_once(store: Store, shop_id: str, key: str | None,
                           place: Callable[[], Awaitable[Order]]) -> tuple[Order, bool]:
    """Run `place` once per (shop, idempotency key). -> (order, duplicate). The same key again
    returns the first order instead of creating a new one. Without a key, always places."""
    key = (key or "").strip()[:MAX_IDEMPOTENCY_KEY_LEN]
    if not key:
        return await place(), False
    key_hash = hashlib.sha256(f"{shop_id}:{key}".encode()).hexdigest()
    existing = store.claim(IDEMPOTENCY, key_hash, {"shop_id": shop_id, "order_id": "",
                                                   "at": now_sg().isoformat()})
    if existing is not None:
        order = store.get_order(existing.get("order_id") or "")
        if order is None:
            raise OrderValidationError([IN_FLIGHT])
        return order, True
    try:
        order = await place()
    except BaseException:
        store.pop_secret(IDEMPOTENCY, key_hash)  # nothing was placed: the key can be retried
        raise
    store.put_secret(IDEMPOTENCY, key_hash, {"shop_id": shop_id, "order_id": order.id,
                                             "at": now_sg().isoformat()})
    return order, False


# --- Risk explanation in the background ------------------------------------------------

# Strong references, so running tasks aren't garbage-collected before they finish.
_background: set[asyncio.Task] = set()


def _start_background(coro) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # called from a sync route's worker thread: just run it here
        asyncio.run(coro)
        return
    task = loop.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


def expire_due(store: Store, settings: Settings, shop: Shop,
               now: datetime | None = None) -> list[Order]:
    """Reject this shop's held orders that waited longer than its approval timeout, and email
    their customers. Called before anyone reads orders (owner list, status page, agents) and
    by the periodic sweep, so expiry doesn't depend on a timer running on Cloud Run."""
    expired = approval.expire_overdue(store, shop, now)
    for order in expired:
        _start_background(notify.customer_update(store, settings, order.id, "expired"))
    return expired


def expire_due_for_order(store: Store, settings: Settings, order_id: str,
                         now: datetime | None = None) -> None:
    """expire_due for the shop of one order, before showing that order."""
    order = store.get_order(order_id)
    shop = store.get_shop(order.shop_id) if order else None
    if order is not None and shop is not None and order.status == OrderStatus.pending_approval:
        expire_due(store, settings, shop, now)


async def wait_for_background_tasks() -> None:
    """Wait for pending risk explanations and owner emails. For scripts and tests that close
    their event loop right after placing orders; the server's loop keeps running."""
    while _background:
        await asyncio.gather(*list(_background), return_exceptions=True)


async def _explain_later(store: Store, order_id: str, scored: Risk, note: str,
                         settings: Settings, client) -> None:
    """Ask Gemini for the owner-facing sentence and put it on the saved order. On any failure
    the order keeps the rule reasons it was saved with. Never raises."""
    try:
        text, source = await risk.explain(scored, note, settings, client)
        if source != "gemini":
            return
        # Re-read so an approve/reject that happened meanwhile is kept; only the
        # explanation changes. No await between get and save.
        order = store.get_order(order_id)
        if order is None:
            return
        order.risk.explanation = text
        store.save_order(order)
        log_event(
            store, shop_id=order.shop_id, actor=Actor.risk_agent, action="risk_explained",
            entity_type="order", entity_id=order.id,
            summary=f"Risk explanation for order {order.id}: {text}",
            details={"explanation": text, "explanation_source": source},
        )
    except Exception:  # a background task must never crash the server
        log.exception("background risk explanation failed for order %s", order_id)


async def _email_owner(store: Store, order_id: str, settings: Settings) -> None:
    """Email the shop owner about a new order, with a "Review order" button that signs them in.
    The order is already saved: a failed email is logged and audited, never raised."""
    try:
        order = store.get_order(order_id)
        shop = store.get_shop(order.shop_id) if order else None
        if order is None or shop is None or not shop.owner_email:
            return
        token = owner_session.issue_link(store, shop.id, "login", owner_session.ORDER_LINK_TTL,
                                         next_path=f"/shop/{shop.id}/orders")
        email = emails.order_email(shop, order, owner_session.link_url(settings, "signin", token))
        sent = await mailer.send_safely(settings, email)
        log_event(
            store, shop_id=shop.id, actor=Actor.system,
            action="owner_emailed" if sent else "owner_email_failed",
            entity_type="order", entity_id=order.id,
            summary=(f"Emailed the owner about order {order.id}" if sent else
                     f"Couldn't email the owner about order {order.id} (the order is saved)"),
            details={"to": mailer.mask_email(shop.owner_email), "subject": email.subject,
                     "customer_phone": mask_phone(order.customer_phone)},
        )
    except Exception:  # a background task must never crash the server
        log.exception("owner email failed for order %s", order_id)


def get_order_status(store: Store, shop_id: str, order_id: str,
                     settings: Settings | None = None) -> dict[str, Any]:
    """What a buyer agent may see. No risk details, so the scoring can't be gamed."""
    approval.get_shop_order(store, shop_id, order_id)
    expire_due_for_order(store, settings or get_settings(), order_id)
    order = approval.get_shop_order(store, shop_id, order_id)
    shop = store.get_shop(shop_id)
    return {
        "order_id": order.id,
        "status": order.status.value,
        "message": buyer_message(shop, order),
        "rejection_reason": order.rejection_reason,
        "items": [line.model_dump(mode="json") for line in order.items],
        "unpriced_items": [u.model_dump(mode="json") for u in order.unpriced_requests],
        "total": str(order.total),
        "currency": shop.currency if shop else "SGD",
        "pickup_at": to_sg(order.pickup_at).isoformat(),
        "customer_name": order.customer_name,
    }
