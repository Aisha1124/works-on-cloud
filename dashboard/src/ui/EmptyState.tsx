import type { ReactNode } from 'react'
import { cx } from './cx'

export interface EmptyStateProps {
  /** One friendly line. */
  message: ReactNode
  action?: ReactNode
  className?: string
}

export function EmptyState({ message, action, className }: EmptyStateProps) {
  return (
    <div
      className={cx(
        'flex flex-col items-start gap-4 border-2 border-dashed border-ink bg-receipt p-6 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
    >
      <p className="font-display text-xl font-bold">{message}</p>
      {action}
    </div>
  )
}
