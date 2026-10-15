from urllib.parse import urlsplit

from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Route

from backend.api.config import Settings
from backend.mcp_server.server import create_mcp_server

__all__ = ["create_mcp_server", "mcp_route"]

MCP_PATH = "/mcp"


def transport_security(settings: Settings) -> TransportSecuritySettings:
    """DNS-rebinding protection: only localhost and the public host from BASE_URL."""
    hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    public = urlsplit(settings.base_url).hostname
    if public and public not in hosts:
        hosts += [public, f"{public}:*"]
    return TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=[])


def mcp_route(mcp, settings: Settings) -> Route:
    """POST/GET/DELETE /mcp, served by the MCP app without a /mcp -> /mcp/ redirect.

    Stateless + JSON responses: any Cloud Run instance can answer any request. The session
    manager is started in the FastAPI lifespan (mounted apps don't get their own lifespan).
    """
    asgi = mcp.streamable_http_app(
        streamable_http_path=MCP_PATH, stateless_http=True, json_response=True,
        max_request_body_size=64 * 1024, transport_security=transport_security(settings),
    )
    return Route(MCP_PATH, endpoint=asgi)
