"""Approval: decide whether an order goes through by itself, and the owner's approve/reject.

Buyer-side agents see the result through commerce.get_order_status.
"""

from decimal import Decimal

from backend.audit import log_event
from backend.models import Actor, Order, OrderStatus, Risk, RiskLevel, Shop
from backend.store.base import Store

MAX_REASON_LEN = 300


class OrderNotFound(LookupError):
    def __init__(self, order_id: str):
        super().__init__(f"Order {order_id} was not found in this shop.")


class InvalidTransition(ValueError):
    """The order is not waiting for approval. str(exc) is safe to show."""


def decide(shop: Shop, risk: Risk, total: Decimal) -> tuple[OrderStatus, str]:
    """-> (status, why). Only low-risk orders within the shop's limit go through by themselves."""
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


def _require_pending(order: Order, verb: str) -> None:
    if order.status != OrderStatus.pending_approval:
        raise InvalidTransition(
            f"Order {order.id} is {order.status.value.replace('_', ' ')}. "
            f"Only orders waiting for approval can be {verb}."
        )


def approve(store: Store, shop_id: str, order_id: str) -> Order:
    order = get_shop_order(store, shop_id, order_id)
    _require_pending(order, "approved")
    order.status = OrderStatus.approved
    store.save_order(order)
    log_event(
        store, shop_id=shop_id, actor=Actor.owner, action="order_approved",
        entity_type="order", entity_id=order.id,
        summary=f"Owner approved order {order.id} (S${order.total:.2f})",
    )
    return order


def reject(store: Store, shop_id: str, order_id: str, reason: str = "") -> Order:
    order = get_shop_order(store, shop_id, order_id)
    _require_pending(order, "rejected")
    reason = " ".join((reason or "").split())[:MAX_REASON_LEN]
    order.status = OrderStatus.rejected
    order.rejection_reason = reason
    store.save_order(order)
    log_event(
        store, shop_id=shop_id, actor=Actor.owner, action="order_rejected",
        entity_type="order", entity_id=order.id,
        summary=f"Owner rejected order {order.id}" + (f": {reason}" if reason else ""),
        details={"reason": reason},
    )
    return order
