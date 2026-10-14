"""FastAPI app: REST API, (later) /mcp and UCP routes, and the built dashboard."""

from fastapi import FastAPI

from backend.api.config import Settings, get_settings
from backend.api.routes import health, shops
from backend.api.spa import spa_router
from backend.store import get_store


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="KampungCart", version="0.1.0")
    app.state.settings = settings
    app.state.store = get_store(settings)

    app.include_router(health.router)
    app.include_router(shops.router)

    # Later: mount the MCP server at /mcp and include the UCP router (/.well-known/ucp)
    # here, BEFORE the SPA catch-all below.

    app.include_router(spa_router(settings.dashboard_dist))
    return app


app = create_app()
