"""Storage interface. LocalJsonStore for dev, FirestoreStore for prod."""

from abc import ABC, abstractmethod

from backend.models import AuditEvent, CheckoutSession, Order, OrderStatus, Product, Shop


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

    # Owner keys: only the hash, kept apart from the Shop so it is never sent to anyone.
    @abstractmethod
    def get_owner_key_hash(self, shop_id: str) -> str | None: ...

    @abstractmethod
    def set_owner_key_hash(self, shop_id: str, key_hash: str) -> None:
        """Replace the shop's key hash (one key per shop)."""

    @abstractmethod
    def find_shop_by_owner_key_hash(self, key_hash: str) -> str | None:
        """The shop id whose key has this hash, or None."""

    @abstractmethod
    def find_shops_by_owner_email(self, email: str) -> list[Shop]:
        """Shops whose owner_email is `email` (already lower-case)."""

    # Short-lived secrets (sign-in links, sessions), keyed by a hash of the secret.
    @abstractmethod
    def put_secret(self, collection: str, key_hash: str, data: dict) -> None: ...

    @abstractmethod
    def get_secret(self, collection: str, key_hash: str) -> dict | None: ...

    @abstractmethod
    def pop_secret(self, collection: str, key_hash: str) -> dict | None:
        """Remove and return it, atomically: a single-use secret can only be used once."""

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

    # UCP checkout sessions
    @abstractmethod
    def get_checkout(self, checkout_id: str) -> CheckoutSession | None: ...

    @abstractmethod
    def save_checkout(self, checkout: CheckoutSession) -> CheckoutSession: ...

    # Audit
    @abstractmethod
    def add_audit_event(self, event: AuditEvent) -> AuditEvent: ...

    @abstractmethod
    def list_audit_events(
        self, shop_id: str, limit: int = 100, offset: int = 0
    ) -> list[AuditEvent]:
        """Newest first. Skips `offset` events, then returns up to `limit`."""
