import { cx } from './cx'

/** primary = chili (main action, reject), approve = pandan (approve, success). */
export type ButtonVariant = 'primary' | 'approve' | 'secondary' | 'ghost'
export type ButtonSize = 'sm' | 'md' | 'lg'

/** Classes for anything that should look like a button (e.g. a router Link). */
export function buttonClass(variant: ButtonVariant = 'primary', size: ButtonSize = 'md', extra?: string) {
  return cx('btn focus-ring', `btn-${variant}`, `btn-${size}`, extra)
}
