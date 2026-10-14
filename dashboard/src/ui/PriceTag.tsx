import { cx } from './cx'
import { formatSGD } from './format'

const sizes = { sm: 'text-sm', md: 'text-base', lg: 'text-2xl font-semibold' }

export interface PriceTagProps {
  value: string | number | null | undefined
  size?: keyof typeof sizes
  /** Turmeric price-tag label instead of plain text. */
  boxed?: boolean
  className?: string
}

export function PriceTag({ value, size = 'md', boxed = false, className }: PriceTagProps) {
  const text = value === null || value === undefined || value === '' ? 'Ask' : formatSGD(value)
  return (
    <span
      className={cx(
        'font-mono tabular-nums whitespace-nowrap',
        sizes[size],
        boxed && 'inline-block border-2 border-ink bg-turmeric px-2 py-0.5 font-semibold text-ink shadow-hard-sm',
        className,
      )}
    >
      {text}
    </span>
  )
}
