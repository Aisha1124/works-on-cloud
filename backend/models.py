"""Shared data models used by the API, MCP server, UCP routes and agents.

Money is always Decimal. In JSON it is a string (e.g. "12.50"), never a float.
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id() -> str:
    return uuid4().hex[:12]


def utc_now() -> datetime:
    return datetime.now(UTC)


class Channel(StrEnum):
    mcp = "mcp"
    ucp = "ucp"
    dashboard = "dashboard"
    web = "web"  # a customer ordering on the public shop page /s/{slug}


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class OrderStatus(StrEnum):
    auto_approved = "auto_approved"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    ready = "ready"
    done = "done"


class Actor(StrEnum):
    owner = "owner"
    system = "system"
    catalog_agent = "catalog_agent"
    risk_agent = "risk_agent"
    shopper_agent = "shopper_agent"
    external_agent = "external_agent"
    customer = "customer"  # a person ordering on the public shop page


class Shop(BaseModel):
    id: str = Field(default_factory=new_id)
    slug: str
    name: str
    tagline: str = ""
    shop_type: str = ""
    address: str = ""
    hours: str = ""
    phone: str = ""
    currency: str = "SGD"
    published: bool = False
    auto_approve_limit: Decimal = Decimal("150")
    # Only the seeded sample shop (mak-kuih): its pages say it is an example, not a real shop.
    example: bool = False
    # Set when the shop goes live. Owner-only: never part of a public or agent response.
    owner_email: str = ""
    email_verified: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class Variant(BaseModel):
    label: str  # size or pack, e.g. "20 pcs"
    price: Decimal


class ProductOption(BaseModel):
    name: str  # e.g. "Flavour"
    choices: list[str] = Field(default_factory=list)


class Product(BaseModel):
    id: str = Field(default_factory=new_id)
    shop_id: str
    name: str
    name_local: str = ""
    category: str = ""
    base_price: Decimal | None = None
    unit: str = ""
    variants: list[Variant] = Field(default_factory=list)
    options: list[ProductOption] = Field(default_factory=list)
    available: bool = True
    description: str = ""
    confidence: float = Field(default=1.0, ge=0, le=1)
    # Owner-only. Why the menu reader wants the owner to check this item (see
    # agents/catalog/checks.py); cleared once the owner saves the item.
    check_reasons: list[str] = Field(default_factory=list)
    owner_checked: bool = False  # the owner saved this item themselves


class OrderItem(BaseModel):
    product_id: str
    name: str
    variant: str | None = None
    options: dict[str, str] = Field(default_factory=dict)  # option name -> chosen value
    qty: int = Field(ge=1)
    unit_price: Decimal
    line_total: Decimal
    request: str = ""  # buyer's custom request for this line; untrusted text, owner confirms


class UnpricedRequest(BaseModel):
    """A line the buyer asked for that is not on the menu. It has no price until the owner
    sets one, so it is never part of the order total."""

    name: str
    qty: int = Field(ge=1)
    request: str = ""


class Risk(BaseModel):
    score: int = Field(ge=0, le=100)
    level: RiskLevel
    reasons: list[str] = Field(default_factory=list)
    explanation: str = ""


class Order(BaseModel):
    id: str = Field(default_factory=new_id)
    shop_id: str
    items: list[OrderItem]
    total: Decimal
    customer_name: str
    customer_phone: str
    pickup_at: datetime
    note: str = ""
    channel: Channel
    agent_name: str = ""
    risk: Risk | None = None
    status: OrderStatus
    rejection_reason: str = ""
    unpriced_requests: list[UnpricedRequest] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)  # why the owner must look at it
    review_codes: list[str] = Field(default_factory=list)  # commerce.HOLD_SENTENCES keys
    created_at: datetime = Field(default_factory=utc_now)


class CheckoutLine(BaseModel):
    id: str  # line id, e.g. "li_1"
    item_id: str  # UCP item id: product id, or "<product id>.v<n>" for a variant
    quantity: int
    options: dict[str, str] = Field(default_factory=dict)


class CheckoutBuyer(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone_number: str = ""


class CheckoutSession(BaseModel):
    """A UCP checkout session: what the buyer agent asked for. Prices are never stored here;
    they are re-quoted from the catalog, and after completion they come from the order."""

    id: str = Field(default_factory=lambda: f"chk_{new_id()}")
    shop_id: str
    lines: list[CheckoutLine]
    buyer: CheckoutBuyer = Field(default_factory=CheckoutBuyer)
    pickup_at: str = ""
    note: str = ""
    agent_name: str = ""
    canceled: bool = False
    order_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AuditEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    shop_id: str
    at: datetime = Field(default_factory=utc_now)
    actor: Actor
    action: str
    entity_type: str
    entity_id: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
