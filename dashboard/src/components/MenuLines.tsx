import { optionsHint } from '../lib/menu'
import type { Product } from '../lib/types'
import { PriceTag, ReceiptRow, cx } from '../ui'

/** One product as receipt lines: the item, then one indented line per pack or size. */
export function MenuLines({ product, className }: { product: Product; className?: string }) {
  const multi = product.variants.length > 1
  const single = product.variants.length === 1 ? product.variants[0] : null
  const hint = [single?.label || product.unit, optionsHint(product)].filter(Boolean).join(' · ')
  const name = (
    <>
      <span className="font-semibold">{product.name}</span>
      {product.name_local && <span className="ml-2 text-ink-soft">{product.name_local}</span>}
    </>
  )
  return (
    <div className={cx(!product.available && 'opacity-60', className)}>
      {multi && product.available ? (
        // Several packs: the name heads the group and each pack gets its own leader line.
        <div className="py-1">
          {name}
          {hint && <div className="font-mono text-xs text-muted">{hint}</div>}
        </div>
      ) : (
        <ReceiptRow
          label={name}
          value={!product.available ? 'Sold out' : <PriceTag value={single ? single.price : product.base_price} />}
          hint={hint || undefined}
        />
      )}
      {multi &&
        product.available &&
        product.variants.map((v, i) => (
          <ReceiptRow key={`${i}-${v.label}`} className="pl-4 text-sm" label={v.label} value={<PriceTag value={v.price} size="sm" />} />
        ))}
    </div>
  )
}
