"""Shared FastAPI dependencies."""

from fastapi import Header, HTTPException, Request

from backend.external import client_key
from backend.owner_auth import key_opens_shop

AUTH_FAIL_LIMIT = 10  # wrong owner keys per client per window
AUTH_FAIL_WINDOW_S = 300.0
TOO_MANY_TRIES = "Too many wrong keys. Please wait 5 minutes and try again."
WRONG_KEY = "That owner key doesn't open this shop. Check it and try again."


def caller(request: Request) -> str:
    host = request.client.host if request.client else None
    return client_key(request.headers, host)


def check_not_locked_out(request: Request) -> None:
    if request.app.state.auth_limiter.blocked(caller(request)):
        raise HTTPException(status_code=429, detail=TOO_MANY_TRIES)


def record_failed_key(request: Request) -> None:
    request.app.state.auth_limiter.allow(caller(request))


def require_owner(request: Request, x_owner_key: str | None = Header(default=None)) -> None:
    """Owner routes for /api/shops/{shop_id}/...: X-Owner-Key must be THIS shop's key.
    A key for another shop, an unknown shop and a wrong key all get the same 401, and every
    failure counts towards the per-client limit."""
    check_not_locked_out(request)
    shop_id = request.path_params.get("shop_id", "")
    if not x_owner_key:
        raise HTTPException(status_code=401, detail="Enter your owner key to manage this shop.")
    if not key_opens_shop(request.app.state.store, shop_id, x_owner_key.strip()):
        record_failed_key(request)
        raise HTTPException(status_code=401, detail=WRONG_KEY)
