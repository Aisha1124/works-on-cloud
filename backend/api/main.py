"""FastAPI app: REST API, /mcp, UCP routes, and the built dashboard."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agents.commerce import service as commerce
from backend.api.config import Settings, get_settings
from backend.api.deps import AUTH_FAIL_LIMIT, AUTH_FAIL_WINDOW_S
from backend.api.routes import health, orders, owner, products, public, shops
from backend.api.routes.owner import LINK_EMAIL_LIMIT, LINK_IP_LIMIT, LINK_WINDOW_S
from backend.api.routes.shops import (
    DRAFT_LIMIT, DRAFT_WINDOW_S, VERIFY_RESEND_LIMIT, VERIFY_RESEND_WINDOW_S,
)
from backend.api.spa import spa_router
from backend.external import ORDER_LIMIT, ORDER_WINDOW_S, RateLimiter
from backend.mcp_server import create_mcp_server, mcp_route
from backend.store import get_store
from backend.ucp import ucp_router

log = logging.getLogger(__name__)
SWEEP_EVERY_S = 300


def sweep_once(store, settings) -> None:
    """Housekeeping over every shop: expire held orders past their approval timeout."""
    for shop in store.list_shops():
        commerce.expire_due(store, settings, shop)


async def sweep_forever(store, settings) -> None:
    """Every 5 minutes while the instance runs. On Cloud Run this only runs while requests
    keep the instance busy, so every read of an order also expires it when due (lazy)."""
    while True:
        try:
            sweep_once(store, settings)
        except Exception:  # never let housekeeping take the server down
            log.exception("sweep failed")
        await asyncio.sleep(SWEEP_EVERY_S)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = get_store(settings)
    order_limiter = RateLimiter(ORDER_LIMIT, ORDER_WINDOW_S)  # shared by MCP and UCP
    mcp = create_mcp_server(store, settings, order_limiter)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        sweeper = asyncio.create_task(sweep_forever(store, settings))
        try:
            async with mcp.session_manager.run():
                yield
        finally:
            sweeper.cancel()

    app = FastAPI(title="KampungCart", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.mcp = mcp
    app.state.order_limiter = order_limiter  # MCP, UCP and the shop page
    app.state.auth_limiter = RateLimiter(AUTH_FAIL_LIMIT, AUTH_FAIL_WINDOW_S)  # wrong owner keys
    app.state.draft_limiter = RateLimiter(DRAFT_LIMIT, DRAFT_WINDOW_S)  # new menu photo reads
    app.state.link_ip_limiter = RateLimiter(LINK_IP_LIMIT, LINK_WINDOW_S)  # sign-in emails per client
    app.state.link_email_limiter = RateLimiter(LINK_EMAIL_LIMIT, LINK_WINDOW_S)  # ... per address
    app.state.verify_limiter = RateLimiter(VERIFY_RESEND_LIMIT, VERIFY_RESEND_WINDOW_S)  # per shop

    app.include_router(health.router)
    app.include_router(owner.router)
    app.include_router(shops.router)
    app.include_router(orders.router)
    app.include_router(products.router)
    app.include_router(public.router)  # /api/public/... and /s/{slug}

    # External agents. Both BEFORE the SPA catch-all below.
    app.router.routes.append(mcp_route(mcp, settings))
    app.include_router(ucp_router())

    app.include_router(spa_router(settings.dashboard_dist))
    return app


app = create_app()
