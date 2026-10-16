import { Flag } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { ApiError, api, errorText } from '../lib/api'
import { Button, Input, Select, Textarea } from '../ui'

const REASONS = [
  ['wrong_info', 'Wrong prices or menu'],
  ['order_problem', 'Problem with an order'],
  ['not_real', 'Not a real shop, or a scam'],
  ['unsafe', 'Unsafe or illegal items'],
  ['other', 'Something else'],
] as const

/** "Report this shop": a small link that opens a short form (reason, details, optional email). */
export function ReportShop({ slug, shopName }: { slug: string; shopName: string }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState<string>('wrong_info')
  const [details, setDetails] = useState('')
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  async function send(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await api<{ message: string }>(`/api/public/shops/${encodeURIComponent(slug)}/report`, {
        method: 'POST',
        owner: false,
        json: { reason, details: details.trim(), email: email.trim() },
      })
      setDone(res.message)
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? 'You have sent a few reports already. Please try again later.' : errorText(err))
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <p role="status" className="font-semibold text-ink">
        {done}
      </p>
    )
  }
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="focus-ring inline-flex items-center gap-1 font-semibold text-ink underline underline-offset-4">
        <Flag aria-hidden className="size-4" /> Report this shop
      </button>
    )
  }
  return (
    <form onSubmit={send} noValidate className="mx-auto flex w-full max-w-md flex-col gap-3 border-2 border-ink bg-receipt p-4 text-left text-ink" aria-label={`Report ${shopName}`}>
      <p className="font-semibold">Report {shopName}</p>
      <Select label="What's wrong?" value={reason} onChange={(e) => setReason(e.target.value)}>
        {REASONS.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </Select>
      <Textarea label="Details (optional)" rows={3} maxLength={1000} value={details} onChange={(e) => setDetails(e.target.value)} />
      <Input label="Your email (optional)" type="email" autoComplete="email" maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} hint="Only if you'd like a reply. The shop won't see it." />
      {error && (
        <p role="alert" className="font-semibold text-chili">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" loading={busy}>
          Send report
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
