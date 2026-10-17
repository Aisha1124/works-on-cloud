"""Keeping customer data only as long as needed (what the /privacy page promises).

90 days after pickup, an order's customer name, phone, email and note are erased. The items,
totals and times stay, so the shop's records still add up. UCP checkout sessions lose their
buyer details 90 days after they were last changed. Runs in the periodic sweep.
"""

from datetime import datetime, timedelta

from backend.audit import log_event
from backend.models import Actor, CheckoutBuyer, Shop, utc_now
from backend.store.base import Store

RETENTION_DAYS = 90
ERASED_NAME = "(erased)"


def erase_old_personal_data(store: Store, shop: Shop, now: datetime | None = None) -> int:
    """-> how many orders were erased now. Safe to run often."""
    now = now or utc_now()
    cutoff = timedelta(days=RETENTION_DAYS)
    erased = 0
    for order in store.list_orders(shop.id):
        if order.personal_data_erased or order.pickup_at + cutoff > now:
            continue
        store.save_order(order.model_copy(update={
            "customer_name": ERASED_NAME, "customer_phone": "", "customer_email": "",
            "note": "", "personal_data_erased": True}))
        erased += 1
    for checkout in store.list_checkouts(shop.id):
        if checkout.updated_at + cutoff <= now and checkout.buyer != CheckoutBuyer():
            store.save_checkout(checkout.model_copy(update={"buyer": CheckoutBuyer(), "note": ""}))
    if erased:
        log_event(
            store, shop_id=shop.id, actor=Actor.system, action="personal_data_erased",
            entity_type="shop", entity_id=shop.id,
            summary=(f"Erased customer name, phone, email and note from {erased} order(s) "
                     f"picked up more than {RETENTION_DAYS} days ago"),
            details={"orders": erased, "retention_days": RETENTION_DAYS},
        )
    return erased
