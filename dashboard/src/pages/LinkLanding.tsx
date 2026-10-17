import { ArrowRight, MailCheck } from 'lucide-react'
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { OwnerSignIn } from '../components/OwnerKeyForm'
import { OwnerBar } from '../components/OwnerShell'
import { api, errorText } from '../lib/api'
import type { SignedIn } from '../lib/types'
import { Button, ReceiptCard } from '../ui'

const COPY = {
  signin: { title: 'Open your shop', line: 'Tap below to sign in on this device.', button: 'Open my dashboard', api: '/api/owner/signin' },
  verify: { title: 'Confirm your email', line: 'Tap below to confirm this is your email. You will be signed in too.', button: 'Confirm my email', api: '/api/owner/verify' },
} as const

/** /signin?token=… and /verify?token=…: the link from an email. Opening it changes nothing (email
 *  scanners open links too); the tap uses the one-time link and signs the owner in. */
export function LinkLanding({ kind }: { kind: keyof typeof COPY }) {
  const copy = COPY[kind]
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(token ? null : 'This link is missing its code. Ask for a new one below.')
  const go = (s: SignedIn) => navigate(s.next || `/shop/${s.shop_id}/orders`, { replace: true })

  async function use() {
    setBusy(true)
    try {
      go(await api<SignedIn>(copy.api, { method: 'POST', json: { token }, owner: false }))
    } catch (err) {
      setError(errorText(err))
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto flex max-w-xl flex-col gap-6 px-4 py-6 sm:py-10">
      <OwnerBar showLogin={false} />
      {error ? (
        <>
          <p role="alert" className="border-2 border-ink bg-turmeric-tint p-4 font-semibold">
            {error}
          </p>
          <OwnerSignIn onSignedIn={go} title="Get a new link" />
        </>
      ) : (
        <ReceiptCard paperClassName="pb-6">
          <div className="flex items-center gap-3">
            <MailCheck aria-hidden className="size-7 flex-none" />
            <h1 className="text-3xl">{copy.title}</h1>
          </div>
          <p className="mt-2 text-ink-soft">{copy.line}</p>
          <Button size="lg" className="mt-5" loading={busy} onClick={use}>
            {copy.button} <ArrowRight aria-hidden className="size-5" />
          </Button>
        </ReceiptCard>
      )}
    </main>
  )
}
