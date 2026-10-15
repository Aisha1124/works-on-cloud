import { KeyRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { ApiError, api, errorText } from '../lib/api'
import { clearOwnerKey, setOwnerKey } from '../lib/ownerKey'
import { Button, Input, ReceiptCard, ReceiptDivider } from '../ui'

/** Asks for OWNER_KEY once per browser tab. Checked against the API before it is kept. */
export function OwnerKeyForm({ className }: { className?: string }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const key = value.trim()
    if (!key) {
      setError('Enter the owner key from your setup.')
      return
    }
    setBusy(true)
    setError(null)
    setOwnerKey(key)
    try {
      await api('/api/shops')
    } catch (err) {
      clearOwnerKey()
      setError(err instanceof ApiError && err.status === 401 ? "That key doesn't match. Check it and try again." : errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <ReceiptCard className={className}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="flex items-center gap-3">
          <KeyRound aria-hidden className="size-6 flex-none" />
          <h2 className="text-2xl">Owner sign-in</h2>
        </div>
        <p className="text-ink-soft">
          Enter your owner key. It stays in this browser tab only and is cleared when you close it.
        </p>
        <ReceiptDivider />
        <Input
          label="Owner key"
          type="password"
          autoComplete="current-password"
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
