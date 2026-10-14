import type { HTMLAttributes, ReactNode } from 'react'
import { cx } from './cx'

export interface ReceiptCardProps extends HTMLAttributes<HTMLDivElement> {
  /** Which edges are torn. */
  edge?: 'bottom' | 'both'
  /** Extra classes for the paper itself (padding, width). */
  paperClassName?: string
}

/** Printed receipt with a zigzag torn edge. */
export function ReceiptCard({ edge = 'bottom', className, paperClassName, children, ...rest }: ReceiptCardProps) {
  return (
    <div className={cx('receipt-wrap', className)} {...rest}>
      <div data-edge={edge} className={cx('receipt-paper px-4 pt-4 sm:px-5', paperClassName)}>
        {children}
      </div>
    </div>
  )
}

export interface ReceiptRowProps {
  label: ReactNode
  value: ReactNode
  /** Smaller line under the label, e.g. variant or options. */
  hint?: ReactNode
  className?: string
}

/** item ........ price */
export function ReceiptRow({ label, value, hint, className }: ReceiptRowProps) {
  return (
    <div className={cx('py-1', className)}>
      <div className="flex items-baseline gap-2">
        <span className="min-w-0 break-words">{label}</span>
        <span className="leader" aria-hidden />
        <span className="font-mono tabular-nums whitespace-nowrap">{value}</span>
      </div>
      {hint && <div className="font-mono text-xs text-muted">{hint}</div>}
    </div>
  )
}

export function ReceiptDivider() {
  return <hr className="my-3 border-0 border-t-2 border-dashed border-ink" />
}

export function ReceiptTotal({ label = 'TOTAL', value }: { label?: ReactNode; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-y-2 border-ink py-2 font-mono text-lg font-semibold">
      <span>{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  )
}
