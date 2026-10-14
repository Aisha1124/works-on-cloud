import type { CSSProperties } from 'react'
import { cx } from './cx'
import { ReceiptCard } from './ReceiptCard'

export interface SkeletonProps {
  /** Number of printed rows. */
  rows?: number
  /** What is loading, read out to screen readers. */
  label?: string
  className?: string
}

/** Loading placeholder: a receipt printing out line by line. */
export function Skeleton({ rows = 5, label = 'Loading', className }: SkeletonProps) {
  return (
    <ReceiptCard className={className} role="status" aria-busy="true" aria-live="polite">
      <span className="sr-only">{label}…</span>
      <div aria-hidden className="flex flex-col gap-3 pb-1">
        <div className="skeleton-line h-4 w-2/5" style={{ '--i': 0 } as CSSProperties} />
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="flex items-center gap-3">
            <div className={cx('skeleton-line', i % 2 ? 'w-1/2' : 'w-2/3')} style={{ '--i': i + 1 } as CSSProperties} />
            <div className="flex-1" />
            <div className="skeleton-line w-14" style={{ '--i': i + 1 } as CSSProperties} />
          </div>
        ))}
      </div>
    </ReceiptCard>
  )
}
