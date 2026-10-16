import { Check, Phone, X } from 'lucide-react'
import { useRef, useState, type FormEvent } from 'react'
import { ErrorCard } from '../components/ErrorCard'
import { api, errorText } from '../lib/api'
import { usePoll } from '../lib/hooks'
import { useShop } from '../lib/shop'
import { formatPickup, formatStamp } from '../lib/time'
import type { Order, OrderStatus } from '../lib/types'
import {
  Button,
  EmptyState,
  PriceTag,
  ReceiptCard,
  ReceiptDivider,
  ReceiptRow,
  ReceiptTotal,
  RiskMeter,
  Skeleton,
  Stamp,
  Textarea,
  cx,
  formatSGD,
  type StampKind,
} from '../ui'

const POLL_MS = 3000
const channelLabel = { mcp: 'MCP', ucp: 'UCP', dashboard: 'Dashboard', web: 'Shop page' } as const
const stampFor: Record<OrderStatus, { kind: StampKind; label: string }> = {
  auto_approved: { kind: 'approved', label: 'Auto-approved' },
  approved: { kind: 'approved', label: 'Approved' },
  pending_approval: { kind: 'held', label: 'Held' },
  rejected: { kind: 'rejected', label: 'Rejected' },
  ready: { kind: 'approved', label: 'Ready' },
  done: { kind: 'approved', label: 'Done' },
}

function OrderCard({
  shopId,
  order,
  fresh,
  justDecided,
  onDecided,
}: {
  shopId: string
  order: Order
  fresh: boolean
  justDecided: boolean
  onDecided: (o: Order) => void
}) {
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const held = order.status === 'pending_approval'
  const stamp = stampFor[order.status]

  async function decide(action: 'approve' | 'reject', e?: FormEvent) {
    e?.preventDefault()
    if (action === 'reject' && !reason.trim()) {
      setError('Add a short reason. The customer’s agent will see it.')
      return
    }
    setBusy(action)
    setError(null)
    try {
      const updated = await api<Order>(`/api/shops/${shopId}/orders/${order.id}/${action}`, {
        method: 'POST',
        json: action === 'reject' ? { reason: reason.trim() } : undefined,
      })
      onDecided(updated)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <li className={cx(fresh && 'slide-in')}>
      <ReceiptCard aria-labelledby={`order-${order.id}`} className="relative">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 id={`order-${order.id}`} className="font-mono text-base font-semibold">
              #{order.id.slice(0, 6).toUpperCase()}
            </h3>
            <p className="font-mono text-xs text-muted">{formatStamp(order.created_at)} SGT</p>
          </div>
          <Stamp key={order.status} kind={stamp.kind} label={stamp.label} />
        </div>

        <p className="mt-2 text-sm font-semibold">
          via {channelLabel[order.channel]}
          {order.agent_name && <> · {order.agent_name}</>}
        </p>

        <ReceiptDivider />
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-muted">Customer</dt>
          <dd className="min-w-0 break-words font-semibold">{order.customer_name}</dd>
          <dt className="text-muted">Phone</dt>
          <dd className="font-mono">
            <a className="focus-ring inline-flex items-center gap-1 underline" href={`tel:${order.customer_phone.replace(/[^\d+]/g, '')}`}>
              <Phone aria-hidden className="size-3.5" />
              {order.customer_phone}
            </a>
          </dd>
          <dt className="text-muted">Pickup</dt>
          <dd className="font-mono font-semibold">{formatPickup(order.pickup_at)}</dd>
        </dl>

        <ReceiptDivider />
        <ul>
          {order.items.map((it, i) => (
            <li key={i}>
              <ReceiptRow
                label={
                  <>
                    <span className="font-mono">{it.qty} ×</span> {it.name}
                  </>
                }
                hint={[it.variant, ...Object.entries(it.options).map(([k, v]) => `${k}: ${v}`), it.request && `Request: “${it.request}”`].filter(Boolean).join(' · ') || undefined}
                value={<PriceTag value={it.line_total} />}
              />
            </li>
          ))}
          {order.unpriced_requests?.map((u, i) => (
            <li key={`unpriced-${i}`}>
              <ReceiptRow
                label={
                  <>
                    <span className="font-mono">{u.qty} ×</span> {u.name}
                  </>
                }
                hint={['Not on the menu', u.request && `Request: “${u.request}”`].filter(Boolean).join(' · ')}
                value={<span className="font-semibold text-chili">PRICE TBC</span>}
              />
            </li>
          ))}
        </ul>
        <ReceiptTotal label={order.unpriced_requests?.length ? 'TOTAL (menu items)' : undefined} value={formatSGD(order.total)} />
        {order.review_reasons && order.review_reasons.length > 0 && (
          <div className="mt-3 border-2 border-ink bg-turmeric-tint p-3 text-sm">
            <p className="font-mono text-xs tracking-widest uppercase">Needs your check</p>
            <ul className="list-[square] pl-5">
              {order.review_reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        )}

        {order.note && (
          <div className="mt-3 border-l-4 border-ink pl-3 text-sm">
            <p className="font-mono text-xs tracking-widest text-muted uppercase">Customer note</p>
            <p className="break-words">“{order.note}”</p>
          </div>
        )}

        <div className="mt-4 flex flex-col gap-3">
          <RiskMeter score={order.risk ? order.risk.score : null} level={order.risk?.level} />
          {order.risk && order.risk.reasons.length > 0 && (
            <ul className="list-[square] pl-5 text-sm">
              {order.risk.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          {/* Until the risk agent's sentence arrives, the explanation is just the reasons again. */}
          {order.risk?.explanation && order.risk.explanation !== order.risk.reasons.join('; ') && <p className="border-2 border-dashed border-ink bg-paper p-3 text-sm">{order.risk.explanation}</p>}
        </div>

        {order.status === 'rejected' && order.rejection_reason && (
          <p className="mt-3 text-sm">
            <span className="font-semibold">Reason given:</span> {order.rejection_reason}
          </p>
        )}

        {justDecided && !held && (
          <div className="mt-5 flex justify-center pb-2" role="status">
            <Stamp kind={stamp.kind} label={stamp.label} size="lg" animate />
          </div>
        )}

        {held && (
          <div className="mt-4 flex flex-col gap-3">
            {rejecting ? (
              <form onSubmit={(e) => decide('reject', e)} className="flex flex-col gap-3" noValidate>
                <Textarea
                  label="Short reason for the customer"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={200}
                  rows={2}
                  placeholder="Sorry, we can't make 400 pieces by tomorrow."
                  autoFocus
                />
                <div className="flex flex-wrap gap-3">
                  <Button type="submit" size="lg" loading={busy === 'reject'} icon={<X aria-hidden className="size-5" />}>
                    Reject order
                  </Button>
                  <Button variant="ghost" onClick={() => setRejecting(false)} disabled={!!busy}>
                    Back
                  </Button>
                </div>
              </form>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <Button
                  variant="approve"
                  size="lg"
                  loading={busy === 'approve'}
                  disabled={!!busy}
                  icon={<Check aria-hidden className="size-5" />}
                  onClick={() => decide('approve')}
                >
                  Approve
                </Button>
                <Button size="lg" disabled={!!busy} icon={<X aria-hidden className="size-5" />} onClick={() => setRejecting(true)}>
                  Reject
                </Button>
              </div>
            )}
            {error && (
              <p role="alert" className="border-2 border-ink border-l-8 border-l-chili bg-receipt px-3 py-2 text-sm font-semibold">
                {error}
              </p>
            )}
          </div>
        )}
      </ReceiptCard>
    </li>
  )
}

export function Orders() {
  const { shopId } = useShop()
  const [orders, setOrders] = useState<Order[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'held' | 'all'>('held')
  const [announce, setAnnounce] = useState('')
  const [decided, setDecided] = useState<Set<string>>(new Set())
  const seen = useRef<Set<string> | null>(null)
  const [fresh, setFresh] = useState<Set<string>>(new Set())

  usePoll(async () => {
    try {
      const list = await api<Order[]>(`/api/shops/${shopId}/orders`)
      if (seen.current) {
        const added = list.filter((o) => !seen.current!.has(o.id))
        if (added.length) {
          setFresh(new Set(added.map((o) => o.id)))
          const heldCount = added.filter((o) => o.status === 'pending_approval').length
          setAnnounce(
            `${added.length} new order${added.length === 1 ? '' : 's'}` + (heldCount ? `, ${heldCount} waiting for your approval.` : '.'),
          )
        }
      }
      seen.current = new Set(list.map((o) => o.id))
      setOrders(list)
      setError(null)
    } catch (err) {
      setError(errorText(err))
    }
  }, POLL_MS)

  const held = orders?.filter((o) => o.status === 'pending_approval') ?? []
  // Orders decided here stay on the "Needs approval" tab so the owner sees the stamp land.
  const shown = tab === 'held' ? (orders?.filter((o) => o.status === 'pending_approval' || decided.has(o.id)) ?? []) : (orders ?? [])

  function onDecided(o: Order) {
    setOrders((list) => list?.map((x) => (x.id === o.id ? o : x)) ?? list)
    setDecided((s) => new Set(s).add(o.id))
  }

  const tabs = [
    { id: 'held' as const, label: 'Needs approval', count: held.length },
    { id: 'all' as const, label: 'All orders', count: orders?.length ?? 0 },
  ]

  return (
    <section aria-labelledby="orders-heading" className="flex flex-col gap-5">
      <h2 id="orders-heading" className="sr-only">
        Orders
      </h2>
      <p aria-live="polite" role="status" className="sr-only">
        {announce}
      </p>

      <div role="tablist" aria-label="Orders" className="flex flex-wrap gap-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls="orders-panel"
            onClick={() => setTab(t.id)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                const next = t.id === 'held' ? 'all' : 'held'
                setTab(next)
                document.getElementById(`tab-${next}`)?.focus()
              }
            }}
            tabIndex={tab === t.id ? 0 : -1}
            className={cx(
              'focus-ring inline-flex min-h-11 items-center gap-2 border-2 border-ink px-3 text-sm font-semibold sm:px-4 sm:text-base',
              tab === t.id ? 'bg-ink text-receipt' : 'bg-receipt shadow-hard-sm hover:bg-turmeric-tint',
            )}
          >
            {t.label}
            <span
              className={cx(
                'min-w-7 border-2 px-1.5 text-center font-mono text-sm',
                t.id === 'held' && t.count > 0 ? 'border-ink bg-turmeric text-ink' : 'border-current',
              )}
            >
              {t.count}
            </span>
          </button>
        ))}
        <p className="hidden self-center font-mono text-xs text-ink-soft sm:ml-auto sm:block">Checks for new orders every 3 seconds</p>
      </div>

      <div id="orders-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {error && !orders ? (
          <ErrorCard message={error} />
        ) : !orders ? (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Skeleton rows={6} label="Loading orders" />
            <Skeleton rows={6} label="Loading orders" className="hidden lg:block" />
          </div>
        ) : shown.length === 0 ? (
          <EmptyState
            message={
              tab === 'held'
                ? 'Nothing waiting for you. Low-risk orders go through on their own.'
                : 'No orders yet. When an AI agent orders, it prints here.'
            }
          />
        ) : (
          <>
            {error && <ErrorCard className="mb-4" message={`${error} Showing the last orders we loaded.`} />}
            <ul className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:items-start">
              {shown.map((o) => (
                <OrderCard key={o.id} shopId={shopId} order={o} fresh={fresh.has(o.id)} justDecided={decided.has(o.id)} onDecided={onDecided} />
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  )
}
