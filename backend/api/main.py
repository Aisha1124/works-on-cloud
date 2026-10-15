"""FastAPI app: REST API, /mcp, UCP routes, and the built dashboard."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api.config import Settings, get_settings
from backend.api.routes import health, orders, shops
from backend.api.spa import spa_router
from backend.external import ORDER_LIMIT, ORDER_WINDOW_S, RateLimiter
from backend.mcp_server import create_mcp_server, mcp_route
from backend.store import get_store
from backend.ucp import ucp_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = get_store(settings)
    order_limiter = RateLimiter(ORDER_LIMIT, ORDER_WINDOW_S)  # shared by MCP and UCP
    mcp = create_mcp_server(store, settings, order_limiter)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="KampungCart", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.mcp = mcp
    app.state.order_limiter = order_limiter

    app.include_router(health.router)
    app.include_router(shops.router)
    app.include_router(orders.router)

    # External agents. Both BEFORE the SPA catch-all below.
    app.router.routes.append(mcp_route(mcp, settings))
    app.include_router(ucp_router())

    app.include_router(spa_router(settings.dashboard_dist))
    return app


app = create_app()
