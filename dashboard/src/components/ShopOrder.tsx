import { Minus, Plus, ShoppingBag, Trash2, X } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { ApiError, api, errorText } from '../lib/api'
import { usePoll } from '../lib/hooks'
import { formatPickup } from '../lib/time'
import { lineKey } from '../lib/cart'
import type { CartLine, PricedLine, Product, WebOrder, WebQuote } from '../lib/types'
import { Button, Input, PriceTag, ReceiptCard, ReceiptDivider, ReceiptRow, ReceiptTotal, Select, Stamp, Textarea } from '../ui'

/* ------------------------------------------------------------------ cart */

function optionsText(line: { variant: string | null; options: Record<string, string> }) {
  return [line.variant, ...Object.values(line.options)].filter(Boolean).join(' · ')
}

/* ------------------------------------------------------------------ add one item */

/** "Add" on a menu item. Items with packs or options open a small picker first. */
export function AddToOrder({ product, onAdd }: { product: Product; onAdd: (line: CartLine) => void }) {
  const needsChoice = product.variants.length > 1 || product.options.some((o) => o.choices.length)
  const [open, setOpen] = useState(false)
  const [variant, setVariant] = useState(product.variants[0]?.label ?? '')
  const [options, setOptions] = useState<Record<string, string>>(() =>
    Object.fromEntries(product.options.filter((o) => o.choices.length).map((o) => [o.name, o.choices[0]])),
  )
  const [qty, setQty] = useState(1)

  function add() {
    onAdd({ product_id: product.id, variant: product.variants.length ? variant : null, options, qty })
    setOpen(false)
    setQty(1)
  }

  if (!product.available) return null
  if (!needsChoice || !open) {
    return (
      <Button
        size="sm"
        variant="secondary"
        icon={<Plus aria-hidden className="size-4" />}
        onClick={() => (needsChoice ? setOpen(true) : add())}
        aria-label={`Add ${product.name}`}
      >
        Add
      </Button>
    )
  }
  return (
    <div className="flex w-full flex-col gap-3 border-2 border-ink bg-paper p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="font-semibold">{product.name}</p>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)} aria-label="Close" icon={<X aria-hidden className="size-4" />} />
      </div>
      {product.variants.length > 1 && (
        <Select label="Pack or size" value={variant} onChange={(e) => setVariant(e.target.value)}>
          {product.variants.map((v) => (
            <option key={v.label} value={v.label}>
              {v.label} · S${v.price}
            </option>
          ))}
        </Select>
      )}
      {product.options
        .filter((o) => o.choices.length)
        .map((o) => (
          <Select key={o.name} label={o.name} value={options[o.name]} onChange={(e) => setOptions({ ...options, [o.name]: e.target.value })}>
            {o.choices.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </Select>
        ))}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <QtyStepper qty={qty} onChange={setQty} label={`How many ${product.name}`} />
        <Button onClick={add} icon={<Plus aria-hidden className="size-4" />}>
          Add to order
        </Button>
      </div>
    </div>
  )
}

function QtyStepper({ qty, onChange, label }: { qty: number; onChange: (n: number) => void; label: string }) {
  return (
    <div className="flex items-center" role="group" aria-label={label}>
      <Button size="sm" variant="secondary" onClick={() => onChange(Math.max(1, qty - 1))} aria-label="One less" icon={<Minus aria-hidden className="size-4" />} />
      <span className="min-w-10 text-center font-mono text-lg tabular-nums" aria-live="polite">
        {qty}
      </span>
      <Button size="sm" variant="secondary" onClick={() => onChange(Math.min(500, qty + 1))} aria-label="One more" icon={<Plus aria-hidden className="size-4" />} />
    </div>
  )
}

/* ------------------------------------------------------------------ checkout */

function minPickup(): string {
  const d = new Date(Date.now() + 60 * 60 * 1000)
  d.setSeconds(0, 0)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function Checkout({
  slug,
  products,
  cart,
  setCart,
  quote,
  quoteError,
  onPlaced,
}: {
  slug: string
  products: Product[]
  cart: CartLine[]
  setCart: (c: CartLine[]) => void
  quote: WebQuote | null
  quoteError: string | null
  onPlaced: (o: WebOrder) => void
}) {
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [pickup, setPickup] = useState('')
  const [note, setNote] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const headingId = useId()
  const byId = new Map(products.map((p) => [p.id, p]))

  async function submit(e: FormEvent) {
    e.preventDefault()
    const errs: Record<string, string> = {}
    if (!name.trim()) errs.name = 'Your name, so the shop knows who is picking up.'
    if (!phone.trim()) errs.phone = 'A Singapore phone number, in case the shop needs to reach you.'
    if (!pickup) errs.pickup = 'Pick a date and time to collect your order.'
    setErrors(errs)
    if (Object.keys(errs).length) return
    setBusy(true)
    setFormError(null)
    try {
      const order = await api<WebOrder>(`/api/public/shops/${encodeURIComponent(slug)}/orders`, {
        method: 'POST',
        owner: false,
        json: { items: cart, customer_name: name, customer_phone: phone, pickup_time: pickup, note },
      })
      onPlaced(order)
    } catch (err) {
      setFormError(err instanceof ApiError && err.status === 429 ? 'Too many orders from this device. Please wait a minute and try again.' : errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const setQty = (i: number, qty: number) => setCart(cart.map((l, j) => (j === i ? { ...l, qty } : l)))
  const priced: (PricedLine | undefined)[] = quote && quote.items.length === cart.length ? quote.items : []

  return (
    <ReceiptCard id="checkout" aria-labelledby={headingId}>
      <h2 id={headingId} className="flex items-center gap-2 text-2xl">
        <ShoppingBag aria-hidden className="size-6" /> Your order
      </h2>
      <ReceiptDivider />
      <ul className="flex flex-col gap-3">
        {cart.map((line, i) => {
          const product = byId.get(line.product_id)
          const p = priced[i]
          return (
            <li key={lineKey(line)} className="flex flex-col gap-1.5">
              <ReceiptRow
                label={<span className="font-semibold">{product?.name ?? 'Item'}</span>}
                hint={optionsText(line) || undefined}
                value={p ? <PriceTag value={p.line_total} /> : '…'}
              />
              <div className="flex items-center justify-between gap-2">
                <QtyStepper qty={line.qty} onChange={(n) => setQty(i, n)} label={`How many ${product?.name ?? 'items'}`} />
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Trash2 aria-hidden className="size-4" />}
                  onClick={() => setCart(cart.filter((_, j) => j !== i))}
                  aria-label={`Remove ${product?.name ?? 'item'}`}
                >
                  Remove
                </Button>
              </div>
            </li>
          )
        })}
      </ul>
      <div className="mt-3">
        <ReceiptTotal value={quote ? <PriceTag value={quote.total} size="lg" /> : '…'} />
      </div>
      {quoteError && (
        <p role="alert" className="mt-2 font-semibold text-chili">
          {quoteError}
        </p>
      )}
      <p className="mt-2 text-center font-mono text-xs text-muted">Prices from the shop's menu · pay at pickup</p>
      <ReceiptDivider />
      <form onSubmit={submit} noValidate className="flex flex-col gap-4 pb-4">
        <Input label="Your name" autoComplete="name" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />
        <Input
          label="Phone number"
          type="tel"
          autoComplete="tel"
          inputMode="tel"
          placeholder="+65 9123 4567"
          maxLength={30}
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          error={errors.phone}
          hint="Only the shop owner sees this."
        />
        <Input
          label="Pickup date and time (Singapore time)"
          type="datetime-local"
          min={minPickup()}
          value={pickup}
          onChange={(e) => setPickup(e.target.value)}
          error={errors.pickup}
        />
        <Textarea label="Note for the shop (optional)" rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
        {formError && (
          <p role="alert" className="font-semibold text-chili">
            {formError}
          </p>
        )}
        <Button type="submit" size="lg" loading={busy} disabled={!cart.length || !!quoteError}>
          Place pickup order
        </Button>
        <p className="text-sm text-ink-soft">No account needed. You pay the shop when you collect.</p>
      </form>
    </ReceiptCard>
  )
}

/* ------------------------------------------------------------------ result */

const STATUS_VIEW: Record<WebOrder['status'], { stamp: 'approved' | 'held' | 'rejected'; label: string; title: string }> = {
  confirmed: { stamp: 'approved', label: 'Confirmed', title: 'Confirmed' },
  pending_owner_approval: { stamp: 'held', label: 'Sent to owner', title: 'Sent to the owner for approval' },
  rejected: { stamp: 'rejected', label: 'Rejected', title: "The shop couldn't take this order" },
  ready: { stamp: 'approved', label: 'Ready', title: 'Ready for pickup' },
  done: { stamp: 'approved', label: 'Collected', title: 'Collected' },
}

/** After ordering: the status in plain words. A held order keeps checking for the owner's decision. */
export function OrderResult({ initial, onNewOrder }: { initial: WebOrder; onNewOrder: () => void }) {
  const [order, setOrder] = useState(initial)
  usePoll(
    async () => {
      setOrder(await api<WebOrder>(`/api/public/orders/${encodeURIComponent(order.order_id)}`, { owner: false }))
    },
    10_000,
    order.status === 'pending_owner_approval',
  )
  const view = STATUS_VIEW[order.status]

  return (
    <ReceiptCard aria-live="polite">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <p className="font-mono text-xs tracking-widest text-muted uppercase">Order {order.order_id}</p>
          <h2 className="text-3xl">{view.title}</h2>
        </div>
        <Stamp key={order.status} kind={view.stamp} label={view.label} size="lg" animate />
      </div>
      <p className="mt-3 text-lg">{order.message}</p>
      {order.rejection_reason && <p className="mt-1 text-ink-soft">Reason from the shop: {order.rejection_reason}</p>}
      {order.status === 'pending_owner_approval' && (
        <p className="mt-1 text-sm text-ink-soft">Keep this page open. It updates when the owner decides.</p>
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
      <div className="py-4">
        <Button variant="secondary" onClick={onNewOrder}>
          Start a new order
        </Button>
      </div>
    </ReceiptCard>
  )
}
