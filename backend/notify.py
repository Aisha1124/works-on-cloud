"""Order emails after the order is placed: status updates to the customer (if they left an
email) and "cancelled" to the owner. Like the new-order email, a failed send is logged and
audited, never raised: the order change is already saved.
"""

import logging
import secrets

from backend import emails, mailer, owner_session
from backend.api.config import Settings
from backend.audit import log_event
from backend.models import Actor, Order
from backend.store.base import Store

log = logging.getLogger(__name__)


def new_status_token() -> str:
    return secrets.token_urlsafe(16)


def status_url(settings: Settings, order: Order) -> str:
    """The customer's private link to their order: /o/{id}?t={token}."""
    return f"{settings.base_url.rstrip('/')}/o/{order.id}?t={order.status_token}"


async def customer_update(store: Store, settings: Settings, order_id: str, kind: str) -> None:
    """kind: confirmed | rejected | expired | cancelled (emails.CUSTOMER_KINDS). Only when the
    customer gave an email. Never raises."""
    try:
        order = store.get_order(order_id)
        shop = store.get_shop(order.shop_id) if order else None
        if order is None or shop is None or not order.customer_email:
            return
        email = emails.customer_email(shop, order, kind, status_url(settings, order))
        sent = await mailer.send_safely(settings, email)
        log_event(
            store, shop_id=shop.id, actor=Actor.system,
            action="customer_emailed" if sent else "customer_email_failed",
            entity_type="order", entity_id=order.id,
            summary=(f"Emailed the customer: order {order.id} {kind}" if sent else
                     f"Couldn't email the customer about order {order.id} ({kind})"),
            details={"to": mailer.mask_email(order.customer_email), "kind": kind},
        )
    except Exception:  # a background task must never crash the server
        log.exception("customer email failed for order %s", order_id)


async def owner_cancelled(store: Store, settings: Settings, order_id: str) -> None:
    """Tell the owner a customer cancelled. Never raises."""
    try:
        order = store.get_order(order_id)
        shop = store.get_shop(order.shop_id) if order else None
        if order is None or shop is None or not shop.owner_email:
            return
        token = owner_session.issue_link(store, shop.id, "login", owner_session.ORDER_LINK_TTL,
                                         next_path=f"/shop/{shop.id}/orders")
        email = emails.owner_cancelled_email(
            shop, order, owner_session.link_url(settings, "signin", token))
        sent = await mailer.send_safely(settings, email)
        log_event(
            store, shop_id=shop.id, actor=Actor.system,
            action="owner_emailed" if sent else "owner_email_failed",
            entity_type="order", entity_id=order.id,
            summary=(f"Emailed the owner: order {order.id} was cancelled" if sent else
                     f"Couldn't email the owner about cancelled order {order.id}"),
            details={"to": mailer.mask_email(shop.owner_email), "subject": email.subject},
        )
    except Exception:  # a background task must never crash the server
        log.exception("owner cancel email failed for order %s", order_id)
