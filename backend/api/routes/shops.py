"""Owner routes for shops."""

import re
import unicodedata
from decimal import Decimal
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from agents.catalog import extract as catalog
from agents.catalog.images import ImageError
from backend.api.deps import require_owner
from backend.audit import log_event
from backend.images import get_image_store
from backend.mcp_server import MCP_PATH
from backend.models import Actor, Product, Shop, new_id
from backend.ucp.convert import orderable
from backend.ucp.profile import base_url

router = APIRouter(prefix="/api/shops", dependencies=[Depends(require_owner)])

MAX_IMAGES = 5
MAX_IMAGE_BYTES = 15 * 1024 * 1024
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "heic", "heif"}


class DraftResponse(BaseModel):
    shop: Shop
    products: list[Product]
    warnings: list[str]


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


class ShopSummary(BaseModel):
    id: str
    name: str
    slug: str
    published: bool


def shop_links(settings, shop: Shop) -> ShopLinks:
    base = base_url(settings)
    return ShopLinks(ucp_profile=f"{base}/.well-known/ucp", mcp=f"{base}{MCP_PATH}",
                     public_page=f"{base}/s/{shop.slug}")


def _shop_or_404(store, shop_id: str) -> Shop:
    shop = store.get_shop(shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found.")
    return shop


async def _read_images(images: list[UploadFile]) -> list[tuple[bytes, str]]:
    if not 1 <= len(images) <= MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"Please upload 1 to {MAX_IMAGES} photos.")
    blobs: list[tuple[bytes, str]] = []
    for upload in images:
        data = await upload.read(MAX_IMAGE_BYTES + 1)
        if not data:
            raise HTTPException(status_code=400, detail="One of the photos is empty.")
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Each photo must be 15 MB or smaller.")
        ext = PurePath(upload.filename or "").suffix.lstrip(".").lower()
        blobs.append((data, ext if ext in IMAGE_EXTS else "img"))
    return blobs


async def _extract(blobs: list[tuple[bytes, str]], settings):
    try:
        return await catalog.extract_catalog_async([d for d, _ in blobs], settings=settings)
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except catalog.CatalogExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _save_extracted(store, settings, shop: Shop, blobs, draft) -> list[Product]:
    image_store = get_image_store(settings)
    paths = [image_store.save(shop.id, data, ext) for data, ext in blobs]
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
        summary=f"Read {len(products)} items from {len(blobs)} photo(s)",
        details={
            "model": settings.gemini_model,
            "images": paths,
            "item_count": len(products),
            "warnings": draft.warnings,
        },
    )
    return products


@router.get("", response_model=list[ShopSummary])
def list_shops(request: Request) -> list[ShopSummary]:
    """Newest first."""
    shops = sorted(request.app.state.store.list_shops(), key=lambda s: s.created_at, reverse=True)
    return [ShopSummary(id=s.id, name=s.name, slug=s.slug, published=s.published) for s in shops]


@router.post("/draft", response_model=DraftResponse)
async def create_draft(request: Request, images: list[UploadFile] = File(default=[])) -> DraftResponse:
    """Upload 1-5 menu photos -> draft (unpublished) shop with the extracted products."""
    blobs = await _read_images(images)
    settings = request.app.state.settings
    store = request.app.state.store
    draft = await _extract(blobs, settings)

    name = draft.shop_name_guess or "My shop"
    shop = Shop(name=name, slug=f"{slugify(name)}-{new_id()[:4]}", currency=draft.currency)
    store.save_shop(shop)
    products = _save_extracted(store, settings, shop, blobs, draft)
    return DraftResponse(shop=shop, products=products, warnings=draft.warnings)


@router.get("/{shop_id}", response_model=ShopDetail)
def get_shop(request: Request, shop_id: str) -> ShopDetail:
    store = request.app.state.store
    shop = _shop_or_404(store, shop_id)
    return ShopDetail(shop=shop, products=store.list_products(shop.id),
                      links=shop_links(request.app.state.settings, shop))


@router.post("/{shop_id}/photos", response_model=DraftResponse)
async def add_photos(request: Request, shop_id: str,
                     images: list[UploadFile] = File(default=[])) -> DraftResponse:
    """Read more menu photos into an existing shop. New items are added, nothing is replaced."""
    store = request.app.state.store
    shop = _shop_or_404(store, shop_id)
    blobs = await _read_images(images)
    settings = request.app.state.settings
    draft = await _extract(blobs, settings)
    products = _save_extracted(store, settings, shop, blobs, draft)
    return DraftResponse(shop=shop, products=products, warnings=draft.warnings)


def unique_slug(store, shop: Shop) -> str:
    base = slugify(shop.name)
    slug, n = base, 2
    while (other := store.get_shop_by_slug(slug)) is not None and other.id != shop.id:
        slug, n = f"{base}-{n}", n + 1
    return slug


@router.post("/{shop_id}/publish", response_model=ShopDetail)
def publish_shop(request: Request, shop_id: str) -> ShopDetail:
    """Go live. The first publish picks a clean, unique slug; later ones keep it."""
    store = request.app.state.store
    shop = _shop_or_404(store, shop_id)
    products = store.list_products(shop.id)
    if not shop.name.strip():
        raise HTTPException(status_code=400, detail="Give your shop a name first.")
    if not any(orderable(p) for p in products):
        raise HTTPException(status_code=400,
                            detail="Add at least one available item with a price first.")
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
    return ShopDetail(shop=shop, products=products,
                      links=shop_links(request.app.state.settings, shop))


class ShopSettingsUpdate(BaseModel):
    """Only the fields sent are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    tagline: str | None = Field(default=None, max_length=160)
    shop_type: str | None = Field(default=None, max_length=60)
    address: str | None = Field(default=None, max_length=200)
    hours: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    auto_approve_limit: Decimal | None = Field(default=None, ge=0, le=100000, decimal_places=2)


@router.patch("/{shop_id}", response_model=Shop)
def update_shop_settings(request: Request, shop_id: str, body: ShopSettingsUpdate) -> Shop:
    store = request.app.state.store
    shop = _shop_or_404(store, shop_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
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
