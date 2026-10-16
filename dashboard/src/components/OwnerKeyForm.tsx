import { KeyRound, Mail } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { api, errorText } from '../lib/api'
import type { SignedIn } from '../lib/types'
import { Button, Input, ReceiptCard, ReceiptDivider } from '../ui'

/** Owner sign-in. Email link first (no password); the backup key is the fallback. Both end in
 *  a session cookie for one shop. */
export function OwnerSignIn({ onSignedIn, className, title = 'Shop owner login' }: { onSignedIn: (s: SignedIn) => void; className?: string; title?: string }) {
  const [mode, setMode] = useState<'email' | 'key'>('email')
  return (
    <ReceiptCard className={className} paperClassName="pb-5">
      {mode === 'email' ? <EmailLink title={title} /> : <BackupKey title={title} onSignedIn={onSignedIn} />}
      <ReceiptDivider />
      <button type="button" className="focus-ring text-sm font-semibold underline underline-offset-4" onClick={() => setMode(mode === 'email' ? 'key' : 'email')}>
        {mode === 'email' ? 'Use backup key instead' : 'Sign in with my email instead'}
      </button>
    </ReceiptCard>
  )
}

function EmailLink({ title }: { title: string }) {
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setError('Enter the email you used when your shop went live.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await api<{ message: string }>('/api/owner/email-link', { method: 'POST', json: { email: email.trim() }, owner: false })
      setSent(res.message)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  if (sent) {
    return (
      <div className="flex flex-col gap-3" role="status">
        <div className="flex items-center gap-3">
          <Mail aria-hidden className="size-6 flex-none" />
          <h1 className="text-2xl sm:text-3xl">Check your email</h1>
        </div>
        <p>
          We sent a sign-in link to <b>{email.trim()}</b>. Open it on this phone or computer and tap “Open my dashboard”.
        </p>
        <p className="text-sm text-ink-soft">{sent} Nothing there? Check your spam folder.</p>
        <Button variant="secondary" className="self-start" onClick={() => setSent(null)}>
          Use a different email
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <div className="flex items-center gap-3">
        <Mail aria-hidden className="size-6 flex-none" />
        <h1 className="text-2xl sm:text-3xl">{title}</h1>
      </div>
      <p className="text-ink-soft">Enter your email. We'll send you a link to sign in. No password needed.</p>
      <Input
        label="Your email"
        type="email"
        autoComplete="email"
        inputMode="email"
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={error}
        autoFocus
      />
      <Button type="submit" loading={busy} className="self-start">
        Email me a sign-in link
      </Button>
    </form>
  )
}

function BackupKey({ title, onSignedIn }: { title: string; onSignedIn: (s: SignedIn) => void }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const key = value.trim()
    if (!key) {
      setError('Enter the backup key you saved when your shop went live.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      onSignedIn(await api<SignedIn>('/api/owner/login', { method: 'POST', json: { key }, owner: false }))
    } catch (err) {
      setError(errorText(err))
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <div className="flex items-center gap-3">
        <KeyRound aria-hidden className="size-6 flex-none" />
        <h1 className="text-2xl sm:text-3xl">{title}</h1>
      </div>
      <p className="text-ink-soft">Use the backup key from when your shop went live (it starts with kc_).</p>
      <Input
        label="Backup key"
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
  )
}
