"""Prod store backed by Firestore (Native mode), with the same behaviour as LocalJsonStore.

One collection per LocalJsonStore file, one document per row, holding exactly what the JSON
file holds (model_dump(mode="json")): money and times are strings, so both stores read back the
same models. Only equality queries are used and sorting happens here, so no composite indexes
are needed. Atomic operations (single-use secrets, order status changes, rate limits) run in
Firestore transactions; idempotency claims use create(), which fails if the document exists.

Credentials: Application Default Credentials (the Cloud Run service account; no key files).
Tests and local runs can point at the emulator with FIRESTORE_EMULATOR_HOST.
"""

import time
from datetime import UTC, datetime
from typing import Any, TypeVar

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import BaseModel

from backend.models import AuditEvent, CheckoutSession, Order, OrderStatus, Product, Shop
from backend.store.base import Store

M = TypeVar("M", bound=BaseModel)
SEQ = "_seq"  # insertion order, kept across updates (LocalJsonStore keeps file order)


class FirestoreStore(Store):
    def __init__(self, project_id: str, database: str = "(default)", client=None):
        self.project_id = project_id
        self.database = database or "(default)"
        self._client = client

    @property
    def db(self) -> firestore.Client:
        # Created on first use, so building the app never needs credentials by itself.
        if self._client is None:
            self._client = firestore.Client(project=self.project_id or None,
                                            database=self.database)
        return self._client

    # --- helpers --------------------------------------------------------------------

    def _col(self, name: str):
        return self.db.collection(name)

    @staticmethod
    def _model(model: type[M], snap) -> M | None:
        return model.model_validate(snap.to_dict()) if snap.exists else None

    def _get(self, collection: str, model: type[M], key: str) -> M | None:
        if not key:
            return None
        return self._model(model, self._col(collection).document(key).get())

    def _where(self, collection: str, field: str, value: Any) -> list[dict]:
        query = self._col(collection).where(filter=FieldFilter(field, "==", value))
        return [snap.to_dict() for snap in query.stream()]

    def _put(self, collection: str, key: str, item: M, keep_order: bool = False) -> M:
        data = item.model_dump(mode="json")
        ref = self._col(collection).document(key)
        if keep_order:
            old = ref.get(field_paths=[SEQ])
            data[SEQ] = (old.to_dict() or {}).get(SEQ) if old.exists else None
            data[SEQ] = data[SEQ] or time.time_ns()
        ref.set(data)
        return item

    # --- shops ----------------------------------------------------------------------

    def get_shop(self, shop_id: str) -> Shop | None:
        return self._get("shops", Shop, shop_id)

    def get_shop_by_slug(self, slug: str) -> Shop | None:
        rows = self._where("shops", "slug", slug)
        return Shop.model_validate(rows[0]) if rows else None

    def list_shops(self) -> list[Shop]:
        rows = sorted((s.to_dict() for s in self._col("shops").stream()),
                      key=lambda r: r.get(SEQ) or 0)
        return [Shop.model_validate(r) for r in rows]

    def save_shop(self, shop: Shop) -> Shop:
        return self._put("shops", shop.id, shop, keep_order=True)

    # --- owner keys (hash only) -----------------------------------------------------

    def get_owner_key_hash(self, shop_id: str) -> str | None:
        snap = self._col("owner_keys").document(shop_id).get()
        return (snap.to_dict() or {}).get("key_hash") if snap.exists else None

    def set_owner_key_hash(self, shop_id: str, key_hash: str) -> None:
        self._col("owner_keys").document(shop_id).set({"shop_id": shop_id, "key_hash": key_hash})

    def find_shop_by_owner_key_hash(self, key_hash: str) -> str | None:
        rows = self._where("owner_keys", "key_hash", key_hash)
        return rows[0]["shop_id"] if rows else None

    def find_shops_by_owner_email(self, email: str) -> list[Shop]:
        if not email:
            return []
        rows = sorted(self._where("shops", "owner_email", email), key=lambda r: r.get(SEQ) or 0)
        return [Shop.model_validate(r) for r in rows]

    # --- short-lived secrets (hash only) --------------------------------------------

    def put_secret(self, collection: str, key_hash: str, data: dict) -> None:
        self._col(collection).document(key_hash).set(data)

    def get_secret(self, collection: str, key_hash: str) -> dict | None:
        snap = self._col(collection).document(key_hash).get()
        return snap.to_dict() if snap.exists else None

    def pop_secret(self, collection: str, key_hash: str) -> dict | None:
        ref = self._col(collection).document(key_hash)

        @firestore.transactional
        def pop(txn) -> dict | None:
            snap = ref.get(transaction=txn)
            if not snap.exists:
                return None
            txn.delete(ref)
            return snap.to_dict()

        return pop(self.db.transaction())

    def take_rate(self, key_hash: str, limit: int, window_s: float, now: float,
                  consume: bool = True) -> bool:
        ref = self._col("rate_limits").document(key_hash)

        @firestore.transactional
        def take(txn) -> bool:
            snap = ref.get(transaction=txn)
            row = snap.to_dict() if snap.exists else None
            if row is None or now - row["start"] >= window_s:
                row = {"start": now, "count": 0, "expires_at": now + window_s}
            if row["count"] >= limit:
                return False
            if consume:
                row["count"] += 1
                # A real timestamp, so a Firestore TTL policy on "expire_at" can delete old rows.
                row["expire_at"] = datetime.fromtimestamp(row["expires_at"], UTC)
                txn.set(ref, row)
            return True

        return take(self.db.transaction())

    def claim(self, collection: str, key_hash: str, data: dict) -> dict | None:
        ref = self._col(collection).document(key_hash)
        try:
            ref.create(data)
            return None
        except AlreadyExists:
            snap = ref.get()
            return snap.to_dict() if snap.exists else {}

    # --- products -------------------------------------------------------------------

    def get_product(self, product_id: str) -> Product | None:
        return self._get("products", Product, product_id)

    def list_products(self, shop_id: str) -> list[Product]:
        rows = sorted(self._where("products", "shop_id", shop_id), key=lambda r: r.get(SEQ) or 0)
        return [Product.model_validate(r) for r in rows]

    def save_product(self, product: Product) -> Product:
        return self._put("products", product.id, product, keep_order=True)

    def delete_product(self, product_id: str) -> bool:
        ref = self._col("products").document(product_id)

        @firestore.transactional
        def delete(txn) -> bool:
            if not ref.get(transaction=txn).exists:
                return False
            txn.delete(ref)
            return True

        return delete(self.db.transaction())

    # --- orders ---------------------------------------------------------------------

    def get_order(self, order_id: str) -> Order | None:
        return self._get("orders", Order, order_id)

    def list_orders(self, shop_id: str, status: OrderStatus | None = None) -> list[Order]:
        rows = sorted(self._where("orders", "shop_id", shop_id), key=lambda r: r.get(SEQ) or 0)
        orders = [Order.model_validate(r) for r in rows]
        if status is not None:
            orders = [o for o in orders if o.status == status]
        # Newest first; equal times keep newest-inserted first (as LocalJsonStore).
        return sorted(reversed(orders), key=lambda o: o.created_at, reverse=True)

    def save_order(self, order: Order) -> Order:
        return self._put("orders", order.id, order, keep_order=True)

    def transition_order(self, order_id: str, from_statuses: set[OrderStatus],
                         update: dict[str, Any]) -> Order | None:
        ref = self._col("orders").document(order_id)

        @firestore.transactional
        def change(txn) -> Order | None:
            snap = ref.get(transaction=txn)
            if not snap.exists:
                return None
            data = snap.to_dict()
            order = Order.model_validate(data)
            if order.status not in from_statuses:
                return None
            order = Order.model_validate({**order.model_dump(), **update})
            txn.set(ref, {**order.model_dump(mode="json"), SEQ: data.get(SEQ)})
            return order

        return change(self.db.transaction())

    # --- UCP checkout sessions ------------------------------------------------------

    def get_checkout(self, checkout_id: str) -> CheckoutSession | None:
        return self._get("checkouts", CheckoutSession, checkout_id)

    def save_checkout(self, checkout: CheckoutSession) -> CheckoutSession:
        return self._put("checkouts", checkout.id, checkout)

    def list_checkouts(self, shop_id: str) -> list[CheckoutSession]:
        return [CheckoutSession.model_validate(r)
                for r in self._where("checkouts", "shop_id", shop_id)]

    # --- audit ----------------------------------------------------------------------

    def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        data = {**event.model_dump(mode="json"), SEQ: time.time_ns()}
        self._col("audit_events").document(event.id).set(data)
        return event

    def list_audit_events(
        self, shop_id: str, limit: int = 100, offset: int = 0
    ) -> list[AuditEvent]:
        # Newest first; equal times keep newest-inserted first (as LocalJsonStore).
        events = [(AuditEvent.model_validate(r), r.get(SEQ) or 0)
                  for r in self._where("audit_events", "shop_id", shop_id)]
        events.sort(key=lambda pair: (pair[0].at, pair[1]), reverse=True)
        return [e for e, _ in events[offset: offset + limit]]
