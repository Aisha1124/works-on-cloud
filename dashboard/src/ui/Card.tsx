import type { HTMLAttributes } from 'react'
import { cx } from './cx'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Paper-coloured card instead of the bright receipt white. */
  tone?: 'receipt' | 'paper'
  padded?: boolean
}

export function Card({ tone = 'receipt', padded = true, className, ...rest }: CardProps) {
  return (
    <div
      className={cx(
        'border-2 border-ink shadow-hard',
        tone === 'receipt' ? 'bg-receipt' : 'bg-paper',
        padded && 'p-4 sm:p-5',
        className,
      )}
      {...rest}
    />
  )
}
