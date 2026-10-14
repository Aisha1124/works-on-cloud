"""Prod store backed by Firestore. Stub for now; implemented in a later task."""

from backend.models import AuditEvent, Order, OrderStatus, Product, Shop
from backend.store.base import Store

_MSG = "FirestoreStore is not implemented yet. Use STORE_BACKEND=local for now."


class FirestoreStore(Store):
    def __init__(self, project_id: str, database: str = "(default)"):
        self.project_id = project_id
        self.database = database

    def get_shop(self, shop_id: str) -> Shop | None:
        raise NotImplementedError(_MSG)

    def get_shop_by_slug(self, slug: str) -> Shop | None:
        raise NotImplementedError(_MSG)

    def list_shops(self) -> list[Shop]:
        raise NotImplementedError(_MSG)

    def save_shop(self, shop: Shop) -> Shop:
        raise NotImplementedError(_MSG)

    def get_product(self, product_id: str) -> Product | None:
        raise NotImplementedError(_MSG)

    def list_products(self, shop_id: str) -> list[Product]:
        raise NotImplementedError(_MSG)

    def save_product(self, product: Product) -> Product:
        raise NotImplementedError(_MSG)

    def delete_product(self, product_id: str) -> bool:
        raise NotImplementedError(_MSG)

    def get_order(self, order_id: str) -> Order | None:
        raise NotImplementedError(_MSG)

    def list_orders(self, shop_id: str, status: OrderStatus | None = None) -> list[Order]:
        raise NotImplementedError(_MSG)

    def save_order(self, order: Order) -> Order:
        raise NotImplementedError(_MSG)

    def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        raise NotImplementedError(_MSG)

    def list_audit_events(self, shop_id: str, limit: int = 100) -> list[AuditEvent]:
        raise NotImplementedError(_MSG)
