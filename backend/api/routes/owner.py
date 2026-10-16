"""Owner login: an owner key -> the one shop it opens."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.deps import check_not_locked_out, record_failed_key
from backend.owner_auth import MAX_KEY_LEN, shop_for_key

router = APIRouter(prefix="/api/owner")

LOGIN_FAILED = "That key doesn't match any shop. Check it (it starts with kc_) and try again."


class LoginBody(BaseModel):
    key: str = Field(max_length=MAX_KEY_LEN)


class LoginResponse(BaseModel):
    shop_id: str
    name: str
    slug: str
    published: bool


@router.post("/login", response_model=LoginResponse)
def login(request: Request, body: LoginBody) -> LoginResponse:
    """Wrong keys count towards the same per-client limit as the owner routes."""
    check_not_locked_out(request)
    store = request.app.state.store
    shop_id = shop_for_key(store, body.key.strip())
    shop = store.get_shop(shop_id) if shop_id else None
    if shop is None:
        record_failed_key(request)
        raise HTTPException(status_code=401, detail=LOGIN_FAILED)
    return LoginResponse(shop_id=shop.id, name=shop.name, slug=shop.slug,
                         published=shop.published)
