"""Shared FastAPI dependencies."""

from fastapi import Header, HTTPException, Request

from backend.external import client_key
from backend.owner_auth import key_opens_shop
from backend.owner_session import COOKIE, session_shop

AUTH_FAIL_LIMIT = 10  # wrong owner keys / bad sign-in links per client per window
AUTH_FAIL_WINDOW_S = 300.0
TOO_MANY_TRIES = "Too many wrong tries. Please wait 5 minutes and try again."
WRONG_KEY = "That owner key doesn't open this shop. Check it and try again."
SIGN_IN = "Please sign in to manage this shop."
OTHER_SHOP = "You're signed in to a different shop. Sign out, then sign in to this one."
# Cookie-signed requests that change something must come from the dashboard (CSRF guard on top
# of SameSite=Lax): the dashboard's fetch sends this header; a form on another site can't.
CSRF_HEADER, CSRF_VALUE = "x-requested-with", "kampungcart"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def caller(request: Request) -> str:
    host = request.client.host if request.client else None
    return client_key(request.headers, host)


def check_not_locked_out(request: Request) -> None:
    if request.app.state.auth_limiter.blocked(caller(request)):
        raise HTTPException(status_code=429, detail=TOO_MANY_TRIES)


def record_failed_key(request: Request) -> None:
    request.app.state.auth_limiter.allow(caller(request))


def require_owner(request: Request, x_owner_key: str | None = Header(default=None)) -> None:
    """Owner routes for /api/shops/{shop_id}/...: either the X-Owner-Key header (backup key or
    draft key) is THIS shop's key, or the session cookie is a sign-in to THIS shop.
    A wrong key counts towards the per-client limit."""
    check_not_locked_out(request)
    store = request.app.state.store
    shop_id = request.path_params.get("shop_id", "")
    if x_owner_key:
        if key_opens_shop(store, shop_id, x_owner_key.strip()):
            return
        record_failed_key(request)
        raise HTTPException(status_code=401, detail=WRONG_KEY)
    signed_in = session_shop(store, request.cookies.get(COOKIE))
    if signed_in is None:
        raise HTTPException(status_code=401, detail=SIGN_IN)
    if signed_in != shop_id:
        raise HTTPException(status_code=401, detail=OTHER_SHOP)
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(status_code=403, detail="Please make this change from your KampungCart dashboard.")
