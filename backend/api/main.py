"""FastAPI app: REST API, /mcp, UCP routes, and the built dashboard."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agents.commerce import service as commerce
from backend import privacy
from backend.api.config import Settings, get_settings
from backend.api.deps import AUTH_FAIL_LIMIT, AUTH_FAIL_WINDOW_S
from agents.shopper.assistant import ShopAssistant
from backend.api.routes import chat, health, orders, owner, products, public, shops
from backend.api.routes.chat import (
    CHAT_IP_LIMIT, CHAT_IP_WINDOW_S, CHAT_SITE_LIMIT, CHAT_SITE_WINDOW_S,
)
from backend.api.routes.owner import LINK_EMAIL_LIMIT, LINK_IP_LIMIT, LINK_WINDOW_S
from backend.api.routes.shops import (
    DRAFT_LIMIT, DRAFT_WINDOW_S, VERIFY_RESEND_LIMIT, VERIFY_RESEND_WINDOW_S,
)
from backend.api.routes.public import (
    REPORT_IP_LIMIT, REPORT_IP_WINDOW_S, REPORT_SHOP_LIMIT, REPORT_SHOP_WINDOW_S,
)
from backend.api.spa import spa_router
from backend.external import ORDER_LIMIT, ORDER_WINDOW_S, StoreRateLimiter
from backend.mcp_server import create_mcp_server, mcp_route
from backend.store import get_store
from backend.ucp import ucp_router

log = logging.getLogger(__name__)
SWEEP_EVERY_S = 300


def sweep_once(store, settings) -> None:
    """Housekeeping over every shop: expire held orders past their approval timeout, and erase
    customer details 90 days after pickup (backend/privacy.py)."""
    for shop in store.list_shops():
        commerce.expire_due(store, settings, shop)
        privacy.erase_old_personal_data(store, shop)


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
    # Rate limits live in the store, so all Cloud Run instances share them.
    def limiter(name: str, limit: int, window_s: float) -> StoreRateLimiter:
        return StoreRateLimiter(store, name, limit, window_s)

    order_limiter = limiter("orders", ORDER_LIMIT, ORDER_WINDOW_S)  # shared by MCP and UCP
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
    app.state.auth_limiter = limiter("auth_fail", AUTH_FAIL_LIMIT, AUTH_FAIL_WINDOW_S)  # wrong keys
    app.state.draft_limiter = limiter("drafts", DRAFT_LIMIT, DRAFT_WINDOW_S)  # menu photo reads
    app.state.link_ip_limiter = limiter("link_ip", LINK_IP_LIMIT, LINK_WINDOW_S)  # per client
    app.state.link_email_limiter = limiter("link_email", LINK_EMAIL_LIMIT, LINK_WINDOW_S)
    app.state.verify_limiter = limiter("verify", VERIFY_RESEND_LIMIT, VERIFY_RESEND_WINDOW_S)
    app.state.report_ip_limiter = limiter("report_ip", REPORT_IP_LIMIT, REPORT_IP_WINDOW_S)
    app.state.report_shop_limiter = limiter("report_shop", REPORT_SHOP_LIMIT,
                                            REPORT_SHOP_WINDOW_S)
    app.state.chat_ip_limiter = limiter("chat_ip", CHAT_IP_LIMIT, CHAT_IP_WINDOW_S)
    app.state.chat_site_limiter = limiter("chat_site", CHAT_SITE_LIMIT, CHAT_SITE_WINDOW_S)
    # "Order with AI": an ADK agent that orders through this app's own /mcp route.
    app.state.shop_assistant = ShopAssistant(app, settings)

    app.include_router(health.router)
    app.include_router(owner.router)
    app.include_router(shops.router)
    app.include_router(orders.router)
    app.include_router(products.router)
    app.include_router(public.router)  # /api/public/... and /s/{slug}
    app.include_router(chat.router)  # /api/public/shops/{slug}/chat

    # External agents. Both BEFORE the SPA catch-all below.
    app.router.routes.append(mcp_route(mcp, settings))
    app.include_router(ucp_router())

    app.include_router(spa_router(settings.dashboard_dist))
    return app


app = create_app()
