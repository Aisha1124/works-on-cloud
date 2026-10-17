import { Mail } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { api, errorText } from '../lib/api'
import { usePoll } from '../lib/hooks'
import { formatPickup } from '../lib/time'
import type { WebOrder } from '../lib/types'
import { Button, PriceTag, ReceiptCard, ReceiptDivider, ReceiptRow, ReceiptTotal, Stamp, type StampKind } from '../ui'
import { CopyLine } from './Share'

const POLL_MS = 10_000

type View = { stamp: StampKind; label: string; title: string }

function viewOf(order: WebOrder): View {
  if (order.expired) return { stamp: 'rejected', label: 'Expired', title: "The shop didn't respond in time" }
  const views: Record<WebOrder['status'], View> = {
    confirmed: { stamp: 'approved', label: 'Confirmed', title: 'Confirmed' },
    pending_owner_approval: { stamp: 'held', label: 'Sent to owner', title: 'Sent to the owner for approval' },
    rejected: { stamp: 'rejected', label: 'Rejected', title: "The shop couldn't take this order" },
    ready: { stamp: 'approved', label: 'Ready', title: 'Ready for pickup' },
    done: { stamp: 'approved', label: 'Collected', title: 'Collected' },
    cancelled: { stamp: 'rejected', label: 'Cancelled', title: 'You cancelled this order' },
  }
  return views[order.status]
}

function optionsText(line: { variant: string | null; options: Record<string, string> }) {
  return [line.variant, ...Object.values(line.options)].filter(Boolean).join(' · ')
}

/** The status link on this site (same path and token as the emailed one). */
function linkHere(order: WebOrder, token: string): string {
  return `${window.location.origin}/o/${encodeURIComponent(order.order_id)}?t=${encodeURIComponent(token)}`
}

/** One order as its customer sees it: status stamp, plain message, receipt, the private
 *  link to come back to, and Cancel while the shop still allows it. Polls while held. */
export function OrderStatusCard({ initial, token, footer }: { initial: WebOrder; token: string; footer?: ReactNode }) {
  const [order, setOrder] = useState(initial)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const base = `/api/public/orders/${encodeURIComponent(order.order_id)}`
  const query = `?t=${encodeURIComponent(token)}`

  usePoll(
    async () => {
      setOrder(await api<WebOrder>(base + query, { owner: false }))
    },
    POLL_MS,
    order.status === 'pending_owner_approval' && !!token,
  )

  async function cancel() {
    setBusy(true)
    setError(null)
    try {
      setOrder(await api<WebOrder>(`${base}/cancel${query}`, { method: 'POST', owner: false }))
      setConfirming(false)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const view = viewOf(order)
  return (
    <ReceiptCard aria-live="polite">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <p className="font-mono text-xs tracking-widest text-muted uppercase">
            {order.shop_name} · Order {order.order_id}
          </p>
          <h2 className="text-3xl">{view.title}</h2>
        </div>
        <Stamp key={`${order.status}-${order.expired}`} kind={view.stamp} label={view.label} size="lg" animate />
      </div>
      <p className="mt-3 text-lg">{order.message}</p>
      {order.rejection_reason && <p className="mt-1 text-ink-soft">Reason from the shop: {order.rejection_reason}</p>}
      {order.status === 'pending_owner_approval' && <p className="mt-1 text-sm text-ink-soft">This page updates by itself when the owner decides.</p>}

      {token && (
        <div className="mt-4 border-2 border-ink bg-turmeric-tint p-3">
          <CopyLine label="Save this link to check your order" value={linkHere(order, token)} />
          {order.email_updates_to && (
            <p className="mt-2 flex items-center gap-2 text-sm">
              <Mail aria-hidden className="size-4 flex-none" /> We'll also email updates to {order.email_updates_to}.
            </p>
          )}
        </div>
      )}

      <ReceiptDivider />
      <ul>
        {order.items.map((l, i) => (
          <li key={i}>
            <ReceiptRow label={`${l.qty} × ${l.name}`} hint={optionsText(l) || undefined} value={<PriceTag value={l.line_total} />} />
          </li>
        ))}
      </ul>
      <div className="mt-2">
        <ReceiptTotal value={<PriceTag value={order.total} size="lg" />} />
      </div>
      <p className="mt-3 font-mono text-sm">Pickup: {formatPickup(order.pickup_time)} · pay at pickup</p>

      {order.can_cancel && token && (
        <div className="mt-4 flex flex-col gap-2">
          {confirming ? (
            <div className="flex flex-col gap-3 border-2 border-ink bg-paper p-3" role="group" aria-label="Cancel this order">
              <p className="font-semibold">Cancel this order? The shop will be told.</p>
              <div className="flex flex-wrap gap-3">
                <Button onClick={cancel} loading={busy}>
                  Yes, cancel it
                </Button>
                <Button variant="ghost" onClick={() => setConfirming(false)} disabled={busy}>
                  Keep my order
                </Button>
              </div>
            </div>
          ) : (
            <Button variant="secondary" className="self-start" onClick={() => setConfirming(true)}>
              Cancel order
            </Button>
          )}
          <p className="text-sm text-ink-soft">You can cancel until {formatPickup(order.cancel_until)}.</p>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-2 font-semibold text-chili">
          {error}
        </p>
      )}
      {footer && <div className="py-4">{footer}</div>}
    </ReceiptCard>
  )
}
