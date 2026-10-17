# KampungCart: one Cloud Run container serving the API, /mcp, the UCP routes and the dashboard.
# Build and deploy: gcloud run deploy --source .   (Cloud Build builds this file)
# No secrets are baked in. GEMINI_API_KEY and OWNER_KEY come from Secret Manager at runtime.

# --- 1. Dashboard ------------------------------------------------------------------------
FROM node:24-slim AS dashboard
WORKDIR /dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build

# --- 2. App ------------------------------------------------------------------------------
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY agents/ agents/
COPY backend/ backend/
COPY scripts/seed_shop.py scripts/seed_shop.py
COPY --from=dashboard /dashboard/dist dashboard/dist

# With STORE_BACKEND=firestore (production) all data lives in Firestore and survives restarts
# and redeploys. With STORE_BACKEND=local, data goes to /app/data, which on Cloud Run is the
# in-memory filesystem and is wiped on every restart.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p data uploads \
    && chown -R app:app data uploads
USER app

# Cloud Run's front end sets X-Forwarded-For/Proto; trust it (read by uvicorn).
ENV PORT=8080 \
    FORWARDED_ALLOW_IPS="*"
EXPOSE 8080
# The sample shop is created only if it doesn't exist yet, so a redeploy never overwrites it.
CMD ["sh", "-c", "python scripts/seed_shop.py && exec uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
