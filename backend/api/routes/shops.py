"""Owner routes for shops.

Reading a first menu photo (POST /draft) needs no key: it creates a draft shop and returns a
draft key for the browser that uploaded it. Every route under /{shop_id} needs that shop's own
key (backend.api.deps.require_owner). Going live swaps the draft key for the real owner key,
which is returned once and stored only as a hash.
"""

import asyncio
import re
import unicodedata
from datetime import date
from decimal import Decimal

from fastapi import (
    APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, Request, Response, UploadFile,
)
from pydantic import BaseModel, Field

from agents.catalog import extract as catalog
from agents.catalog.checks import menu_checks
from agents.catalog.images import NOT_AN_IMAGE, ImageError, preprocess, sniff_image_type
from agents.commerce import pickup
from backend.api.deps import caller, require_owner
from backend import emails, mailer, owner_session
from backend.audit import log_event
from backend.images import get_image_store
from backend.mcp_server import MCP_PATH
from backend.models import Actor, Product, Shop, new_id
from backend.owner_auth import issue_owner_key
from backend.ucp.convert import orderable
from backend.ucp.profile import base_url

router = APIRouter(prefix="/api/shops")
OWNER = [Depends(require_owner)]

MAX_IMAGES = 5
MAX_IMAGE_MB = 10
MAX_IMAGE_BYTES = MAX_IMAGE_MB * 1024 * 1024


class DraftResponse(BaseModel):
    shop: Shop
    products: list[Product]
    warnings: list[str]
    # product id -> why the owner should check it (agents/catalog/checks.py). Guidance only.
    checks: dict[str, list[str]] = {}
    # Only on a new draft: the temporary key this browser uses until the shop goes live.
    draft_key: str | None = None

DRAFT_LIMIT = 5  # new drafts (Gemini photo reads) per client
DRAFT_WINDOW_S = 600.0
DRAFT_LIMIT_MESSAGE = ("You've read a lot of menus in a short time. Please wait 10 minutes, "
                       "then try again.")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "shop"


class ShopLinks(BaseModel):
    ucp_profile: str
    mcp: str
    public_page: str


class ShopDetail(BaseModel):
    shop: Shop
    products: list[Product]
    links: ShopLinks
    # product id -> why the owner should check it (agents/catalog/checks.py). Guidance only.
    checks: dict[str, list[str]] = {}
    # The hours as a weekly table for the settings page (9am-6pm daily if unreadable).
    opening_hours: list[dict] = []
    hours_readable: bool = True


def shop_detail(settings, shop: Shop, products: list[Product], cls=None, **extra):
    return (cls or ShopDetail)(shop=shop, products=products, links=shop_links(settings, shop),
                               checks=menu_checks(products),
                               opening_hours=pickup.week_table(shop),
                               hours_readable=pickup.hours_readable(shop), **extra)


class PublishResponse(ShopDetail):
    # Only the first time a shop goes live: the backup key. Shown to the owner once; never
    # stored in plain text.
    owner_key: str | None = None
    # Where the "confirm your email" link was sent (the owner's own address).
    verify_sent_to: str | None = None


class PublishIn(BaseModel):
    """Going live creates the owner's account: shop name and owner email (required the first
    time; ignored once the shop is live)."""

    name: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=owner_session.MAX_EMAIL_LEN)


def send_verify_email(store, settings, shop: Shop) -> mailer.Email:
    """A fresh "confirm your email" message for this shop (sent after the response)."""
    token = owner_session.issue_link(store, shop.id, "verify", owner_session.VERIFY_LINK_TTL,
                                     next_path=f"/shop/{shop.id}/orders")
    return emails.verify_email(shop, owner_session.link_url(settings, "verify", token))


VERIFY_RESEND_LIMIT = 3  # "send it again" per shop
VERIFY_RESEND_WINDOW_S = 900.0


def shop_links(settings, shop: Shop) -> ShopLinks:
    base = base_url(settings)
    return ShopLinks(ucp_profile=f"{base}/.well-known/ucp", mcp=f"{base}{MCP_PATH}",
                     public_page=f"{base}/s/{shop.slug}")


def _shop_or_404(store, shop_id: str) -> Shop:
    shop = store.get_shop(shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found.")
    return shop


async def _read_images(images: list[UploadFile]) -> list[bytes]:
    """1-5 photos, each at most 10 MB and really an image (checked from its bytes, not its
    name or content type)."""
    if not 1 <= len(images) <= MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"Please upload 1 to {MAX_IMAGES} photos.")
    raw: list[bytes] = []
    for upload in images:
        data = await upload.read(MAX_IMAGE_BYTES + 1)
        if not data:
            raise HTTPException(status_code=400, detail="One of the photos is empty.")
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400,
                                detail=f"Each photo must be {MAX_IMAGE_MB} MB or smaller.")
        if sniff_image_type(data) is None:
            raise HTTPException(status_code=400, detail=NOT_AN_IMAGE)
        raw.append(data)
    return raw


async def _clean(raw: list[bytes]) -> list[bytes]:
    """Rotate, shrink and re-encode as JPEG with no EXIF, so a photo's GPS location is never
    stored or sent to Gemini."""
    try:
        # Pillow work is CPU-bound; keep it off the event loop.
        return list(await asyncio.gather(*(asyncio.to_thread(preprocess, d) for d in raw)))
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _extract(jpegs: list[bytes], settings):
    try:
        return await catalog.extract_catalog_async(jpegs, settings=settings, preprocessed=True)
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except catalog.CatalogExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _save_extracted(store, settings, shop: Shop, jpegs: list[bytes], draft) -> list[Product]:
    image_store = get_image_store(settings)
    paths = [image_store.save(shop.id, jpeg, "jpg") for jpeg in jpegs]  # cleaned, no EXIF
    products = [
        store.save_product(Product(shop_id=shop.id, **p.model_dump())) for p in draft.products
    ]
    log_event(
        store,
        shop_id=shop.id,
        actor=Actor.catalog_agent,
        action="catalog_extracted",
        entity_type="shop",
        entity_id=shop.id,
        summary=f"Read {len(products)} items from {len(jpegs)} photo(s)",
        details={
            "model": settings.gemini_model,
            "images": paths,
            "item_count": len(products),
            "warnings": draft.warnings,
        },
    )
    return products


@router.post("/draft", response_model=DraftResponse)
async def create_draft(request: Request, images: list[UploadFile] = File(default=[])) -> DraftResponse:
    """Upload 1-5 menu photos -> draft (unpublished) shop with the extracted products, plus a
    draft key for this browser. No owner key needed; limited to DRAFT_LIMIT reads per client
    IP per 10 minutes (each photo is a Gemini call)."""
    raw = await _read_images(images)
    if not request.app.state.draft_limiter.allow(caller(request)):
        raise HTTPException(status_code=429, detail=DRAFT_LIMIT_MESSAGE)
    jpegs = await _clean(raw)
    settings = request.app.state.settings
    store = request.app.state.store
    draft = await _extract(jpegs, settings)

    name = draft.shop_name_guess or "My shop"
    shop = Shop(name=name, slug=f"{slugify(name)}-{new_id()[:4]}", currency=draft.currency)
    store.save_shop(shop)
    products = _save_extracted(store, settings, shop, jpegs, draft)
    return DraftResponse(shop=shop, products=products, warnings=draft.warnings,
                         checks=menu_checks(products), draft_key=issue_owner_key(store, shop.id))


@router.get("/{shop_id}", response_model=ShopDetail, dependencies=OWNER)
def get_shop(request: Request, shop_id: str) -> ShopDetail:
    store = request.app.state.store
    shop = _shop_or_404(store, shop_id)
    return shop_detail(request.app.state.settings, shop, store.list_products(shop.id))


@router.post("/{shop_id}/photos", response_model=DraftResponse, dependencies=OWNER)
async def add_photos(request: Request, shop_id: str,
                     images: list[UploadFile] = File(default=[])) -> DraftResponse:
    """Read more menu photos into an existing shop. New items are added, nothing is replaced."""
    store = request.app.state.store
    shop = _shop_or_404(store, shop_id)
    jpegs = await _clean(await _read_images(images))
    settings = request.app.state.settings
    draft = await _extract(jpegs, settings)
    products = _save_extracted(store, settings, shop, jpegs, draft)
    # Checks over the whole menu (e.g. a new item that duplicates an old one), for the new items.
    checks = menu_checks(store.list_products(shop.id))
    return DraftResponse(shop=shop, products=products, warnings=draft.warnings,
                         checks={p.id: checks[p.id] for p in products if p.id in checks})


def unique_slug(store, shop: Shop) -> str:
    base = slugify(shop.name)
    slug, n = base, 2
    while (other := store.get_shop_by_slug(slug)) is not None and other.id != shop.id:
        slug, n = f"{base}-{n}", n + 1
    return slug


@router.post("/{shop_id}/publish", response_model=PublishResponse, dependencies=OWNER)
def publish_shop(request: Request, response: Response, background: BackgroundTasks, shop_id: str,
                 body: PublishIn | None = Body(default=None)) -> PublishResponse:
    """Go live = create the owner's account. The first publish needs the shop name and owner
    email, picks a clean unique slug, issues the backup key (the draft key stops working),
    signs the owner in with a session cookie, and emails a "confirm your email" link. The shop
    is live straight away. Later publishes change nothing."""
    store = request.app.state.store
    settings = request.app.state.settings
    shop = _shop_or_404(store, shop_id)
    products = store.list_products(shop.id)
    if not shop.published:
        name = " ".join((body.name or "").split()) if body else ""
        email = owner_session.normalize_email(body.email or "") if body else None
        if not name:
            raise HTTPException(status_code=400, detail="Give your shop a name first.")
        if email is None:
            raise HTTPException(status_code=400,
                                detail="Enter your email so we can send you orders and sign-in links.")
        shop = shop.model_copy(update={"name": name, "owner_email": email, "email_verified": False})
    if not shop.name.strip():
        raise HTTPException(status_code=400, detail="Give your shop a name first.")
    if not any(orderable(p) for p in products):
        raise HTTPException(status_code=400,
                            detail="Add at least one available item with a price first.")
    owner_key = verify_sent_to = None
    if not shop.published:
        old_slug = shop.slug
        shop = shop.model_copy(update={"slug": unique_slug(store, shop), "published": True})
        store.save_shop(shop)
        log_event(
            store,
            shop_id=shop.id,
            actor=Actor.owner,
            action="shop_published",
            entity_type="shop",
            entity_id=shop.id,
            summary=f"Owner published the shop at /s/{shop.slug}",
            details={"slug": shop.slug, "previous_slug": old_slug,
                     "orderable_items": sum(orderable(p) for p in products)},
        )
        owner_key = issue_owner_key(store, shop.id)
        log_event(store, shop_id=shop.id, actor=Actor.system, action="owner_key_issued",
                  entity_type="shop", entity_id=shop.id,
                  summary="Backup owner key created (shown once; only its hash is stored)",
                  details={})
        owner_session.start_session(store, response, settings, shop.id)
        background.add_task(mailer.send_safely, settings, send_verify_email(store, settings, shop))
        verify_sent_to = shop.owner_email
        log_event(store, shop_id=shop.id, actor=Actor.system, action="verify_email_sent",
                  entity_type="shop", entity_id=shop.id,
                  summary=f"Sent a confirm-your-email link to {mailer.mask_email(shop.owner_email)}",
                  details={})
    return shop_detail(settings, shop, products, PublishResponse, owner_key=owner_key,
                       verify_sent_to=verify_sent_to)


@router.post("/{shop_id}/verify-email", dependencies=OWNER)
def resend_verify_email(request: Request, background: BackgroundTasks, shop_id: str) -> dict:
    """Send the "confirm your email" link again (limited per shop)."""
    store = request.app.state.store
    shop = _shop_or_404(store, shop_id)
    if shop.email_verified or not shop.owner_email:
        return {"sent_to": None, "verified": shop.email_verified}
    if not request.app.state.verify_limiter.allow(shop.id):
        raise HTTPException(status_code=429,
                            detail="We've sent a few already. Check your spam folder, or try again in 15 minutes.")
    settings = request.app.state.settings
    background.add_task(mailer.send_safely, settings, send_verify_email(store, settings, shop))
    return {"sent_to": shop.owner_email, "verified": False}


class DayHours(BaseModel):
    day: int = Field(ge=0, le=6)  # 0 = Monday
    closed: bool = False
    open: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    close: str = Field(default="18:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class ShopSettingsUpdate(BaseModel):
    """Only the fields sent are changed. daily_capacity and paused_until can be cleared with
    null (daily_capacity 0 also means no limit)."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    tagline: str | None = Field(default=None, max_length=160)
    shop_type: str | None = Field(default=None, max_length=60)
    address: str | None = Field(default=None, max_length=200)
    hours: str | None = Field(default=None, max_length=200)
    # The weekly table from the settings page; saved as hours text (pickup.format_week).
    opening_hours: list[DayHours] | None = Field(default=None, min_length=7, max_length=7)
    phone: str | None = Field(default=None, max_length=30)
    auto_approve_limit: Decimal | None = Field(default=None, ge=0, le=100000, decimal_places=2)
    min_notice_hours: int | None = Field(default=None, ge=0, le=336)
    daily_capacity: int | None = Field(default=None, ge=0, le=1000)
    approval_timeout_hours: int | None = Field(default=None, ge=1, le=168)
    cancel_cutoff_hours: int | None = Field(default=None, ge=0, le=168)
    paused_until: date | None = None


NULLABLE = {"daily_capacity", "paused_until"}


@router.patch("/{shop_id}", response_model=Shop, dependencies=OWNER)
def update_shop_settings(request: Request, shop_id: str, body: ShopSettingsUpdate) -> Shop:
    store = request.app.state.store
    shop = _shop_or_404(store, shop_id)
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items()
               if v is not None or k in NULLABLE}
    if "opening_hours" in changes:
        table = changes.pop("opening_hours")
        if {row["day"] for row in table} != set(range(7)):
            raise HTTPException(status_code=400, detail="Send hours for all 7 days.")
        if all(row["closed"] for row in table):
            raise HTTPException(status_code=400, detail=(
                "Open at least one day. To stop orders for a while, use Pause orders instead."))
        if any(not row["closed"] and row["open"] == row["close"] for row in table):
            raise HTTPException(status_code=400,
                                detail="Opening and closing time can't be the same.")
        changes["hours"] = pickup.format_week(table)
    if changes.get("daily_capacity") == 0:
        changes["daily_capacity"] = None
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to change.")
    before = {k: getattr(shop, k) for k in changes}
    shop = shop.model_copy(update=changes)
    store.save_shop(shop)
    log_event(
        store,
        shop_id=shop.id,
        actor=Actor.owner,
        action="shop_settings_updated",
        entity_type="shop",
        entity_id=shop.id,
        summary="Owner changed " + ", ".join(k.replace("_", " ") for k in changes),
        details={"before": {k: str(v) for k, v in before.items()},
                 "after": {k: str(v) for k, v in changes.items()}},
    )
    return shop
