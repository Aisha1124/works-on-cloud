import { ArrowRight, X } from 'lucide-react'
import { useEffect, useId, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { errorText } from '../lib/api'
import { goLive, liveScreen } from '../lib/publish'
import type { ShopDetail } from '../lib/types'
import { Button, Input, ReceiptCard } from '../ui'

/** Go live = create the owner's account: shop name and email, then straight to the shop. */
export function GoLiveDialog({
  shopId,
  defaultName,
  onClose,
  onLive,
}: {
  shopId: string
  defaultName: string
  onClose: () => void
  onLive?: (detail: ShopDetail) => void
}) {
  const navigate = useNavigate()
  const titleId = useId()
  const [name, setName] = useState(defaultName === 'My shop' ? '' : defaultName)
  const [email, setEmail] = useState('')
  const [errors, setErrors] = useState<{ name?: string; email?: string; form?: string }>({})
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !busy && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onClose])

  async function submit(e: FormEvent) {
    e.preventDefault()
    const errs: typeof errors = {}
    if (!name.trim()) errs.name = 'The name customers will see, e.g. “Auntie Lim’s Bakes”.'
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) errs.email = 'Your email, so we can send you orders.'
    setErrors(errs)
    if (errs.name || errs.email) return
    setBusy(true)
    try {
      const { detail, ownerKey } = await goLive(shopId, { name: name.trim(), email: email.trim() })
      onLive?.(detail)
      const next = liveScreen(shopId, ownerKey)
      navigate(next.to, next.options)
    } catch (err) {
      const text = errorText(err)
      setErrors(/email/i.test(text) ? { email: text } : /name/i.test(text) ? { name: text } : { form: text })
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/60 p-3 sm:items-center" onMouseDown={(e) => e.target === e.currentTarget && !busy && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="w-full max-w-md">
        <ReceiptCard paperClassName="pb-5">
          <div className="flex items-start justify-between gap-3">
            <h2 id={titleId} className="text-2xl sm:text-3xl">
              Create your shop
            </h2>
            <Button variant="ghost" size="sm" onClick={onClose} disabled={busy} aria-label="Close" icon={<X aria-hidden className="size-4" />} />
          </div>
          <p className="mt-1 text-ink-soft">Two things, then you're live. No password needed: we email you a link to sign in.</p>
          <form onSubmit={submit} noValidate className="mt-4 flex flex-col gap-4">
            <Input label="Shop name" autoFocus maxLength={80} value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />
            <Input
              label="Your email"
              type="email"
              autoComplete="email"
              inputMode="email"
              placeholder="you@example.com"
              maxLength={254}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              error={errors.email}
              hint="New orders and sign-in links go here. Customers never see it."
            />
            {errors.form && (
              <p role="alert" className="font-semibold text-chili">
                {errors.form}
              </p>
            )}
            <Button type="submit" size="lg" loading={busy}>
              Go live <ArrowRight aria-hidden className="size-5" />
            </Button>
          </form>
        </ReceiptCard>
      </div>
    </div>
  )
}
