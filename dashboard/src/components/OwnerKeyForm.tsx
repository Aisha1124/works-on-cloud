import { KeyRound } from 'lucide-react'
import { forwardRef, useId, useState, type FormEvent } from 'react'
import { ApiError, api, errorText } from '../lib/api'
import { setOwnerKey } from '../lib/ownerKey'
import { Button, Input, ReceiptCard, ReceiptDivider, cx } from '../ui'

/** Checks a key against the API before keeping it (sessionStorage, this tab only). */
function useKeyCheck(onUnlocked?: () => void) {
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
    try {
      // Check first, keep after: storing the key re-renders the page without this form.
      await api('/api/shops', { ownerKey: key })
    } catch (err) {
      setBusy(false)
      setError(err instanceof ApiError && err.status === 401 ? "That key doesn't match. Check it and try again." : errorText(err))
      return
    }
    setOwnerKey(key)
    onUnlocked?.()
  }

  return { value, setValue, error, busy, submit }
}

/** Full card, for owner pages opened directly (e.g. /shop/:id). */
export function OwnerKeyForm({ className }: { className?: string }) {
  const { value, setValue, error, busy, submit } = useKeyCheck()
  return (
    <ReceiptCard className={className}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="flex items-center gap-3">
          <KeyRound aria-hidden className="size-6 flex-none" />
          <h2 className="text-2xl">Owner sign-in</h2>
        </div>
        <p className="text-ink-soft">Enter your owner key to open your shop. We keep it in this browser tab only.</p>
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

/** One-line key step, clipped to the top of the photo drop zone like a ticket stub. */
export const OwnerKeyStrip = forwardRef<HTMLInputElement, { onUnlocked?: () => void; waiting?: boolean; className?: string }>(
  function OwnerKeyStrip({ onUnlocked, waiting = false, className }, ref) {
    const { value, setValue, error, busy, submit } = useKeyCheck(onUnlocked)
    const id = useId()
    return (
      <form
        onSubmit={submit}
        noValidate
        className={cx('flex flex-col gap-2 border-2 border-b-0 border-ink bg-turmeric-tint px-3 py-2.5 sm:px-4', className)}
        aria-label="Owner key"
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <label htmlFor={id} className="flex items-center gap-2 text-sm font-semibold whitespace-nowrap">
            <KeyRound aria-hidden className="size-4" />
            {waiting ? 'Enter your owner key to read this photo' : 'Owner key'}
          </label>
          <div className="flex min-w-0 flex-1 basis-56 gap-2">
            <input
              ref={ref}
              id={id}
              type="password"
              autoComplete="current-password"
              className="control min-h-9 min-w-0 flex-1 py-1 text-sm"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? `${id}-error` : undefined}
            />
            <Button type="submit" size="sm" loading={busy}>
              {waiting ? 'Unlock & read' : 'Unlock'}
            </Button>
          </div>
        </div>
        {error && (
          <p id={`${id}-error`} role="alert" className="text-sm font-semibold">
            {error}
          </p>
        )}
      </form>
    )
  },
)
