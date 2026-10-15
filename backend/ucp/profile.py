"""The UCP discovery profile served at /.well-known/ucp.

Spec: https://ucp.dev/2026-08-25/specification/overview/ (checked 2026-10-15).
One platform profile for all shops; the spec defines no per-merchant profile.
See docs/architecture/UCP_IMPLEMENTATION.md for what is and isn't implemented.
"""

from typing import Any

from backend.api.config import Settings

UCP_VERSION = "2026-08-25"
SPEC = f"https://ucp.dev/{UCP_VERSION}"

CHECKOUT = "dev.ucp.shopping.checkout"
CATALOG_SEARCH = "dev.ucp.shopping.catalog.search"
CATALOG_LOOKUP = "dev.ucp.shopping.catalog.lookup"

PAY_AT_PICKUP_NAME = "com.kampungcart.pay_at_pickup"
PAY_AT_PICKUP_ID = "pay_at_pickup"
PAY_AT_PICKUP_TEXT = ("Pay at pickup: the buyer pays the shop in person when collecting the "
                      "order. No payment details are collected and no money moves online.")

API_PREFIX = "/ucp/v1"
PAY_AT_PICKUP_SCHEMA_PATH = "/ucp/schemas/pay_at_pickup.json"


def base_url(settings: Settings) -> str:
    return settings.base_url.rstrip("/")


def payment_handlers(settings: Settings) -> dict[str, Any]:
    return {PAY_AT_PICKUP_NAME: [{
        "id": PAY_AT_PICKUP_ID,
        "version": UCP_VERSION,
        "spec": f"{base_url(settings)}{PAY_AT_PICKUP_SCHEMA_PATH}",
        "schema": f"{base_url(settings)}{PAY_AT_PICKUP_SCHEMA_PATH}",
        "available_instruments": [{"type": "pay_at_pickup"}],
        "config": {"description": PAY_AT_PICKUP_TEXT},
    }]}


def envelope(settings: Settings, *capabilities: str, status: str | None = None) -> dict[str, Any]:
    """The `ucp` member every response carries: the version and the capability used."""
    ucp: dict[str, Any] = {"version": UCP_VERSION,
                           "capabilities": {c: [{"version": UCP_VERSION}] for c in capabilities}}
    if CHECKOUT in capabilities:
        ucp["payment_handlers"] = payment_handlers(settings)
    if status:
        ucp["status"] = status
    return ucp


def business_profile(settings: Settings) -> dict[str, Any]:
    return {
        "ucp": {
            "version": UCP_VERSION,
            "services": {"dev.ucp.shopping": [{
                "version": UCP_VERSION,
                "spec": f"{SPEC}/specification/overview/",
                "transport": "rest",
                "endpoint": f"{base_url(settings)}{API_PREFIX}",
                "schema": f"{SPEC}/services/shopping/rest.openapi.json",
            }]},
            "capabilities": {
                CHECKOUT: [{"version": UCP_VERSION,
                            "spec": f"{SPEC}/specification/shopping/checkout",
                            "schema": f"{SPEC}/schemas/shopping/checkout.json"}],
                CATALOG_SEARCH: [{"version": UCP_VERSION,
                                  "spec": f"{SPEC}/specification/shopping/catalog",
                                  "schema": f"{SPEC}/schemas/shopping/catalog_search.json"}],
                CATALOG_LOOKUP: [{"version": UCP_VERSION,
                                  "spec": f"{SPEC}/specification/shopping/catalog",
                                  "schema": f"{SPEC}/schemas/shopping/catalog_lookup.json"}],
            },
            "payment_handlers": payment_handlers(settings),
        },
        "kampungcart": {
            "about": "KampungCart hosts many small Singapore shops behind one UCP endpoint. "
                     "Search the catalog (optionally filters.shop = shop slug); a checkout "
                     "must contain items from one shop.",
            "payment": PAY_AT_PICKUP_TEXT,
            "fulfillment": "Pickup at the shop only. Send kampungcart.pickup_at "
                           "(Singapore time, e.g. 2026-10-17T10:00) in the checkout.",
            "approval": "Large or risky orders are held for the shop owner. Such a checkout "
                        "stays complete_in_progress until the owner approves (completed) or "
                        "rejects (canceled). Poll GET /checkout-sessions/{id}.",
            "mcp": f"{base_url(settings)}/mcp",
        },
    }


PAY_AT_PICKUP_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "KampungCart pay at pickup instrument",
    "description": PAY_AT_PICKUP_TEXT,
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "handler_id": {"const": PAY_AT_PICKUP_ID},
        "type": {"const": "pay_at_pickup"},
    },
    "required": ["handler_id"],
}
