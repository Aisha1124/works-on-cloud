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
from backend.models import Actor, Product, Shop, new_id

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


@router.post("/draft", response_model=DraftResponse)
async def create_draft(request: Request, images: list[UploadFile] = File(default=[])) -> DraftResponse:
    """Upload 1-5 menu photos -> draft (unpublished) shop with the extracted products."""
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

    settings = request.app.state.settings
    store = request.app.state.store
    try:
        draft = await catalog.extract_catalog_async([d for d, _ in blobs], settings=settings)
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except catalog.CatalogExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    name = draft.shop_name_guess or "My shop"
    shop = Shop(name=name, slug=f"{slugify(name)}-{new_id()[:4]}", currency=draft.currency)
    store.save_shop(shop)

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
    return DraftResponse(shop=shop, products=products, warnings=draft.warnings)


class ShopSettingsUpdate(BaseModel):
    """Only the fields sent are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    tagline: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=200)
    hours: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    auto_approve_limit: Decimal | None = Field(default=None, ge=0, le=100000, decimal_places=2)


@router.patch("/{shop_id}", response_model=Shop)
def update_shop_settings(request: Request, shop_id: str, body: ShopSettingsUpdate) -> Shop:
    store = request.app.state.store
    shop = store.get_shop(shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found.")
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
