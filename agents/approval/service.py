"""Approval: decide whether an order goes through by itself, and the owner's approve/reject.

Buyer-side agents see the result through commerce.get_order_status.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from backend.audit import log_event
from backend.models import Actor, Order, OrderStatus, Risk, RiskLevel, Shop, utc_now
from backend.store.base import Store

MAX_REASON_LEN = 300


class OrderNotFound(LookupError):
    def __init__(self, order_id: str):
        super().__init__(f"Order {order_id} was not found in this shop.")


class InvalidTransition(ValueError):
    """The order is not waiting for approval. str(exc) is safe to show."""


def decide(shop: Shop, risk: Risk, total: Decimal,
           review_reasons: Sequence[str] = ()) -> tuple[OrderStatus, str]:
    """-> (status, why). Only low-risk orders within the shop's limit, with nothing the owner
    must review (commerce.owner_review_reasons), go through by themselves."""
    if review_reasons:
        return OrderStatus.pending_approval, "needs owner review: " + "; ".join(review_reasons)
    if total > shop.auto_approve_limit:
        return (OrderStatus.pending_approval,
                f"total S${total:.2f} is above the S${shop.auto_approve_limit:.2f} "
                "auto-approve limit")
    if risk.level != RiskLevel.low:
        return OrderStatus.pending_approval, f"risk is {risk.level.value.upper()}"
    return OrderStatus.auto_approved, "low risk and within the auto-approve limit"


def get_shop_order(store: Store, shop_id: str, order_id: str) -> Order:
    order = store.get_order(order_id)
    if order is None or order.shop_id != shop_id:
        raise OrderNotFound(order_id)
    return order


def _not_pending(order: Order, verb: str) -> InvalidTransition:
    return InvalidTransition(
        f"Order {order.id} is {order.status.value.replace('_', ' ')}. "
        f"Only orders waiting for approval can be {verb}."
    )


def _decide(store: Store, shop_id: str, order_id: str, verb: str,
            update: dict) -> Order:
    """Pending -> decided, atomically (an expiry or a second tap can't also win)."""
    order = get_shop_order(store, shop_id, order_id)
    if order.status != OrderStatus.pending_approval:
        raise _not_pending(order, verb)
    decided = store.transition_order(order_id, {OrderStatus.pending_approval}, update)
    if decided is None:
        raise _not_pending(store.get_order(order_id) or order, verb)
    return decided


def approve(store: Store, shop_id: str, order_id: str) -> Order:
    order = _decide(store, shop_id, order_id, "approved", {"status": OrderStatus.approved})
    log_event(
        store, shop_id=shop_id, actor=Actor.owner, action="order_approved",
        entity_type="order", entity_id=order.id,
        summary=f"Owner approved order {order.id} (S${order.total:.2f})",
    )
    return order


def reject(store: Store, shop_id: str, order_id: str, reason: str = "") -> Order:
    reason = " ".join((reason or "").split())[:MAX_REASON_LEN]
    order = _decide(store, shop_id, order_id, "rejected",
                    {"status": OrderStatus.rejected, "rejection_reason": reason})
    log_event(
        store, shop_id=shop_id, actor=Actor.owner, action="order_rejected",
        entity_type="order", entity_id=order.id,
        summary=f"Owner rejected order {order.id}" + (f": {reason}" if reason else ""),
        details={"reason": reason},
    )
    return order


# --- Held orders that wait too long ------------------------------------------------------

EXPIRED_REASON = "The shop didn't respond in time"


def expiry_time(shop: Shop, order: Order) -> datetime:
    return order.created_at + timedelta(hours=shop.approval_timeout_hours)


def expire_overdue(store: Store, shop: Shop, now: datetime | None = None) -> list[Order]:
    """Reject this shop's held orders the owner didn't decide within approval_timeout_hours.
    -> the orders that expired now (the caller tells their customers). Safe to run often and
    from several instances: each order expires at most once."""
    now = now or utc_now()
    expired = []
    for order in store.list_orders(shop.id, OrderStatus.pending_approval):
        if expiry_time(shop, order) > now:
            continue
        done = store.transition_order(
            order.id, {OrderStatus.pending_approval},
            {"status": OrderStatus.rejected, "rejection_reason": EXPIRED_REASON, "expired": True})
        if done is None:
            continue  # the owner decided meanwhile
        log_event(
            store, shop_id=shop.id, actor=Actor.system, action="order_expired",
            entity_type="order", entity_id=order.id,
            summary=(f"Order {order.id} was rejected automatically: the owner didn't decide "
                     f"within {shop.approval_timeout_hours} hours"),
            details={"approval_timeout_hours": shop.approval_timeout_hours},
        )
        expired.append(done)
    return expired


# --- Customer cancels ------------------------------------------------------------------

CANCELLABLE = {OrderStatus.pending_approval, OrderStatus.auto_approved, OrderStatus.approved}


def cancel_deadline(shop: Shop, order: Order) -> datetime:
    return order.pickup_at - timedelta(hours=shop.cancel_cutoff_hours)


def can_cancel(shop: Shop, order: Order, now: datetime | None = None) -> bool:
    return order.status in CANCELLABLE and (now or utc_now()) < cancel_deadline(shop, order)


def cancel(store: Store, shop: Shop, order_id: str, now: datetime | None = None) -> Order:
    """The customer cancels from their status page. Raises InvalidTransition (a sentence)."""
    order = get_shop_order(store, shop.id, order_id)
    if order.status == OrderStatus.cancelled:
        raise InvalidTransition("This order is already cancelled.")
    if order.status not in CANCELLABLE:
        raise InvalidTransition("This order can't be cancelled any more.")
    if not can_cancel(shop, order, now):
        raise InvalidTransition(
            f"Orders can only be cancelled up to {shop.cancel_cutoff_hours} hours before "
            "pickup. Please call the shop.")
    done = store.transition_order(order_id, CANCELLABLE, {"status": OrderStatus.cancelled})
    if done is None:
        raise InvalidTransition("This order can't be cancelled any more.")
    log_event(
        store, shop_id=shop.id, actor=Actor.customer, action="order_cancelled",
        entity_type="order", entity_id=order.id,
        summary=f"Customer cancelled order {order.id} (S${order.total:.2f})",
        details={"previous_status": order.status.value},
    )
    return done
