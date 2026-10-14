import { cx } from './cx'

export type StampKind = 'approved' | 'held' | 'rejected' | 'check'

const defaultLabel: Record<StampKind, string> = {
  approved: 'Approved',
  held: 'Held',
  rejected: 'Rejected',
  check: 'Check',
}

const sizes = { sm: 'text-sm', md: 'text-xl', lg: 'text-3xl' }

export interface StampProps {
  kind: StampKind
  /** Override the default word, e.g. "API OK". */
  label?: string
  size?: keyof typeof sizes
  /** Land with a small bounce when it mounts. */
  animate?: boolean
  className?: string
}

export function Stamp({ kind, label, size = 'md', animate = false, className }: StampProps) {
  return (
    <span
      className={cx('stamp', `stamp-${kind}`, sizes[size], className)}
      data-animate={animate || undefined}
    >
      {label ?? defaultLabel[kind]}
    </span>
  )
}
