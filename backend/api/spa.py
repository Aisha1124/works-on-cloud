"""Serve the built dashboard (dashboard/dist) with SPA fallback."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

# Owned by the REST API, the MCP server and the UCP routes. Never falls back to index.html.
RESERVED_PREFIXES = ("api", "mcp", "ucp", ".well-known")


def spa_router(dist_dir: Path) -> APIRouter:
    router = APIRouter()
    dist = Path(dist_dir).resolve()

    @router.get("/{path:path}", include_in_schema=False)
    def serve(path: str):
        first = path.split("/", 1)[0]
        if first in RESERVED_PREFIXES:
            raise HTTPException(status_code=404, detail="Not found")

        index = dist / "index.html"
        if not index.is_file():
            return PlainTextResponse(
                "Dashboard not built yet. Run scripts/build.ps1, "
                "or run scripts/dev.ps1 and open http://localhost:5173.",
                status_code=503,
            )

        if path:
            candidate = (dist / path).resolve()
            if candidate.is_relative_to(dist) and candidate.is_file():
                return FileResponse(candidate)
            # A missing asset is a real 404, not the app shell.
            if first == "assets":
                raise HTTPException(status_code=404, detail="Not found")

        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return router
