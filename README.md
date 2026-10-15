# KampungCart

**Make any shop AI-ready from one photo.**

AI shopping agents are becoming the new way people shop. Small shops without websites are invisible to them. KampungCart turns a menu or price-list photo into an AI-agent-ready store with built-in fraud checks and owner approval.

Built for the Google Cloud AI Builder Cup 2026 — Retail & Commerce.

## Team: Works On Cloud
- Aisha Siddiqua (Lead): agents, AI, MCP
- Bijay Pathak: infrastructure, deployment, security, deck

## Stack
Gemini · Google ADK · Cloud Run · Firestore · Cloud Storage · Secret Manager

The catalog extraction prompt was first prototyped and tested in Google AI Studio with a real Singapore home-bakery price list.

One Cloud Run container (asia-southeast1) serves the API, the MCP server, the UCP endpoints and the built dashboard. It is deployed with `gcloud run deploy --source .`, which uses Cloud Build only to build the image.

## Structure
- `agents/`: ADK + Gemini agents
- `backend/`: FastAPI APIs, MCP server, UCP endpoint
- `dashboard/`: owner dashboard
- `infra/`: deploy docs
- `docs/`: deck and architecture
- `tests/`: evaluation data

## Run locally (Windows, PowerShell)
Needs Python 3.12, [uv](https://docs.astral.sh/uv/) and Node.js. Copy `.env.example` to `.env` first.

- `.\scripts\dev.ps1`: backend on http://localhost:8000 and dashboard on http://localhost:5173 (Ctrl+C stops both)
- `.\scripts\build.ps1`: builds the dashboard into `dashboard/dist`, which FastAPI serves at `/`
- `.\scripts\test.ps1`: runs pytest (extra arguments go to pytest)

The design system lives at http://localhost:5173/styleguide.

Note: the repo path may contain `&`. npm's `.cmd` shims break on such paths, so the dashboard's
npm scripts call each tool with `node ./node_modules/...` directly. Keep that pattern when adding scripts.

## For AI agents: MCP and UCP
- MCP (streamable HTTP): `http://localhost:8000/mcp`. Tools: `find_shops`, `get_shop`,
  `search_products`, `get_quote`, `place_order`, `get_order_status`.
- UCP discovery profile: `http://localhost:8000/.well-known/ucp`. This is a partial
  implementation; [docs/architecture/UCP_IMPLEMENTATION.md](docs/architecture/UCP_IMPLEMENTATION.md)
  lists exactly what is and isn't implemented.
- Try it: `uv run python scripts/seed_demo_shop.py`, start the backend, then
  `uv run python scripts/try_mcp.py`. UCP request bodies for `curl.exe` are in `scripts/ucp/`.
- On Cloud Run, set `BASE_URL` to the service's public URL. The MCP server only accepts
  requests whose Host is localhost or the host in `BASE_URL`, and the UCP profile advertises
  `BASE_URL` as its endpoint.
