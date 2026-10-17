import { ArrowDown, ArrowRight, Bot, Camera, QrCode, ShieldCheck, type LucideIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { GoLiveDialog } from '../components/GoLiveDialog'
import { OwnerBar } from '../components/OwnerShell'
import { PhotoDrop } from '../components/PhotoDrop'
import { ScanView, type ScanPhase } from '../components/ScanView'
import { PHOTO_TIMEOUT_MS, api, errorText } from '../lib/api'
import { setOwnerKey } from '../lib/ownerKey'
import { SAMPLE_SHOP } from '../lib/sample'
import type { DraftResponse } from '../lib/types'
import { Button, Signboard, buttonClass, cx } from '../ui'

const STEPS: { icon: LucideIcon; who: string; line: string }[] = [
  { icon: Camera, who: 'Owner', line: 'Snaps a menu photo. Gemini turns it into a menu.' },
  { icon: QrCode, who: 'Owner', line: 'Taps Go live and gets a shop link, QR code and owner key.' },
  { icon: Bot, who: 'Customers', line: 'Order from the shop link. Any AI can read the menu from it; AI apps connected through MCP can also order.' },
  { icon: ShieldCheck, who: 'Orders', line: "Normal orders confirm automatically. Unusual ones wait for the owner's OK." },
]

/** Two equal doors: one for shop owners, one for customers. */
function AudienceButtons({ onOwner }: { onOwner: () => void }) {
  const tile = 'h-full w-full flex-col items-start gap-1 py-4 text-left'
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <button type="button" onClick={onOwner} className={buttonClass('primary', 'lg', tile)}>
        <span className="font-mono text-xs tracking-widest uppercase opacity-90">I run a shop</span>
        <span className="flex items-center gap-2 font-display text-2xl font-extrabold">
          Upload my menu <ArrowDown aria-hidden className="size-6" />
        </span>
      </button>
      <Link to={`/s/${SAMPLE_SHOP.slug}`} className={buttonClass('approve', 'lg', tile)}>
        <span className="font-mono text-xs tracking-widest uppercase opacity-90">See what customers see</span>
        <span className="flex items-center gap-2 font-display text-2xl font-extrabold">
          Try Mak's Kuih <ArrowRight aria-hidden className="size-6" />
        </span>
      </Link>
    </div>
  )
}

function HowItWorks() {
  return (
    <section aria-labelledby="how-it-works" className="flex flex-col gap-3">
      <h2 id="how-it-works" className="text-2xl sm:text-3xl">
        How KampungCart works
      </h2>
      <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map(({ icon: Icon, who, line }, i) => (
          <li key={line} className="flex gap-3 border-2 border-ink bg-receipt p-4 shadow-hard-sm lg:flex-col">
            <div className="flex flex-none items-center gap-3 lg:justify-between">
              <span className="font-mono text-2xl font-semibold text-chili">{i + 1}</span>
              <span className="grid size-10 place-items-center border-2 border-ink bg-turmeric">
                <Icon aria-hidden className="size-5" />
              </span>
            </div>
            <p className="min-w-0">
              <span className="block font-mono text-xs tracking-widest text-muted uppercase">{who}</span>
              <span className="leading-snug">{line}</span>
            </p>
          </li>
        ))}
      </ol>
    </section>
  )
}

/** After the menu is read: the next step, always on screen. */
function GoLiveBar({ shopId, shopName, count }: { shopId: string; shopName: string; count: number }) {
  const [open, setOpen] = useState(false)
  return (
    <>
    <div className="fixed inset-x-0 bottom-0 z-40 border-t-2 border-ink bg-receipt" role="region" aria-label="Next step">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <p className="font-mono text-sm">
          <span className="font-semibold">
            {count} item{count === 1 ? '' : 's'} read
          </span>
          <span className="hidden text-ink-soft sm:inline"> · you can edit them any time</span>
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Link to={`/shop/${shopId}`} className={buttonClass('secondary', 'md')}>
            Fix something first
          </Link>
          <Button size="lg" onClick={() => setOpen(true)}>
            Looks right? Go live <ArrowRight aria-hidden className="size-5" />
          </Button>
        </div>
      </div>
    </div>
    {open && <GoLiveDialog shopId={shopId} defaultName={shopName} onClose={() => setOpen(false)} />}
    </>
  )
}

export function Onboarding() {
  const navigate = useNavigate()
  const [files, setFiles] = useState<File[]>([])
  const [photos, setPhotos] = useState<string[]>([])
  const [phase, setPhase] = useState<ScanPhase | 'idle'>('idle')
  const [result, setResult] = useState<DraftResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const ctrlRef = useRef<AbortController | null>(null)
  const uploadRef = useRef<HTMLHeadingElement>(null)

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
      // The draft key lets this tab review the new shop. Going live swaps it for the owner key.
      if (res.draft_key) setOwnerKey(res.shop.id, res.draft_key)
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

  function toUpload() {
    const target = uploadRef.current
    if (!target) return
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    target.scrollIntoView?.({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
    target.focus({ preventScroll: true })
  }

  const read = phase === 'done' && result && result.products.length > 0

  return (
    // The right gutter is 4px wider than the left so the hard shadows don't eat into it.
    <main className={cx('mx-auto flex max-w-6xl flex-col gap-8 pt-4 pr-5 pl-4 sm:pt-6 sm:pr-7 sm:pl-6', read ? 'pb-36' : 'pb-16')}>
      <OwnerBar />
      <div className="flex flex-col gap-5">
        <Signboard
          plate={
            <>
              For Singapore <span className="hidden sm:inline">home bakers, hawkers &amp; heartland </span>shops
            </>
          }
          title="Make your shop AI‑ready from one photo."
          subtitle={
            <span className="hidden sm:inline">
              Customers order from your link. Any AI can read your menu from it; AI apps connected through MCP can also order. You approve anything unusual.
            </span>
          }
        />
        {phase === 'idle' && <AudienceButtons onOwner={toUpload} />}
      </div>

      {phase === 'idle' && <HowItWorks />}

      <section aria-labelledby="upload-menu" className="flex scroll-mt-4 flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h2 id="upload-menu" ref={uploadRef} tabIndex={-1} className="text-2xl outline-none sm:text-3xl">
            {phase === 'idle' ? 'Upload your menu' : 'Reading your menu'}
          </h2>
          {phase === 'idle' && <p className="text-ink-soft">Free. No account needed to start. You'll create your shop at the end.</p>}
        </div>
        {phase === 'idle' ? (
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
          <ScanView
            photos={photos}
            phase={phase}
            products={result?.products ?? []}
            checks={result?.checks}
          warnings={result?.warnings}
            error={error}
            onRetry={() => void upload(files)}
            onCancel={reset}
            // With items, the sticky bar below is the next step. With none, add them by hand.
            onContinue={result && !read ? () => navigate(`/shop/${result.shop.id}`) : undefined}
            continueLabel="Add items by hand"
          />
        )}
      </section>

      <footer className="border-t-2 border-dashed border-ink pt-4 text-center text-sm text-ink-soft">
        <Link to="/privacy" className="focus-ring font-semibold text-ink underline underline-offset-4">
          Privacy
        </Link>
      </footer>

      {read && <GoLiveBar shopId={result.shop.id} shopName={result.shop.name} count={result.products.length} />}
    </main>
  )
}
