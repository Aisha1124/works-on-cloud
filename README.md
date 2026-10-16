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

## Connect an AI agent
Every published shop can be used by any AI agent that speaks MCP (Claude, Gemini, ChatGPT with
MCP support) through one MCP server, using the streamable HTTP transport:

- Local: `http://localhost:8000/mcp`
- Cloud Run: `https://<your-service-url>/mcp`. Set `BASE_URL` to the service's public URL. The
  server only accepts requests whose Host is localhost or the host in `BASE_URL`.

### Tools
| Tool | What it does |
|---|---|
| `find_shops(query?)` | Lists published shops and their `shop_slug`. |
| `get_shop(shop_slug)` | Address, opening hours, phone and categories. |
| `get_menu(shop_slug, query?, category?)` | Items with price in SGD, category, availability, notes, sizes and options. |
| `get_quote(shop_slug, items, pickup_time?)` | Line items and subtotal priced from the menu, plus `needs_owner_approval` and the reasons. |
| `place_pickup_order(shop_slug, items, pickup_time, customer_name, customer_phone, note?)` | Returns `order_id` and a status of `confirmed` or `pending_owner_approval`. |
| `get_order_status(order_id)` | `confirmed`, `pending_owner_approval`, `rejected`, `ready` or `done`. |

An item is `{"name": "Kuih Lapis", "qty": 2, "variant": "20 pcs"}`. You can also send
`product_id`, `options` and a `request`. Prices always come from the shop's stored menu. A price
sent by an agent is ignored.

An order is held as `pending_owner_approval` until the owner approves it in the dashboard when:
- an item is not on the menu (it has no price until the owner sets one);
- a line has a custom request;
- a quantity is more than 3 times the item's largest pack;
- the total is above the shop's auto-approve limit;
- the pickup time is outside opening hours;
- the risk check scores the order medium or high.

The read tools are public. `place_pickup_order` is limited to 10 orders a minute per client IP.

### Claude Desktop
**Deployed server (HTTPS):** in Claude Desktop, open Settings → Connectors → Add custom
connector, then paste `https://<your-service-url>/mcp`.

**Local server:** `claude_desktop_config.json` starts local (stdio) servers, so bridge to the
HTTP endpoint with [`mcp-remote`](https://github.com/geelen/mcp-remote), which needs Node.js.
On Windows, the file is at `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kampungcart": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8000/mcp",
               "--transport", "http-only", "--allow-http"]
    }
  }
}
```

Restart Claude Desktop, then ask something like: "Find a kuih shop on KampungCart and quote
3 boxes of kuih lapis, 20 pcs, for Saturday 10am pickup."

### Try it from a script
Run `uv run python scripts/seed_demo_shop.py`, start the backend, then run
`uv run python scripts/try_mcp.py`. The script places a normal order, an order with an item
that is not on the menu, and a risky order.

### UCP
The UCP discovery profile is at `http://localhost:8000/.well-known/ucp`. This is a partial
implementation; [docs/architecture/UCP_IMPLEMENTATION.md](docs/architecture/UCP_IMPLEMENTATION.md)
lists exactly what is and isn't implemented. UCP request bodies for `curl.exe` are in
`scripts/ucp/`. The profile advertises `BASE_URL` as its endpoint.
