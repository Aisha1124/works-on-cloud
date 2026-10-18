import type { CSSProperties, ReactNode } from 'react'
import { cx } from './cx'

export interface SignboardProps {
  title: ReactNode
  subtitle?: ReactNode
  /** Small stall-number style plate, e.g. "#01-23". */
  plate?: ReactNode
  /** Buttons or links on the right. */
  actions?: ReactNode
  /** Board colour (a hex from SHOP_COLOURS). Default: chili. */
  color?: string
  className?: string
}

/** Page header painted like a hawker stall signboard. */
export function Signboard({ title, subtitle, plate, actions, color, className }: SignboardProps) {
  return (
    <header
      className={cx('signboard px-6 py-5 sm:px-8 sm:py-6', className)}
      style={color ? ({ '--signboard-bg': color } as CSSProperties) : undefined}
    >
      <div className="relative flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          {plate && (
            <span className="mb-2 inline-block border-2 border-ink bg-turmeric px-2 py-0.5 font-mono text-xs font-semibold tracking-widest text-ink uppercase">
              {plate}
            </span>
          )}
          <h1 className="text-3xl break-words text-receipt sm:text-5xl">{title}</h1>
          {subtitle && <p className="mt-1.5 text-base font-medium text-receipt sm:text-lg">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap gap-3">{actions}</div>}
      </div>
    </header>
  )
}
