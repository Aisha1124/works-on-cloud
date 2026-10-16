import { ArrowRight } from 'lucide-react'
import { useEffect, useState, type CSSProperties } from 'react'
import type { MenuChecks, Product } from '../lib/types'
import { Button, ReceiptCard, ReceiptDivider, Stamp, cx } from '../ui'
import { ErrorCard } from './ErrorCard'
import { MenuLines } from './MenuLines'

const STATUS = [
  'Reading prices…',
  'Finding flavours and pack sizes…',
  'Sorting items into categories…',
  'Reading names in every language on the menu…',
  'Double-checking every price…',
  'Still reading. Long menus take up to a minute…',
]

export type ScanPhase = 'reading' | 'done' | 'error'

export interface ScanViewProps {
  photos: string[]
  phase: ScanPhase
  products: Product[]
  /** Product id -> reasons to check it (from the API). */
  checks?: MenuChecks
  warnings?: string[]
  error?: string | null
  onRetry?: () => void
  onCancel?: () => void
  onContinue?: () => void
  continueLabel?: string
}

/** Changes every few seconds while the photo is read. Mounted fresh for each read. */
function StatusLine() {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const t = window.setInterval(() => setStep((s) => Math.min(s + 1, STATUS.length - 1)), 4500)
    return () => window.clearInterval(t)
  }, [])
  return <>{STATUS[step]}</>
}

/** The photo with a scan line while Gemini reads it, then the items printing into a receipt. */
export function ScanView({ photos, phase, products, checks = {}, warnings = [], error, onRetry, onCancel, onContinue, continueLabel = 'Check your menu' }: ScanViewProps) {
  const toCheck = products.filter((p) => checks[p.id]?.length).length

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:items-start">
      <div className="flex flex-col gap-3">
        <div className={cx('grid gap-2', photos.length > 1 && 'grid-cols-2')}>
          {photos.map((src, i) => (
            <div key={src} className="scan-frame">
              <img src={src} alt={`Menu photo ${i + 1}`} className="block max-h-[28rem] w-full object-contain opacity-90" />
              {phase === 'reading' && <div className="scan-line" aria-hidden />}
            </div>
          ))}
        </div>
        <p className="font-mono text-sm text-ink-soft">
          {photos.length} photo{photos.length === 1 ? '' : 's'} · read by Gemini
        </p>
      </div>

      <div className="flex flex-col gap-4">
        {phase === 'reading' && (
          <ReceiptCard aria-busy="true">
            <p className="font-mono text-xs tracking-widest text-muted uppercase">Catalog agent</p>
            <p className="mt-2 font-display text-2xl font-extrabold sm:text-3xl" aria-live="polite">
              <StatusLine />
            </p>
            <ReceiptDivider />
            <div aria-hidden className="flex flex-col gap-3">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className={cx('skeleton-line', i % 2 ? 'w-1/2' : 'w-2/3')} style={{ '--i': i } as CSSProperties} />
                  <div className="flex-1" />
                  <div className="skeleton-line w-14" style={{ '--i': i } as CSSProperties} />
                </div>
              ))}
            </div>
            {onCancel && (
              <Button variant="ghost" size="sm" className="mt-4" onClick={onCancel}>
                Cancel
              </Button>
            )}
          </ReceiptCard>
        )}

        {phase === 'error' && (
          <ErrorCard
            message={error ?? "We couldn't read this photo. Please try again."}
            onRetry={onRetry}
            action={
              onCancel && (
                <Button variant="ghost" onClick={onCancel}>
                  Use another photo
                </Button>
              )
            }
          />
        )}

        {phase === 'done' && (
          <>
            <ReceiptCard>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-xs tracking-widest text-muted uppercase">Catalog agent</p>
                  <h2 className="mt-1 text-3xl">
                    Found {products.length} item{products.length === 1 ? '' : 's'}
                  </h2>
                </div>
                {toCheck > 0 && <Stamp kind="check" label={`${toCheck} to check`} size="sm" animate />}
              </div>
              <ReceiptDivider />
              {products.length === 0 ? (
                <p className="font-semibold">No prices found on this photo. Try a clearer photo, or add items by hand.</p>
              ) : (
                <ul aria-label="Items read from the photo">
                  {products.map((p, i) => (
                    <li key={p.id} className="print-in" style={{ '--i': i } as CSSProperties}>
                      <MenuLines product={p} />
                    </li>
                  ))}
                </ul>
              )}
              {warnings.length > 0 && (
                <>
                  <ReceiptDivider />
                  <ul className="list-disc pl-5 text-sm text-ink-soft">
                    {warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </>
              )}
            </ReceiptCard>
            {onContinue && (
              <Button size="lg" className="self-start" onClick={onContinue}>
                {continueLabel} <ArrowRight aria-hidden className="size-5" />
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  )
}
