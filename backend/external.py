"""Shared rules for external AI agents, used by the MCP server and the UCP routes.

Only plumbing lives here: which shops are visible, per-client rate limits, input clean-up and
the audit record of every external call. Business logic stays in agents/commerce.
"""

import re
import threading
import time
from collections import defaultdict, deque

from backend.audit import log_event
from backend.models import Actor, Channel, Shop
from backend.store.base import Store

PLATFORM = "platform"  # audit shop_id for calls that aren't about one shop (find_shops, profile)
MAX_AGENT_NAME_LEN = 80
MAX_QUERY_LEN = 100
MAX_SLUG_LEN = 60
MAX_ID_LEN = 64
GENERIC_ERROR = "Something went wrong on our side. Please try again in a minute."


class ShopNotFound(LookupError):
    def __init__(self, slug: str):
        super().__init__(f"No shop called '{slug}'. Use find_shops to see the shops you can order from.")


def published_shop(store: Store, slug: str) -> Shop:
    """The published shop with this slug. Unpublished shops are invisible to external agents."""
    shop = store.get_shop_by_slug((slug or "").strip()[:MAX_SLUG_LEN]) if slug else None
    if shop is None or not shop.published:
        raise ShopNotFound((slug or "").strip()[:MAX_SLUG_LEN])
    return shop


def published_shops(store: Store) -> list[Shop]:
    return [s for s in store.list_shops() if s.published]


def clean_agent_name(name: str | None) -> str:
    """One line, at most 80 characters. Kept as data only, never followed."""
    return " ".join((name or "").split())[:MAX_AGENT_NAME_LEN]


def area_of(shop: Shop) -> str:
    """The last part of the address, e.g. "Tampines" from "Blk 123, Tampines" or from
    "Tampines, Singapore" (a trailing country/postcode part is skipped)."""
    parts = [p.strip() for p in shop.address.split(",") if p.strip()]
    while len(parts) > 1 and re.fullmatch(r"(?i)(republic of )?singapore( \d{6})?|\d{6}",
                                          parts[-1]):
        parts.pop()
    return parts[-1] if parts else ""


def mask_phone(phone: str) -> str:
    """'+65 9123 4567' -> '****4567'. Customer phone numbers are never sent back to agents,
    and order emails only show the last 4 digits."""
    digits = "".join(c for c in phone if c.isdigit())
    return f"****{digits[-4:]}" if len(digits) > 4 else ("****" if digits else "")


def client_key(headers, client_host: str | None) -> str:
    """Who is calling, for rate limits. Cloud Run puts the caller first in X-Forwarded-For."""
    forwarded = (headers or {}).get("x-forwarded-for", "") if headers is not None else ""
    first = forwarded.split(",")[0].strip()
    return first or client_host or "unknown"


class RateLimiter:
    """At most `limit` events per `window_s` seconds per key. In memory, per instance."""

    def __init__(self, limit: int, window_s: float, clock=time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def blocked(self, key: str) -> bool:
        """True if `key` has used up its limit. Records nothing."""
        now = self._clock()
        with self._lock:
            hits = self._hits.get(key)
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            return bool(hits) and len(hits) >= self.limit


ORDER_LIMIT = 10  # orders per client per minute
ORDER_WINDOW_S = 60.0
RATE_LIMIT_MESSAGE = (f"Too many orders from this client: the limit is {ORDER_LIMIT} a minute. "
                      "Wait a minute, then try again.")


def audit_external_call(
    store: Store, *, shop_id: str | None, channel: Channel, call: str, agent_name: str,
    ok: bool, error: str = "", entity_id: str = "",
) -> None:
    """One audit event per external call, successful or not. actor = external_agent."""
    by = agent_name or "an unnamed agent"
    outcome = "ok" if ok else f"failed: {error}"
    log_event(
        store, shop_id=shop_id or PLATFORM, actor=Actor.external_agent, action="external_call",
        entity_type="call", entity_id=entity_id or call,
        summary=f"{by} called {call} via {channel.value.upper()} ({outcome})"[:300],
        details={"channel": channel.value, "call": call, "agent_name": agent_name, "ok": ok,
                 "error": error[:300]},
    )
