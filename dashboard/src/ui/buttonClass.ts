import { cx } from './cx'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost'
export type ButtonSize = 'sm' | 'md'

/** Classes for anything that should look like a button (e.g. a router Link). */
export function buttonClass(variant: ButtonVariant = 'primary', size: ButtonSize = 'md', extra?: string) {
  return cx('btn focus-ring', `btn-${variant}`, `btn-${size}`, extra)
}
