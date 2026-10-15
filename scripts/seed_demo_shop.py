"""Create (or refresh) the published demo shop that external agents order from.

Fixed ids, so scripts/try_mcp.py and the UCP request files in scripts/ucp/ can refer to them:
  shop slug  mak-kuih-demo
  products   demo-lapis (variants: 20 pcs = item demo-lapis.v0, 40 pcs = demo-lapis.v1)
             demo-ondeh (one pack, option Flavour: Pandan / Gula Melaka)
No orders are placed and Gemini is not called.

Usage:  uv run python scripts/seed_demo_shop.py
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.api.config import get_settings  # noqa: E402
from backend.models import Product, ProductOption, Shop, Variant  # noqa: E402
from backend.store import get_store  # noqa: E402

SHOP_ID = "demo-shop"
SLUG = "mak-kuih-demo"


def main() -> None:
    store = get_store(get_settings())
    shop = store.save_shop(Shop(
        id=SHOP_ID, slug=SLUG, name="Mak's Kuih (demo)", tagline="Nyonya kuih, made fresh",
        shop_type="Home baker", address="Blk 201 Tampines St 21, Tampines",
        hours="Tue-Sun 9am-6pm", phone="+65 6123 4567", published=True))
    store.save_product(Product(
        id="demo-lapis", shop_id=shop.id, name="Kuih Lapis", name_local="九层糕",
        category="Kuih", description="Steamed layered kuih.",
        variants=[Variant(label="20 pcs", price=Decimal("16")),
                  Variant(label="40 pcs", price=Decimal("30"))]))
    store.save_product(Product(
        id="demo-ondeh", shop_id=shop.id, name="Ondeh Ondeh", category="Kuih",
        base_price=Decimal("12.50"), unit="10 pcs",
        options=[ProductOption(name="Flavour", choices=["Pandan", "Gula Melaka"])]))
    print(f"Published shop '{shop.name}' (slug {SLUG}, id {SHOP_ID}) with 2 products.")


if __name__ == "__main__":
    main()
