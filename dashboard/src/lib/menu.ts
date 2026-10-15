import type { Product } from './types'

/** "Flavour: Pandan / Gula Melaka · Size: S / L" */
export function optionsHint(p: Product): string {
  return p.options
    .filter((o) => o.choices.length)
    .map((o) => `${o.name}: ${o.choices.join(' / ')}`)
    .join(' · ')
}
