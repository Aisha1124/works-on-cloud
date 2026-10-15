import { Bot, Clock, MapPin, Phone } from 'lucide-react'
import { useEffect } from 'react'
import { useParams } from 'react-router'
import { ErrorCard } from '../components/ErrorCard'
import { MenuLines } from '../components/MenuLines'
import { api } from '../lib/api'
import { useLoad } from '../lib/hooks'
import type { Product, PublicShopPage } from '../lib/types'
import { EmptyState, ReceiptCard, ReceiptDivider, Signboard, Skeleton } from '../ui'

const NO_CATEGORY = 'More'

function group(products: Product[]) {
  const map = new Map<string, Product[]>()
  for (const p of products) {
    const c = p.category.trim() || NO_CATEGORY
    map.set(c, [...(map.get(c) ?? []), p])
  }
  return [...map.entries()]
}

/** Read-only shop page. The server also injects schema.org JSON-LD for this route. */
export function PublicShop() {
  const { slug = '' } = useParams()
  const page = useLoad((signal) => api<PublicShopPage>(`/api/public/shops/${encodeURIComponent(slug)}`, { owner: false, signal }), slug)
  const notFound = page.error && !page.data
  const shop = page.data?.shop

  useEffect(() => {
    if (shop) document.title = `${shop.name} · KampungCart`
  }, [shop])

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6 sm:py-10">
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

          {page.data.products.length === 0 ? (
            <EmptyState message="The menu is being updated. Please check back soon." />
          ) : (
            group(page.data.products).map(([category, items]) => (
              <ReceiptCard key={category} aria-labelledby={`menu-${category}`}>
                <h2 id={`menu-${category}`} className="text-center text-2xl uppercase">
                  {category}
                </h2>
                <ReceiptDivider />
                <ul className="flex flex-col gap-1">
                  {items.map((p) => (
                    <li key={p.id}>
                      <MenuLines product={p} />
                      {p.description && <p className="pb-1 text-sm text-ink-soft">{p.description}</p>}
                    </li>
                  ))}
                </ul>
                <ReceiptDivider />
                <p className="text-center font-mono text-xs text-muted">Prices in SGD · pay at pickup</p>
              </ReceiptCard>
            ))
          )}

          <footer className="flex flex-col gap-3 border-2 border-ink bg-ink p-4 text-receipt shadow-hard sm:p-5" aria-labelledby="for-agents">
            <h2 id="for-agents" className="flex items-center gap-2 text-xl text-receipt">
              <Bot aria-hidden className="size-5" /> For AI agents
            </h2>
            <p className="text-sm">This shop takes pickup orders from AI shopping agents.</p>
            <dl className="grid gap-2 font-mono text-sm sm:grid-cols-[auto_1fr] sm:gap-x-4">
              <dt className="text-turmeric">UCP profile</dt>
              <dd className="break-all">
                <a className="underline focus-visible:text-ink" href={page.data.links.ucp_profile}>
                  {page.data.links.ucp_profile}
                </a>
              </dd>
              <dt className="text-turmeric">MCP endpoint</dt>
              <dd className="break-all">{page.data.links.mcp}</dd>
            </dl>
          </footer>
        </>
      )}
    </main>
  )
}
