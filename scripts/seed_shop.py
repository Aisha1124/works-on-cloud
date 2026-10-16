"""Create the published sample shop that external agents order from, only if it doesn't exist.
The container runs this at every startup (see Dockerfile); an existing shop, its menu and its
orders are never overwritten, so a redeploy never wipes data. Only its owner key follows
OWNER_KEY.

Fixed ids, so scripts/try_mcp.py and the UCP request files in scripts/ucp/ can refer to them:
  shop slug  mak-kuih
  products   kuih-lapis (variants: 20 pcs = item kuih-lapis.v0, 40 pcs = kuih-lapis.v1)
             ondeh-ondeh (one pack, option Flavour: Pandan / Gula Melaka)
No orders are placed and Gemini is not called.

It is clearly an example: example=True (the shop page and llms.txt say "Example shop"), the
phone is the placeholder +65 0000 0000 and the address is only "Tampines, Singapore".

The shop's owner email is SAMPLE_OWNER_EMAIL (optional: it gets the order emails and can
sign in by email link). Its owner key is OWNER_KEY (only its hash is stored). It opens this shop only. If
OWNER_KEY is empty the shop gets no key, so nobody can manage it.

Usage:  uv run python scripts/seed_shop.py
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.api.config import get_settings  # noqa: E402
from backend.models import Product, ProductOption, Shop, Variant  # noqa: E402
from backend.owner_auth import hash_owner_key  # noqa: E402
from backend.store import get_store  # noqa: E402

SHOP_ID = "mak-kuih"
SLUG = "mak-kuih"


def main() -> None:
    settings = get_settings()
    store = get_store(settings)
    key = settings.owner_key.get_secret_value().strip() if settings.owner_key else ""
    existing = store.get_shop(SHOP_ID)
    if existing is not None:
        # Never overwrite: the owner may have edited the menu or settings, and orders point
        # at these products. Only the owner key follows OWNER_KEY (so it can be rotated).
        if key:
            store.set_owner_key_hash(existing.id, hash_owner_key(key))
        print(f"Sample shop '{existing.name}' already exists; left as it is."
              + (" Owner key: OWNER_KEY." if key else ""))
        return
    shop = store.save_shop(Shop(
        id=SHOP_ID, slug=SLUG, name="Mak's Kuih", tagline="Nyonya kuih, made fresh",
        shop_type="Home baker", address="Tampines, Singapore",
        # An example, not a real business: placeholder phone, area only, "Example shop" label.
        hours="Tue-Sun 9am-6pm", phone="+65 0000 0000", published=True, example=True,
        owner_email=(settings.sample_owner_email or "").strip().lower(),
        email_verified=bool(settings.sample_owner_email)))
    store.save_product(Product(
        id="kuih-lapis", shop_id=shop.id, name="Kuih Lapis", name_local="九层糕",
        category="Kuih", description="Steamed layered kuih.",
        variants=[Variant(label="20 pcs", price=Decimal("16")),
                  Variant(label="40 pcs", price=Decimal("30"))]))
    store.save_product(Product(
        id="ondeh-ondeh", shop_id=shop.id, name="Ondeh Ondeh", category="Kuih",
        base_price=Decimal("12.50"), unit="10 pcs",
        options=[ProductOption(name="Flavour", choices=["Pandan", "Gula Melaka"])]))
    if key:
        store.set_owner_key_hash(shop.id, hash_owner_key(key))
    print(f"Published shop '{shop.name}' (slug {SLUG}, id {SHOP_ID}) with 2 products. "
          + ("Owner key: OWNER_KEY." if key else "No owner key (OWNER_KEY is empty)."))


if __name__ == "__main__":
    main()
