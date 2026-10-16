"""Owner routes for editing a shop's products."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.api.deps import require_owner
from backend.audit import log_event
from backend.models import Actor, Product

router = APIRouter(prefix="/api/shops/{shop_id}/products", dependencies=[Depends(require_owner)])


class VariantIn(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    price: Decimal = Field(ge=0, le=100000, decimal_places=2)


class OptionIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    choices: list[str] = Field(default_factory=list, max_length=20)


class ProductIn(BaseModel):
    """The whole product as the owner sees it. Items the owner saves get confidence 1 and lose
    their read-time check reasons (the owner has looked at them)."""

    name: str = Field(min_length=1, max_length=80)
    name_local: str = Field(default="", max_length=80)
    category: str = Field(default="", max_length=60)
    base_price: Decimal | None = Field(default=None, ge=0, le=100000, decimal_places=2)
    unit: str = Field(default="", max_length=40)
    variants: list[VariantIn] = Field(default_factory=list, max_length=20)
    options: list[OptionIn] = Field(default_factory=list, max_length=10)
    available: bool = True
    description: str = Field(default="", max_length=300)

    def fields(self) -> dict:
        data = self.model_dump()
        data["name"] = data["name"].strip()
        for opt in data["options"]:
            opt["choices"] = [c.strip() for c in opt["choices"] if c.strip()][:20]
        return data


def _store(request: Request, shop_id: str):
    store = request.app.state.store
    if store.get_shop(shop_id) is None:
        raise HTTPException(status_code=404, detail="Shop not found.")
    return store


def _product_or_404(store, shop_id: str, product_id: str) -> Product:
    product = store.get_product(product_id)
    if product is None or product.shop_id != shop_id:
        raise HTTPException(status_code=404, detail="Item not found.")
    return product


def _snapshot(p: Product) -> dict:
    return p.model_dump(mode="json", exclude={"shop_id"})


@router.post("", response_model=Product, status_code=201)
def create_product(request: Request, shop_id: str, body: ProductIn) -> Product:
    store = _store(request, shop_id)
    product = store.save_product(Product(shop_id=shop_id, confidence=1.0, owner_checked=True,
                                         **body.fields()))
    log_event(store, shop_id=shop_id, actor=Actor.owner, action="product_created",
              entity_type="product", entity_id=product.id,
              summary=f"Owner added {product.name}", details={"after": _snapshot(product)})
    return product


@router.put("/{product_id}", response_model=Product)
def update_product(request: Request, shop_id: str, product_id: str, body: ProductIn) -> Product:
    store = _store(request, shop_id)
    before = _product_or_404(store, shop_id, product_id)
    fields = body.fields()
    old = before.model_dump(include=set(fields))
    # Only "sold out" toggled: the owner hasn't looked at the item, so its checks stay.
    toggled_only = {k for k in fields if fields[k] != old[k]} <= {"available"} and (
        fields["available"] != old["available"])
    checked = {} if toggled_only else {"confidence": 1.0, "check_reasons": [],
                                       "owner_checked": True}
    product = store.save_product(Product.model_validate(
        {**before.model_dump(), **fields, **checked}))
    log_event(store, shop_id=shop_id, actor=Actor.owner, action="product_updated",
              entity_type="product", entity_id=product.id,
              summary=f"Owner edited {product.name}",
              details={"before": _snapshot(before), "after": _snapshot(product)})
    return product


@router.delete("/{product_id}", status_code=204)
def delete_product(request: Request, shop_id: str, product_id: str) -> Response:
    store = _store(request, shop_id)
    product = _product_or_404(store, shop_id, product_id)
    store.delete_product(product.id)
    log_event(store, shop_id=shop_id, actor=Actor.owner, action="product_deleted",
              entity_type="product", entity_id=product.id,
              summary=f"Owner removed {product.name}", details={"before": _snapshot(product)})
    return Response(status_code=204)
