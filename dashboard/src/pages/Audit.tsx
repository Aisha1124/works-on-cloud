import { RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { ErrorCard } from '../components/ErrorCard'
import { api, errorText } from '../lib/api'
import { useLoad } from '../lib/hooks'
import { useShop } from '../lib/shop'
import type { AuditEvent, AuditPage } from '../lib/types'
import { Button, EmptyState, ReceiptCard, Skeleton, TimelineRow, cx, type Actor } from '../ui'

const PAGE = 50
const actors: { id: Actor | 'all'; label: string }[] = [
  { id: 'all', label: 'Everyone' },
  { id: 'owner', label: 'Owner' },
  { id: 'catalog_agent', label: 'Catalog agent' },
  { id: 'risk_agent', label: 'Risk agent' },
  { id: 'shopper_agent', label: 'Shopper agent' },
  { id: 'external_agent', label: 'External agent' },
  { id: 'customer', label: 'Customer' },
  { id: 'system', label: 'System' },
]

function Details({ event }: { event: AuditEvent }) {
  const hasDetails = Object.keys(event.details).length > 0
  return (
    <div className="flex flex-col gap-2 font-mono text-xs">
      <p>
        <span className="text-muted">{event.entity_type}</span> {event.entity_id}
      </p>
      {hasDetails && <pre className="max-h-80 overflow-auto break-words whitespace-pre-wrap">{JSON.stringify(event.details, null, 2)}</pre>}
    </div>
  )
}

export function Audit() {
  const { shopId } = useShop()
  const [filter, setFilter] = useState<Actor | 'all'>('all')
  const [more, setMore] = useState<AuditEvent[]>([])
  const [hasMore, setHasMore] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState<string | null>(null)

  const first = useLoad(async (signal) => {
    const page = await api<AuditPage>(`/api/shops/${shopId}/audit?limit=${PAGE}`, { signal })
    setMore([])
    setHasMore(page.events.length === PAGE)
    return page.events
  }, shopId)

  const events = [...(first.data ?? []), ...more]
  const shown = filter === 'all' ? events : events.filter((e) => e.actor === filter)

  async function loadMore() {
    setLoadingMore(true)
    setMoreError(null)
    try {
      const page = await api<AuditPage>(`/api/shops/${shopId}/audit?limit=${PAGE}&offset=${events.length}`)
      setMore((m) => [...m, ...page.events])
      setHasMore(page.events.length === PAGE)
    } catch (err) {
      setMoreError(errorText(err))
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <section aria-labelledby="audit-heading" className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="audit-heading" className="text-3xl">
            Audit log
          </h2>
          <p className="text-ink-soft">Every step, newest first, and who did it. Tap a line for details.</p>
        </div>
        <Button variant="secondary" size="sm" icon={<RefreshCw aria-hidden className="size-4" />} onClick={first.reload} loading={first.loading && !!first.data}>
          Refresh
        </Button>
      </div>

      <div role="group" aria-label="Filter by who did it" className="flex flex-wrap gap-2">
        {actors.map((a) => (
          <button
            key={a.id}
            type="button"
            aria-pressed={filter === a.id}
            onClick={() => setFilter(a.id)}
            className={cx(
              'focus-ring min-h-10 border-2 border-ink px-3 text-sm font-semibold',
              filter === a.id ? 'bg-ink text-receipt' : 'bg-receipt shadow-hard-sm hover:bg-turmeric-tint',
            )}
          >
            {a.label}
          </button>
        ))}
      </div>

      {first.error && !first.data ? (
        <ErrorCard message={first.error} onRetry={first.reload} />
      ) : !first.data ? (
        <Skeleton rows={8} label="Loading the audit log" />
      ) : shown.length === 0 ? (
        <EmptyState message={events.length ? 'Nothing from them yet.' : 'Nothing logged yet.'} />
      ) : (
        <ReceiptCard>
          <ol aria-label="Audit events">
            {shown.map((e, i) => (
              <TimelineRow
                key={e.id}
                at={e.at}
                actor={e.actor}
                action={e.action}
                summary={e.summary}
                details={<Details event={e} />}
                last={i === shown.length - 1}
              />
            ))}
          </ol>
        </ReceiptCard>
      )}

      {first.data && hasMore && (
        <div className="flex flex-col items-start gap-2">
          <Button variant="secondary" onClick={loadMore} loading={loadingMore}>
            Load older events
          </Button>
          {moreError && <p role="alert" className="font-semibold">{moreError}</p>}
        </div>
      )}
    </section>
  )
}
