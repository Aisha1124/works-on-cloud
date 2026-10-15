import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { OwnerBar } from '../components/OwnerShell'
import { OwnerKeyForm } from '../components/OwnerKeyForm'
import { PhotoDrop } from '../components/PhotoDrop'
import { ScanView, type ScanPhase } from '../components/ScanView'
import { PHOTO_TIMEOUT_MS, api, errorText } from '../lib/api'
import { useLoad, useOwnerKey } from '../lib/hooks'
import type { DraftResponse, ShopSummary } from '../lib/types'
import { ReceiptCard, ReceiptDivider, Signboard, Stamp } from '../ui'

const steps = [
  { n: '01', word: 'Snap', done: '1 photo', line: 'Your price list, menu board or Instagram post.' },
  { n: '02', word: 'Check', done: 'fix', line: 'Fix any name, price, pack or flavour we read wrong.' },
  { n: '03', word: 'Go live', done: 'open', line: 'AI agents can find your shop and place pickup orders.' },
]

function StepsReceipt() {
  return (
    <ReceiptCard aria-label="How it works" paperClassName="font-mono">
      <p className="text-center text-xs tracking-[0.3em] text-muted uppercase">How it works</p>
      <ReceiptDivider />
      <ol className="flex flex-col gap-4">
        {steps.map((s) => (
          <li key={s.n}>
            <div className="flex items-baseline gap-2">
              <span className="text-sm text-muted">{s.n}</span>
              <span className="font-display text-2xl font-extrabold">{s.word}</span>
              <span className="leader" aria-hidden />
              <span className="text-sm font-semibold text-chili">{s.done}</span>
            </div>
            <p className="pl-7 text-xs leading-snug text-ink-soft">{s.line}</p>
          </li>
        ))}
      </ol>
      <ReceiptDivider />
      <p className="text-center text-xs text-muted">Payment at pickup · SGD</p>
    </ReceiptCard>
  )
}

function YourShops() {
  const shops = useLoad((signal) => api<ShopSummary[]>('/api/shops', { signal }), 'shops')
  if (!shops.data?.length) return null
  return (
    <section aria-labelledby="your-shops" className="flex flex-col gap-3">
      <h2 id="your-shops" className="text-2xl">
        Your shops
      </h2>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {shops.data.slice(0, 6).map((s) => (
          <li key={s.id}>
            <Link
              to={`/shop/${s.id}`}
              className="focus-ring flex items-center justify-between gap-3 border-2 border-ink bg-receipt p-3 shadow-hard-sm hover:bg-turmeric-tint"
            >
              <span className="min-w-0 truncate font-semibold">{s.name}</span>
              <Stamp kind={s.published ? 'approved' : 'check'} label={s.published ? 'Live' : 'Draft'} size="sm" />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function Onboarding() {
  const key = useOwnerKey()
  const navigate = useNavigate()
  const [files, setFiles] = useState<File[]>([])
  const [photos, setPhotos] = useState<string[]>([])
  const [phase, setPhase] = useState<ScanPhase | 'idle'>('idle')
  const [result, setResult] = useState<DraftResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const ctrlRef = useRef<AbortController | null>(null)

  useEffect(() => () => photos.forEach((u) => URL.revokeObjectURL(u)), [photos])
  useEffect(() => () => ctrlRef.current?.abort(), [])

  async function upload(list: File[]) {
    ctrlRef.current?.abort()
    const ctrl = new AbortController()
    ctrlRef.current = ctrl
    setPhase('reading')
    setError(null)
    const form = new FormData()
    list.forEach((f) => form.append('images', f, f.name))
    try {
      const res = await api<DraftResponse>('/api/shops/draft', {
        method: 'POST',
        form,
        timeoutMs: PHOTO_TIMEOUT_MS,
        signal: ctrl.signal,
      })
      setResult(res)
      setPhase('done')
    } catch (err) {
      if (ctrl.signal.aborted) return
      setError(errorText(err))
      setPhase('error')
    }
  }

  function start(list: File[]) {
    setFiles(list)
    setPhotos(list.map((f) => URL.createObjectURL(f)))
    void upload(list)
  }

  function reset() {
    ctrlRef.current?.abort()
    setPhase('idle')
    setFiles([])
    setPhotos([])
    setResult(null)
  }

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 pt-4 pb-16 sm:px-6 sm:pt-6">
      <OwnerBar />
      <Signboard
        plate={
          <>
            For Singapore <span className="hidden sm:inline">home bakers, hawkers &amp; heartland </span>shops
          </>
        }
        title="Make your shop AI‑ready from one photo."
        subtitle={
          <span className="hidden sm:inline">
            AI shopping assistants can find your menu, get a quote and place pickup orders. You approve anything unusual.
          </span>
        }
      />

      {phase === 'idle' ? (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] lg:items-start">
          {key ? (
            <PhotoDrop
              onFiles={start}
              title={
                <>
                  <span className="sm:hidden">Snap your menu</span>
                  <span className="hidden sm:inline">Drop your menu photo here</span>
                </>
              }
            />
          ) : (
            <OwnerKeyForm />
          )}
          <StepsReceipt />
        </div>
      ) : (
        <section aria-label="Reading your menu">
          <ScanView
            photos={photos}
            phase={phase}
            products={result?.products ?? []}
            warnings={result?.warnings}
            error={error}
            onRetry={() => void upload(files)}
            onCancel={reset}
            onContinue={result ? () => navigate(`/shop/${result.shop.id}`) : undefined}
          />
        </section>
      )}

      {key && phase === 'idle' && <YourShops />}
    </main>
  )
}
