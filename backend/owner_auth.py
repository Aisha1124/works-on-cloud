"""Per-shop owner keys.

Each shop has its own owner key. Only a SHA-256 hash is stored (in the store's owner-key
collection, never on the Shop model, so no API response can carry it). Generated keys are
256-bit random tokens, so a fast hash is enough: there is nothing to brute-force offline.
The plain key is shown to the owner once, when the shop goes live.

A draft shop gets a temporary key when its menu photo is read. The browser that uploaded
the photo uses it to review the menu. Going live replaces it with the real owner key.
"""

import hashlib
import secrets

from backend.store.base import Store

KEY_PREFIX = "kc_"
MAX_KEY_LEN = 200


def new_owner_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_owner_key(key: str) -> str:
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()


def issue_owner_key(store: Store, shop_id: str) -> str:
    """A new key for this shop. Any earlier key for the shop stops working."""
    key = new_owner_key()
    store.set_owner_key_hash(shop_id, hash_owner_key(key))
    return key


def key_opens_shop(store: Store, shop_id: str, key: str | None) -> bool:
    if not key or len(key) > MAX_KEY_LEN:
        return False
    stored = store.get_owner_key_hash(shop_id)
    return bool(stored) and secrets.compare_digest(stored, hash_owner_key(key))


def shop_for_key(store: Store, key: str | None) -> str | None:
    """The id of the shop this key opens, or None."""
    if not key or len(key) > MAX_KEY_LEN:
        return None
    return store.find_shop_by_owner_key_hash(hash_owner_key(key))
