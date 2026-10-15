"""Storage interface. LocalJsonStore for dev, FirestoreStore for prod."""

from abc import ABC, abstractmethod

from backend.models import AuditEvent, Order, OrderStatus, Product, Shop


class Store(ABC):
    # Shops
    @abstractmethod
    def get_shop(self, shop_id: str) -> Shop | None: ...

    @abstractmethod
    def get_shop_by_slug(self, slug: str) -> Shop | None: ...

    @abstractmethod
    def list_shops(self) -> list[Shop]: ...

    @abstractmethod
    def save_shop(self, shop: Shop) -> Shop: ...

    # Products
    @abstractmethod
    def get_product(self, product_id: str) -> Product | None: ...

    @abstractmethod
    def list_products(self, shop_id: str) -> list[Product]: ...

    @abstractmethod
    def save_product(self, product: Product) -> Product: ...

    @abstractmethod
    def delete_product(self, product_id: str) -> bool: ...

    # Orders
    @abstractmethod
    def get_order(self, order_id: str) -> Order | None: ...

    @abstractmethod
    def list_orders(self, shop_id: str, status: OrderStatus | None = None) -> list[Order]:
        """Newest first."""

    @abstractmethod
    def save_order(self, order: Order) -> Order: ...

    # Audit
    @abstractmethod
    def add_audit_event(self, event: AuditEvent) -> AuditEvent: ...

    @abstractmethod
    def list_audit_events(
        self, shop_id: str, limit: int = 100, offset: int = 0
    ) -> list[AuditEvent]:
        """Newest first. Skips `offset` events, then returns up to `limit`."""
