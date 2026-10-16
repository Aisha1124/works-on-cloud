import { KeyRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { api, errorText } from '../lib/api'
import { setOwnerKey } from '../lib/ownerKey'
import type { LoginResponse } from '../lib/types'
import { Button, Input, ReceiptCard, ReceiptDivider } from '../ui'

/** Owner sign-in: the key finds its own shop. Wrong keys get a friendly message (and the
 *  server limits how many tries a client gets). */
export function OwnerKeyForm({ onSignedIn, className }: { onSignedIn: (shop: LoginResponse) => void; className?: string }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const key = value.trim()
    if (!key) {
      setError('Enter the owner key you saved when your shop went live.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const shop = await api<LoginResponse>('/api/owner/login', { method: 'POST', json: { key }, owner: false })
      setOwnerKey(shop.shop_id, key)
      onSignedIn(shop)
    } catch (err) {
      setError(errorText(err))
      setBusy(false)
    }
  }

  return (
    <ReceiptCard className={className}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="flex items-center gap-3">
          <KeyRound aria-hidden className="size-6 flex-none" />
          <h1 className="text-2xl sm:text-3xl">Shop owner login</h1>
        </div>
        <p className="text-ink-soft">
          Enter the owner key you got when your shop went live. It opens your orders and menu. We keep it in this browser tab only.
        </p>
        <ReceiptDivider />
        <Input
          label="Owner key"
          type="password"
          autoComplete="current-password"
          placeholder="kc_…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          error={error}
          autoFocus
        />
        <Button type="submit" loading={busy} className="self-start">
          Open my shop
        </Button>
      </form>
    </ReceiptCard>
  )
}
