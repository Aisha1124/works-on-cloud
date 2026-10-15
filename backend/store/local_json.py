"""Dev store: one JSON file per collection under data/."""

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from backend.models import AuditEvent, Order, OrderStatus, Product, Shop
from backend.store.base import Store

M = TypeVar("M", bound=BaseModel)


class LocalJsonStore(Store):
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # --- file helpers ---------------------------------------------------

    def _path(self, collection: str) -> Path:
        return self.data_dir / f"{collection}.json"

    def _read(self, collection: str) -> dict[str, dict]:
        path = self._path(collection)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, collection: str, rows: dict[str, dict]) -> None:
        # Write to a temp file, then swap it in, so a crash never leaves half a file.
        fd, tmp = tempfile.mkstemp(dir=self.data_dir, prefix=f".{collection}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path(collection))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _get(self, collection: str, model: type[M], key: str) -> M | None:
        with self._lock:
            row = self._read(collection).get(key)
        return model.model_validate(row) if row is not None else None

    def _all(self, collection: str, model: type[M]) -> list[M]:
        """All rows, in insertion order."""
        with self._lock:
            rows = self._read(collection)
        return [model.model_validate(r) for r in rows.values()]

    @staticmethod
    def _newest_first(items: list[M], key) -> list[M]:
        # Reverse first so rows with equal timestamps keep newest-inserted first
        # (sort is stable). Windows clock ticks can give two events the same time.
        return sorted(reversed(items), key=key, reverse=True)

    def _put(self, collection: str, key: str, item: M) -> M:
        with self._lock:
            rows = self._read(collection)
            rows[key] = item.model_dump(mode="json")
            self._write(collection, rows)
        return item

    # --- shops ----------------------------------------------------------

    def get_shop(self, shop_id: str) -> Shop | None:
        return self._get("shops", Shop, shop_id)

    def get_shop_by_slug(self, slug: str) -> Shop | None:
        return next((s for s in self.list_shops() if s.slug == slug), None)

    def list_shops(self) -> list[Shop]:
        return self._all("shops", Shop)

    def save_shop(self, shop: Shop) -> Shop:
        return self._put("shops", shop.id, shop)

    # --- products -------------------------------------------------------

    def get_product(self, product_id: str) -> Product | None:
        return self._get("products", Product, product_id)

    def list_products(self, shop_id: str) -> list[Product]:
        return [p for p in self._all("products", Product) if p.shop_id == shop_id]

    def save_product(self, product: Product) -> Product:
        return self._put("products", product.id, product)

    def delete_product(self, product_id: str) -> bool:
        with self._lock:
            rows = self._read("products")
            if rows.pop(product_id, None) is None:
                return False
            self._write("products", rows)
        return True

    # --- orders ---------------------------------------------------------

    def get_order(self, order_id: str) -> Order | None:
        return self._get("orders", Order, order_id)

    def list_orders(self, shop_id: str, status: OrderStatus | None = None) -> list[Order]:
        orders = [o for o in self._all("orders", Order) if o.shop_id == shop_id]
        if status is not None:
            orders = [o for o in orders if o.status == status]
        return self._newest_first(orders, key=lambda o: o.created_at)

    def save_order(self, order: Order) -> Order:
        return self._put("orders", order.id, order)

    # --- audit ----------------------------------------------------------

    def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        return self._put("audit_events", event.id, event)

    def list_audit_events(
        self, shop_id: str, limit: int = 100, offset: int = 0
    ) -> list[AuditEvent]:
        events = [e for e in self._all("audit_events", AuditEvent) if e.shop_id == shop_id]
        return self._newest_first(events, key=lambda e: e.at)[offset : offset + limit]
