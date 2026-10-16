# KampungCart: one image that serves the API, /mcp, the UCP routes and the built dashboard.
# Built by `gcloud run deploy --source .` (Cloud Build) or locally with `docker build .`.
# See infra/README.md for the deploy steps.

# --- 1. Dashboard: React + Vite -> static files ------------------------------------------
FROM node:22-slim AS dashboard
WORKDIR /dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY dashboard/ ./
RUN npm run build

# --- 2. Python deps: resolved from uv.lock into /app/.venv ---------------------------------
FROM python:3.12-slim AS python-deps
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
# --frozen: fail instead of re-locking if uv.lock is out of date. No dev deps (pytest, httpx).
RUN uv sync --frozen --no-dev --no-install-project

# --- 3. Runtime: no uv, no node, non-root ------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8080
WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --no-create-home app

COPY --from=python-deps /app/.venv /app/.venv
COPY agents/ ./agents/
COPY backend/ ./backend/
COPY --from=dashboard /dashboard/dist ./dashboard/dist

# data/ and uploads/ are only used by STORE_BACKEND=local. On Cloud Run they live on the
# in-memory filesystem: lost on restart and not shared between instances.
RUN mkdir -p data uploads && chown app:app data uploads
USER app

EXPOSE 8080
# Cloud Run sets PORT. exec so uvicorn is PID 1 and gets SIGTERM on shutdown.
CMD ["sh", "-c", "exec uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT} --no-server-header"]
