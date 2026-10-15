# UCP implementation in KampungCart

KampungCart implements a **small subset** of the Universal Commerce Protocol, enough for an AI
shopping agent to discover our shops, search the catalog, and place pay-at-pickup orders.
It is **not** a full or certified UCP implementation.

- Spec version targeted: **2026-08-25** (https://ucp.dev/2026-08-25/specification/overview/),
  read on 2026-10-15.
- Code: `backend/ucp/` (`profile.py`, `routes.py`, `convert.py`). Business logic is the shared
  `agents/commerce` service, the same one the MCP server uses, with `channel = "ucp"`.
- Tests: `tests/test_ucp.py`.

## Implemented

| Area | What we do |
|---|---|
| Discovery | `GET /.well-known/ucp` returns a business profile with `ucp.version`, `ucp.services` (one `dev.ucp.shopping` REST service with endpoint `{BASE_URL}/ucp/v1`), `ucp.capabilities` and `ucp.payment_handlers`. CORS `*` on this route only. |
| Capabilities declared | `dev.ucp.shopping.checkout`, `dev.ucp.shopping.catalog.search`, `dev.ucp.shopping.catalog.lookup`, each with `version`, `spec` and `schema` pointing to ucp.dev. |
| Catalog search | `POST /ucp/v1/catalog/search` with `query`, `filters.categories`, `pagination.limit` (1-50) and `pagination.cursor`. Returns `products` with `id`, `title`, `description.plain`, `price_range`, `variants[]` (`id`, `title`, `price {amount, currency}`, `availability`) and `pagination`. |
| Catalog lookup | `POST /ucp/v1/catalog/lookup` (`ids`, max 50, product or variant ids; unknown ids appear as `info`/`not_found` messages) and `POST /ucp/v1/catalog/product` (`id`). |
| Checkout | `POST /ucp/v1/checkout-sessions` (create, 201), `GET` / `PUT /ucp/v1/checkout-sessions/{id}` (get, full-replace update), `POST .../complete`, `POST .../cancel`. |
| Checkout object | `ucp`, `id`, `status`, `currency`, `line_items[]` (`id`, `item {id, title, price}`, `quantity`, `totals`), `totals[]` (`subtotal`, `total`), `links`, `buyer`, `messages[]`, and `order {id, permalink_url}` once completed. |
| Money | Integer minor units (cents). Prices always come from the shop's catalog via `commerce.build_quote`; any price the agent sends is ignored. |
| Statuses | `incomplete` (missing buyer name, phone or pickup time, or bad items), `ready_for_complete`, `complete_in_progress`, `completed`, `canceled`. |
| Errors | Business errors return HTTP 200 with `messages[]` (`type`, `code`, `content`, `path`, `severity`); a refused create also has `ucp.status: "error"` and no checkout. Protocol errors return `{code, content}` with 400 (bad JSON or fields), 404 (unknown checkout), 413 (body over 64 KB), 429 (rate limit, `Retry-After: 60`) and 500 (no internals). |
| Every response | Carries `ucp.version`. |

### How our order flow maps to UCP statuses

| KampungCart order status | UCP checkout status | Message |
|---|---|---|
| (no order yet) | `incomplete` / `ready_for_complete` | what is missing |
| `auto_approved`, `approved`, `ready`, `done` | `completed` + `order` | none |
| `pending_approval` (held for the owner) | `complete_in_progress` | `info` `held_for_approval`: "Held for owner approval" |
| `rejected` | `canceled` | `error` `rejected_by_shop` with the owner's reason |

The agent polls `GET /ucp/v1/checkout-sessions/{id}` to see the owner's decision.

## Not implemented

- Negotiation: we accept the `UCP-Agent` header but never fetch the platform profile or intersect
  capabilities. We always answer with version 2026-08-25. No `version_unsupported` or
  `capabilities_incompatible` handling, and no `supported_versions`.
- Signing: no `keys`, no HTTP Message Signatures (RFC 9421), no `Content-Digest` checks, no
  signed webhooks.
- `Idempotency-Key` and `Request-Id` headers are not processed. (Completing a checkout twice is
  still safe: the second call returns the same order.)
- Transports other than REST: no UCP MCP binding, A2A or embedded checkout. KampungCart's
  separate MCP server at `/mcp` uses its own tools, not the UCP OpenRPC schema.
- Extensions and other capabilities: fulfillment, discounts, buyer consent, cart, order
  webhooks, identity linking, AP2 mandates, split payments.
- Catalog: no `context`-based localisation, media, ratings, `selected`/`preferences` option
  resolution, or price filters.
- `continue_url` / `requires_escalation`: there is no buyer-facing web page to hand off to.
- Confirmation email after completion.
- Real payment of any kind.

## Deviations (KampungCart-specific)

These are things our demo needs that the spec does not define. All of them are namespaced as
`kampungcart` or `com.kampungcart.*`.

1. **One platform profile for many shops.** The spec defines a profile only at the origin root.
   We serve one profile for all shops. Catalog search spans every published shop; the
   non-standard `filters.shop` (a shop slug) narrows it. Each product carries
   `kampungcart.shop`. A checkout must contain items from one shop. Unpublished shops are
   invisible everywhere.
2. **Pay at pickup.** The spec defines no offline payment handler. We declare our own handler
   `com.kampungcart.pay_at_pickup` (id `pay_at_pickup`; schema at
   `/ucp/schemas/pay_at_pickup.json`). Complete accepts an instrument with
   `handler_id: "pay_at_pickup"`, or no `payment` at all, and refuses other handlers with
   `payment_failed`. No money moves and no payment details are collected. Our namespace
   (`com.kampungcart`) doesn't match the host serving the schema, because we have no own domain
   yet; the spec says the two must match.
3. **Pickup time, note and agent name.** The spec has no field for a buyer-requested pickup
   time. We read `kampungcart.pickup_at` (Singapore time, e.g. `2026-10-17T10:00`),
   `kampungcart.note` (max 500 characters) and `kampungcart.agent_name` from the
   create/update body. Without `agent_name`, we use the host of the `UCP-Agent` profile URL.
4. **Product options** (e.g. flavour) are sent per line as `kampungcart.options`, e.g.
   `{"Flavour": "Pandan"}`, instead of being modelled as separate variants.
5. **Variant ids**: a product with several packs has variant ids `<product id>.v<n>`. A product
   with one price has a single variant whose id is the product id.
6. **`links` is empty**: we have no terms-of-service or privacy page yet.
7. **`order.permalink_url`** points to the checkout session URL, as there is no order web page.
8. **Held orders** use `complete_in_progress` (described above), and a rejection ends as
   `canceled`.

## Security

- Request bodies are capped at 64 KB, and every field has a length limit (names 80, note 500,
  20 lines, 50 lookup ids). Unknown fields are ignored.
- Names, notes and agent names are untrusted data. They are never followed; the risk check flags
  instructions, links and payment-change requests in notes.
- `complete` is rate-limited per client: 10 orders a minute per IP (the first
  `X-Forwarded-For` hop on Cloud Run), shared with MCP `place_order`. The limit is held in
  memory per instance.
- Every UCP request writes an `external_call` audit event with `actor = external_agent` and the
  agent name. The profile, and catalog calls without a shop, are logged under
  `shop_id = "platform"`.
- Internal errors return a generic message; details go only to the server log.
