"""Shared FastAPI dependencies."""

import secrets

from fastapi import Header, HTTPException, Request


def require_owner(request: Request, x_owner_key: str | None = Header(default=None)) -> None:
    """Owner routes need the X-Owner-Key header to match OWNER_KEY."""
    expected = request.app.state.settings.owner_key
    if expected is None or not expected.get_secret_value():
        raise HTTPException(status_code=503, detail="Owner access is not set up (OWNER_KEY is empty).")
    if not x_owner_key or not secrets.compare_digest(
        x_owner_key.encode(), expected.get_secret_value().encode()
    ):
        raise HTTPException(status_code=401, detail="Wrong or missing owner key.")
