"""Owner sign-in by email: one-time links and session cookies.

- Sign-in and verification links carry a random token. Only its SHA-256 hash is stored, with
  the shop it opens, its purpose and an expiry. A token works once (pop_secret is atomic).
- A session is a random token in an HttpOnly, SameSite=Lax cookie; the store keeps its hash,
  the shop and an expiry. A session opens exactly one shop.
"""

import hashlib
import re
import secrets
from datetime import datetime, timedelta

from fastapi import Response

from backend.api.config import Settings
from backend.models import utc_now
from backend.store.base import Store

LINKS = "link_tokens"
SESSIONS = "sessions"
COOKIE = "kc_session"

LOGIN_LINK_TTL = timedelta(minutes=15)
# The "Review order" button in an order email signs the owner in too. Owners read those emails
# hours later, so that link lives longer (still single use, still one shop).
ORDER_LINK_TTL = timedelta(hours=24)
VERIFY_LINK_TTL = timedelta(days=3)
SESSION_TTL = timedelta(days=30)

MAX_EMAIL_LEN = 254
_EMAIL = re.compile(r"^[^@\s<>\"',;]+@[^@\s<>\"',;]+\.[A-Za-z]{2,}$")


def normalize_email(text: str) -> str | None:
    """Lower-case, trimmed, plausible email address, or None."""
    email = (text or "").strip().lower()
    return email if len(email) <= MAX_EMAIL_LEN and _EMAIL.match(email) else None


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _iso(when: datetime) -> str:
    return when.isoformat()


def _expired(row: dict, now: datetime) -> bool:
    return datetime.fromisoformat(row["expires_at"]) <= now


# --- one-time links ---------------------------------------------------------------------


def issue_link(store: Store, shop_id: str, purpose: str, ttl: timedelta, next_path: str = "",
               now: datetime | None = None) -> str:
    """purpose: "login" or "verify". next_path: where to go after signing in (an app path)."""
    token = secrets.token_urlsafe(32)
    now = now or utc_now()
    store.put_secret(LINKS, _hash(token), {"shop_id": shop_id, "purpose": purpose,
                                           "next": next_path if next_path.startswith("/") else "",
                                           "expires_at": _iso(now + ttl)})
    return token


def use_link(store: Store, token: str, purpose: str, now: datetime | None = None) -> dict | None:
    """The link's record if it is valid for `purpose`, else None. Valid or not, it is used up."""
    if not token or len(token) > 200:
        return None
    row = store.pop_secret(LINKS, _hash(token))
    if row is None or row.get("purpose") != purpose or _expired(row, now or utc_now()):
        return None
    return row


def link_url(settings: Settings, page: str, token: str) -> str:
    """The app page that confirms the link with a tap (email scanners only follow GET links,
    so opening the link alone never uses it up)."""
    return f"{settings.base_url.rstrip('/')}/{page}?token={token}"


# --- sessions ---------------------------------------------------------------------------


def start_session(store: Store, response: Response, settings: Settings, shop_id: str,
                  now: datetime | None = None) -> None:
    token = secrets.token_urlsafe(32)
    now = now or utc_now()
    store.put_secret(SESSIONS, _hash(token), {"shop_id": shop_id,
                                              "expires_at": _iso(now + SESSION_TTL)})
    response.set_cookie(
        COOKIE, token, max_age=int(SESSION_TTL.total_seconds()), httponly=True,
        secure=settings.base_url.startswith("https://"), samesite="lax", path="/")


def session_shop(store: Store, token: str | None, now: datetime | None = None) -> str | None:
    if not token or len(token) > 200:
        return None
    row = store.get_secret(SESSIONS, _hash(token))
    if row is None or _expired(row, now or utc_now()):
        return None
    return row["shop_id"]


def end_session(store: Store, response: Response, token: str | None) -> None:
    if token and len(token) <= 200:
        store.pop_secret(SESSIONS, _hash(token))
    response.delete_cookie(COOKIE, path="/")
