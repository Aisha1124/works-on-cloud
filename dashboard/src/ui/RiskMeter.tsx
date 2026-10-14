import type { CSSProperties } from 'react'
import { cx } from './cx'
import { riskLevel, type RiskLevel } from './format'

const SEGMENTS = 20

const levelStyle: Record<RiskLevel, { color: string; chip: string }> = {
  low: { color: 'var(--pandan)', chip: 'bg-pandan text-receipt' },
  medium: { color: 'var(--turmeric)', chip: 'bg-turmeric text-ink' },
  high: { color: 'var(--chili)', chip: 'bg-chili text-receipt' },
}

export interface RiskMeterProps {
  /** 0-100. null while the risk check is still running. */
  score: number | null
  /** Level from the backend. Falls back to the thresholds below. */
  level?: RiskLevel
  mediumAt?: number
  highAt?: number
  className?: string
}

/** Risk score drawn like a receipt-printer gauge. */
export function RiskMeter({ score, level, mediumAt = 40, highAt = 70, className }: RiskMeterProps) {
  const loading = score === null
  const value = loading ? 0 : Math.max(0, Math.min(100, Math.round(score)))
  const lvl = level ?? riskLevel(value, mediumAt, highAt)
  const on = Math.ceil((value / 100) * SEGMENTS)
  const style = levelStyle[lvl]

  return (
    <div
      className={cx('border-2 border-ink bg-receipt p-3 font-mono shadow-hard-sm', className)}
      role="meter"
      aria-label="Risk score"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={loading ? undefined : value}
      aria-valuetext={loading ? 'Checking' : `${value} out of 100, ${lvl} risk`}
      aria-busy={loading || undefined}
      style={{ '--meter-color': style.color } as CSSProperties}
    >
      <div className="flex items-baseline justify-between gap-2 text-xs tracking-widest text-muted uppercase">
        <span>Risk check</span>
        <span>0–100</span>
      </div>

      <div className="mt-2 grid grid-cols-[repeat(20,minmax(0,1fr))] gap-[3px]" aria-hidden>
        {Array.from({ length: SEGMENTS }, (_, i) => (
          <span
            key={i}
            className={cx('meter-seg', loading && 'animate-pulse motion-reduce:animate-none')}
            data-on={!loading && i < on}
            style={{ '--i': i } as CSSProperties}
          />
        ))}
      </div>

      {/* Scale with threshold ticks */}
      <div className="relative mt-1 h-4 text-[10px] text-muted" aria-hidden>
        {[0, mediumAt, highAt, 100].map((t) => (
          <span
            key={t}
            className="absolute top-0 -translate-x-1/2 border-l-2 border-ink pl-0.5 leading-none first:translate-x-0 last:-translate-x-full last:border-l-0 last:border-r-2 last:pr-0.5"
            style={{ left: `${t}%` }}
          >
            {t}
          </span>
        ))}
      </div>

      <div className="mt-2 flex items-center justify-between gap-3 border-t-2 border-dashed border-ink pt-2">
        <span className="text-2xl font-semibold tabular-nums">
          {loading ? '---' : String(value).padStart(3, '0')}
          <span className="text-sm text-muted">/100</span>
        </span>
        <span className={cx('px-2 py-0.5 text-sm font-semibold tracking-wider uppercase', loading ? 'border-2 border-dashed border-ink' : style.chip)}>
          {loading ? 'Checking…' : lvl}
        </span>
      </div>
    </div>
  )
}
