import { ArrowDown, ArrowRight, Bot, Clock, MapPin, PauseCircle, Phone } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ErrorCard } from '../components/ErrorCard'
import { MenuLines } from '../components/MenuLines'
import { ReportShop } from '../components/ReportShop'
import { AddToOrder, Checkout, OrderResult } from '../components/ShopOrder'
import { api } from '../lib/api'
import { addLine, useCartQuote } from '../lib/cart'
import { useLoad } from '../lib/hooks'
import type { CartLine, Product, PublicShopPage, WebOrder } from '../lib/types'
import { EmptyState, PriceTag, ReceiptCard, ReceiptDivider, Signboard, Skeleton, Stamp, buttonClass, useToast } from '../ui'

const NO_CATEGORY = 'More'

function group(products: Product[]) {
  const map = new Map<string, Product[]>()
  for (const p of products) {
    const c = p.category.trim() || NO_CATEGORY
    map.set(c, [...(map.get(c) ?? []), p])
  }
  return [...map.entries()]
}

/** One sentence a customer could type to their AI assistant, using a real item from this menu. */
function exampleAsk(slug: string, products: Product[]): string {
  const item = products.find((p) => p.available)?.name ?? 'your favourite item'
  return `Order 2 boxes of ${item} from ${slug} for Saturday 10am pickup.`
}

// The last order placed from this tab, so a reload still shows its status.
const lastOrderKey = (slug: string) => `kampungcart.lastOrder.${slug}`
function loadLastOrder(slug: string): WebOrder | null {
  try {
    const raw = sessionStorage.getItem(lastOrderKey(slug))
    return raw ? (JSON.parse(raw) as WebOrder) : null
  } catch {
    return null
  }
}
function saveLastOrder(slug: string, order: WebOrder | null) {
  try {
    if (order) sessionStorage.setItem(lastOrderKey(slug), JSON.stringify(order))
    else sessionStorage.removeItem(lastOrderKey(slug))
  } catch {
    // not kept across reloads; fine
  }
}

/** The customer's shop page: menu with prices, add items, pick a pickup time, order.
 *  No key and no signup. The server also injects schema.org JSON-LD for this route. */
export function PublicShop() {
  const { slug = '' } = useParams()
  const page = useLoad((signal) => api<PublicShopPage>(`/api/public/shops/${encodeURIComponent(slug)}`, { owner: false, signal }), slug)
  const notFound = page.error && !page.data
  const shop = page.data?.shop
  const toast = useToast()
  const [cart, setCart] = useState<CartLine[]>([])
  const [placed, setPlaced] = useState<WebOrder | null>(() => loadLastOrder(slug))
  const { quote, error: quoteError } = useCartQuote(slug, cart)
  const count = cart.reduce((n, l) => n + l.qty, 0)
  const paused = !!shop?.ordering_message

  useEffect(() => {
    if (shop) document.title = `${shop.name} · KampungCart`
  }, [shop])

  function add(line: CartLine) {
    setCart((c) => addLine(c, line))
    const name = page.data?.products.find((p) => p.id === line.product_id)?.name ?? 'Item'
    toast.show(`Added ${line.qty} × ${name}.`, 'success')
  }

  function onPlaced(order: WebOrder) {
    saveLastOrder(slug, order)
    setPlaced(order)
    setCart([])
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function newOrder() {
    saveLastOrder(slug, null)
    setPlaced(null)
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 pt-6 pb-32 sm:pt-10">
      {notFound ? (
        page.errorStatus === 404 ? (
          <EmptyState message="This shop isn't open on KampungCart yet. Check the link, or ask the shop for a new one." />
        ) : (
          <ErrorCard message={page.error} onRetry={page.reload} />
        )
      ) : !page.data || !shop ? (
        <Skeleton rows={6} label="Loading the menu" />
      ) : (
        <>
          {shop.example && (
            <p className="flex flex-wrap items-center gap-3 text-sm text-ink-soft">
              <Stamp kind="check" label="Example shop" size="sm" />
              <span>A sample menu to try KampungCart. It is not a real business.</span>
            </p>
          )}
          <Signboard title={shop.name} subtitle={shop.tagline || undefined} plate={shop.shop_type || 'KampungCart shop'} />

          {(shop.hours || shop.address || shop.phone) && (
            <ul className="flex flex-col gap-2 border-2 border-ink bg-receipt p-4 shadow-hard-sm sm:flex-row sm:flex-wrap sm:gap-x-6">
              {shop.hours && (
                <li className="flex items-center gap-2">
                  <Clock aria-hidden className="size-4 flex-none" />
                  <span className="sr-only">Hours: </span>
                  {shop.hours}
                </li>
              )}
              {shop.address && (
                <li className="flex items-center gap-2">
                  <MapPin aria-hidden className="size-4 flex-none" />
                  <span className="sr-only">Address: </span>
                  {shop.address}
                </li>
              )}
              {shop.phone && (
                <li className="flex items-center gap-2">
                  <Phone aria-hidden className="size-4 flex-none" />
                  <a className="focus-ring font-mono underline" href={`tel:${shop.phone.replace(/[^\d+]/g, '')}`}>
                    {shop.phone}
                  </a>
                </li>
              )}
            </ul>
          )}

          {shop.ordering_message && (
            <p role="status" className="flex items-center gap-3 border-2 border-ink bg-turmeric p-4 text-lg font-semibold shadow-hard-sm">
              <PauseCircle aria-hidden className="size-6 flex-none" />
              {shop.ordering_message}
            </p>
          )}

          {placed && <OrderResult key={placed.order_id} initial={placed} onNewOrder={newOrder} />}

          {page.data.products.length === 0 ? (
            <EmptyState message="The menu is being updated. Please check back soon." />
          ) : (
            group(page.data.products).map(([category, items]) => (
              <ReceiptCard key={category} aria-labelledby={`menu-${category}`}>
                <h2 id={`menu-${category}`} className="text-center text-2xl uppercase">
                  {category}
                </h2>
                <ReceiptDivider />
                <ul className="flex flex-col gap-3">
                  {items.map((p) => (
                    <li key={p.id} className="flex flex-col gap-1.5">
                      <MenuLines product={p} />
                      {p.description && <p className="text-sm text-ink-soft">{p.description}</p>}
                      {!paused && (
                        <div className="flex justify-end">
                          <AddToOrder product={p} onAdd={add} />
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
                <ReceiptDivider />
                <p className="pb-4 text-center font-mono text-xs text-muted">Prices in SGD · pay at pickup</p>
              </ReceiptCard>
            ))
          )}

          {cart.length > 0 && !paused && (
            <Checkout
              slug={slug}
              products={page.data.products}
              cart={cart}
              setCart={setCart}
              quote={quote}
              quoteError={quoteError}
              onPlaced={onPlaced}
            />
          )}

          <section className="flex flex-col gap-2 border-2 border-ink bg-ink p-4 text-receipt shadow-hard sm:p-5" aria-labelledby="ai-order">
            <h2 id="ai-order" className="flex items-start gap-2 text-xl text-receipt">
              <Bot aria-hidden className="mt-1 size-5 flex-none" /> Ask your AI assistant about this shop
            </h2>
            <p>Share this page's link with ChatGPT, Gemini or Claude to ask about the menu, prices and opening hours.</p>
            <p className="text-sm">
              AI apps that support MCP can also place pickup orders: add{' '}
              <code className="font-mono break-all text-turmeric">{page.data.links.mcp}</code> as a connector.
            </p>
            <p className="text-sm">
              <span className="text-turmeric">Try:</span> <q>{exampleAsk(shop.slug, page.data.products)}</q>
            </p>
          </section>

          {cart.length > 0 && !paused && (
            <div className="fixed inset-x-0 bottom-0 z-40 border-t-2 border-ink bg-receipt">
              <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-3">
                <p className="font-mono text-sm">
                  <span className="font-semibold">
                    {count} {count === 1 ? 'item' : 'items'}
                  </span>
                  {quote && (
                    <>
                      {' · '}
                      <PriceTag value={quote.total} />
                    </>
                  )}
                </p>
                <a href="#checkout" className={buttonClass('primary', 'md')}>
                  Review order <ArrowDown aria-hidden className="size-4" />
                </a>
              </div>
            </div>
          )}
        </>
      )}

      <footer className="border-t-2 border-dashed border-ink pt-4 text-center text-sm text-ink-soft">
        Shop page made with <span className="font-semibold text-ink">KampungCart</span> ·{' '}
        <Link to="/" className="focus-ring inline-flex items-center gap-1 font-semibold text-ink underline underline-offset-4">
          Make one for your shop <ArrowRight aria-hidden className="size-4" />
        </Link>{' '}
        ·{' '}
        <Link to="/privacy" className="focus-ring font-semibold text-ink underline underline-offset-4">
          Privacy
        </Link>
        {shop && (
          <div className="mt-3">
            <ReportShop slug={shop.slug} shopName={shop.name} />
          </div>
        )}
      </footer>
    </main>
  )
}
