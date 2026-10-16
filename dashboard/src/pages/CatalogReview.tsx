import { ArrowRight, ImagePlus, Pencil, Plus, Trash2, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { GoLiveDialog } from '../components/GoLiveDialog'
import { MenuLines } from '../components/MenuLines'
import { PhotoDrop } from '../components/PhotoDrop'
import { ScanView, type ScanPhase } from '../components/ScanView'
import { PHOTO_TIMEOUT_MS, api, errorText } from '../lib/api'
import { useShop } from '../lib/shop'
import type { DraftResponse, Product, ProductInput, Shop, ShopDetail } from '../lib/types'
import {
  Button,
  Card,
  EmptyState,
  Input,
  ReceiptCard,
  ReceiptDivider,
  Select,
  Stamp,
  Textarea,
  Toggle,
  buttonClass,
  cx,
  useToast,
} from '../ui'

const LOW_CONFIDENCE = 0.7
const MONEY = /^\d{1,6}(\.\d{1,2})?$/
const SHOP_TYPES = ['Home baker', 'Hawker stall', 'Heartland shop', 'Instagram seller', 'Cafe', 'Caterer']
const NO_CATEGORY = 'Other items'

const needsCheck = (p: Product) => p.confidence < LOW_CONFIDENCE

/* ------------------------------------------------------------------ shop details */

function ShopDetailsForm({ shop, onSaved }: { shop: Shop; onSaved: (s: Shop) => void }) {
  const toast = useToast()
  const initial = useMemo(
    () => ({
      name: shop.name,
      tagline: shop.tagline,
      shop_type: shop.shop_type,
      address: shop.address,
      hours: shop.hours,
      phone: shop.phone,
      auto_approve_limit: shop.auto_approve_limit,
    }),
    [shop],
  )
  const [form, setForm] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<keyof typeof initial, string>>>({})

  const changed = (Object.keys(form) as (keyof typeof form)[]).filter((k) => form[k].trim() !== initial[k])
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function save(e: FormEvent) {
    e.preventDefault()
    const errs: typeof errors = {}
    if (!form.name.trim()) errs.name = 'Your shop needs a name.'
    if (!MONEY.test(form.auto_approve_limit.trim())) errs.auto_approve_limit = 'Enter an amount like 150 or 150.00.'
    setErrors(errs)
    if (Object.keys(errs).length || !changed.length) return
    setBusy(true)
    try {
      const body = Object.fromEntries(changed.map((k) => [k, form[k].trim()]))
      const saved = await api<Shop>(`/api/shops/${shop.id}`, { method: 'PATCH', json: body })
      onSaved(saved)
      toast.show('Shop details saved.', 'success')
    } catch (err) {
      toast.show(errorText(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const types = SHOP_TYPES.includes(shop.shop_type) || !shop.shop_type ? SHOP_TYPES : [shop.shop_type, ...SHOP_TYPES]

  return (
    <Card className="flex flex-col gap-4">
      <h2 className="text-2xl">Shop details</h2>
      <form onSubmit={save} className="flex flex-col gap-4" noValidate>
        <Input label="Shop name" value={form.name} onChange={set('name')} error={errors.name} maxLength={80} required />
        <Input label="Tagline" value={form.tagline} onChange={set('tagline')} maxLength={160} placeholder="e.g. Nyonya kuih, made fresh" />
        <Select label="Type of shop" value={form.shop_type} onChange={set('shop_type')}>
          <option value="">Choose one</option>
          {types.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </Select>
        <Input
          label="Area / address"
          value={form.address}
          onChange={set('address')}
          maxLength={200}
          placeholder="e.g. Blk 201 Tampines St 21, Tampines"
          hint="Put the area last. Agents show it to buyers."
        />
        <Input label="Opening hours" value={form.hours} onChange={set('hours')} maxLength={200} placeholder="e.g. Tue-Sun 9am-6pm" />
        <Input label="Phone" type="tel" value={form.phone} onChange={set('phone')} maxLength={30} placeholder="e.g. +65 6123 4567" />
        <Input
          label="Auto-approve orders up to (S$)"
          inputMode="decimal"
          value={form.auto_approve_limit}
          onChange={set('auto_approve_limit')}
          error={errors.auto_approve_limit}
          hint="Bigger or risky orders wait for your one-tap approval."
          className="font-mono"
        />
        <Button type="submit" variant="secondary" loading={busy} disabled={!changed.length} className="self-start">
          {changed.length ? 'Save details' : 'Saved'}
        </Button>
      </form>
    </Card>
  )
}

/* ------------------------------------------------------------------ product editor */

interface Draft {
  name: string
  name_local: string
  category: string
  base_price: string
  unit: string
  variants: { label: string; price: string }[]
  options: { name: string; choices: string }[]
  available: boolean
  description: string
}

function toDraft(p: Partial<Product>): Draft {
  return {
    name: p.name ?? '',
    name_local: p.name_local ?? '',
    category: p.category ?? '',
    base_price: p.base_price ?? '',
    unit: p.unit ?? '',
    variants: (p.variants ?? []).map((v) => ({ ...v })),
    options: (p.options ?? []).map((o) => ({ name: o.name, choices: o.choices.join(', ') })),
    available: p.available ?? true,
    description: p.description ?? '',
  }
}

function validate(d: Draft): { input?: ProductInput; error?: string } {
  if (!d.name.trim()) return { error: 'Give the item a name.' }
  const variants = d.variants.filter((v) => v.label.trim() || v.price.trim())
  if (variants.some((v) => !v.label.trim())) return { error: 'Every pack or size needs a label, like "20 pcs".' }
  if (variants.some((v) => !MONEY.test(v.price.trim()))) return { error: 'Pack prices must look like 16 or 16.50.' }
  const base = d.base_price.trim()
  if (!variants.length && base && !MONEY.test(base)) return { error: 'The price must look like 12 or 12.50.' }
  const options = d.options
    .filter((o) => o.name.trim())
    .map((o) => ({ name: o.name.trim(), choices: o.choices.split(',').map((c) => c.trim()).filter(Boolean) }))
  return {
    input: {
      name: d.name.trim(),
      name_local: d.name_local.trim(),
      category: d.category.trim(),
      base_price: variants.length ? null : base || null,
      unit: variants.length ? '' : d.unit.trim(),
      variants: variants.map((v) => ({ label: v.label.trim(), price: v.price.trim() })),
      options,
      available: d.available,
      description: d.description.trim(),
    },
  }
}

function ProductEditor({
  shopId,
  product,
  defaultCategory,
  categories,
  onSaved,
  onDeleted,
  onClose,
}: {
  shopId: string
  product?: Product
  defaultCategory?: string
  categories: string[]
  onSaved: (p: Product) => void
  onDeleted?: (id: string) => void
  onClose: () => void
}) {
  const toast = useToast()
  const [d, setD] = useState<Draft>(() => toDraft(product ?? { category: defaultCategory }))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const firstRef = useRef<HTMLDivElement>(null)
  const listId = `cats-${product?.id ?? 'new'}`

  useEffect(() => {
    firstRef.current?.querySelector('input')?.focus()
  }, [])

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }))

  async function save(e: FormEvent) {
    e.preventDefault()
    const { input, error: problem } = validate(d)
    if (!input) return setError(problem ?? null)
    setError(null)
    setBusy(true)
    try {
      const saved = product
        ? await api<Product>(`/api/shops/${shopId}/products/${product.id}`, { method: 'PUT', json: input })
        : await api<Product>(`/api/shops/${shopId}/products`, { method: 'POST', json: input })
      onSaved(saved)
      toast.show(`${saved.name} saved.`, 'success')
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!product || !onDeleted) return
    setBusy(true)
    try {
      await api(`/api/shops/${shopId}/products/${product.id}`, { method: 'DELETE' })
      onDeleted(product.id)
      toast.show(`${product.name} removed.`, 'success')
    } catch (err) {
      setError(errorText(err))
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={save}
      noValidate
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
      className="my-2 flex flex-col gap-4 border-2 border-ink bg-paper p-3 sm:p-4"
      aria-label={product ? `Edit ${product.name}` : 'New item'}
    >
      <div ref={firstRef} className="grid gap-3 sm:grid-cols-2">
        <Input label="Item name" value={d.name} onChange={(e) => set('name', e.target.value)} maxLength={80} />
        <Input label="Local name (optional)" value={d.name_local} onChange={(e) => set('name_local', e.target.value)} maxLength={80} placeholder="e.g. 九层糕" />
        <Input label="Category" value={d.category} onChange={(e) => set('category', e.target.value)} list={listId} maxLength={60} />
        <datalist id={listId}>
          {categories.map((c) => (
            <option key={c} value={c} />
          ))}
        </datalist>
      </div>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 text-sm font-semibold">Price</legend>
        {d.variants.length === 0 ? (
          <div className="grid grid-cols-2 gap-3">
            <Input label="Price (S$)" inputMode="decimal" value={d.base_price} onChange={(e) => set('base_price', e.target.value)} placeholder="e.g. 12.50" />
            <Input label="Per" value={d.unit} onChange={(e) => set('unit', e.target.value)} placeholder="e.g. 10 pcs" maxLength={40} />
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {d.variants.map((v, i) => (
              <li key={i} className="grid grid-cols-[1fr_7rem_auto] items-end gap-2">
                <Input
                  label={i === 0 ? 'Pack or size' : <span className="sr-only">Pack or size {i + 1}</span>}
                  value={v.label}
                  onChange={(e) => set('variants', d.variants.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))}
                  placeholder="e.g. 20 pcs"
                  maxLength={40}
                />
                <Input
                  label={i === 0 ? 'S$' : <span className="sr-only">Price {i + 1}</span>}
                  inputMode="decimal"
                  value={v.price}
                  onChange={(e) => set('variants', d.variants.map((x, j) => (j === i ? { ...x, price: e.target.value } : x)))}
                  placeholder="16.00"
                />
                <Button
                  variant="ghost"
                  size="md"
                  aria-label={`Remove ${v.label || 'this pack'}`}
                  icon={<X aria-hidden className="size-4" />}
                  onClick={() => set('variants', d.variants.filter((_, j) => j !== i))}
                />
              </li>
            ))}
          </ul>
        )}
        <Button
          variant="secondary"
          size="sm"
          className="self-start"
          icon={<Plus aria-hidden className="size-4" />}
          onClick={() =>
            set(
              'variants',
              d.variants.length
                ? [...d.variants, { label: '', price: '' }]
                : [{ label: d.unit, price: d.base_price }, { label: '', price: '' }],
            )
          }
        >
          {d.variants.length ? 'Add pack or size' : 'Sold in packs or sizes'}
        </Button>
      </fieldset>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 text-sm font-semibold">Choices (flavours, spice level…)</legend>
        {d.options.map((o, i) => (
          <div key={i} className="grid grid-cols-[8rem_1fr_auto] items-end gap-2 sm:grid-cols-[10rem_1fr_auto]">
            <Input
              label={i === 0 ? 'Name' : <span className="sr-only">Choice name {i + 1}</span>}
              value={o.name}
              onChange={(e) => set('options', d.options.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))}
              placeholder="e.g. Flavour"
              maxLength={40}
            />
            <Input
              label={i === 0 ? 'Choices, separated by commas' : <span className="sr-only">Choices {i + 1}</span>}
              value={o.choices}
              onChange={(e) => set('options', d.options.map((x, j) => (j === i ? { ...x, choices: e.target.value } : x)))}
              placeholder="e.g. Pandan, Gula Melaka"
            />
            <Button
              variant="ghost"
              aria-label={`Remove ${o.name || 'this choice'}`}
              icon={<X aria-hidden className="size-4" />}
              onClick={() => set('options', d.options.filter((_, j) => j !== i))}
            />
          </div>
        ))}
        <Button
          variant="secondary"
          size="sm"
          className="self-start"
          icon={<Plus aria-hidden className="size-4" />}
          onClick={() => set('options', [...d.options, { name: '', choices: '' }])}
        >
          Add choice
        </Button>
      </fieldset>

      <Textarea label="Description (optional)" value={d.description} onChange={(e) => set('description', e.target.value)} maxLength={300} rows={2} />
      <Toggle checked={d.available} onChange={(v) => set('available', v)} label="Available" hint="Turn off when sold out. Agents won't offer it." />

      {error && (
        <p role="alert" className="border-2 border-ink border-l-8 border-l-chili bg-receipt px-3 py-2 font-semibold">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" loading={busy}>
          {product ? 'Save item' : 'Add item'}
        </Button>
        <Button variant="ghost" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        {product && onDeleted && (
          <div className="ml-auto flex items-center gap-2">
            {confirmDelete ? (
              <>
                <span className="text-sm font-semibold">Delete this item?</span>
                <Button size="sm" onClick={remove} loading={busy}>
                  Yes, delete
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(false)}>
                  No
                </Button>
              </>
            ) : (
              <Button variant="ghost" size="sm" icon={<Trash2 aria-hidden className="size-4" />} onClick={() => setConfirmDelete(true)}>
                Delete
              </Button>
            )}
          </div>
        )}
      </div>
    </form>
  )
}

/* ------------------------------------------------------------------ product row */

function ProductRow({
  shopId,
  product,
  categories,
  editing,
  onEdit,
  onClose,
  onSaved,
  onDeleted,
}: {
  shopId: string
  product: Product
  categories: string[]
  editing: boolean
  onEdit: () => void
  onClose: () => void
  onSaved: (p: Product) => void
  onDeleted: (id: string) => void
}) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)

  async function setAvailable(available: boolean) {
    setBusy(true)
    try {
      const { input } = validate({ ...toDraft(product), available })
      if (!input) return
      onSaved(await api<Product>(`/api/shops/${shopId}/products/${product.id}`, { method: 'PUT', json: input }))
    } catch (err) {
      toast.show(errorText(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  if (editing) {
    return (
      <li>
        <ProductEditor shopId={shopId} product={product} categories={categories} onSaved={onSaved} onDeleted={onDeleted} onClose={onClose} />
      </li>
    )
  }
  return (
    <li className={cx('border-b-2 border-dotted border-muted/50 py-2 last:border-b-0', needsCheck(product) && '-mx-2 bg-turmeric-tint px-2')}>
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-3">
        <div className="min-w-0 flex-1">
          <MenuLines product={product} />
          {needsCheck(product) && <Stamp kind="check" size="sm" className="mt-1 hidden sm:inline-flex" />}
        </div>
        <div className="flex items-center gap-2">
          {needsCheck(product) && <Stamp kind="check" size="sm" className="sm:hidden" />}
          <Toggle
            className="ml-auto pt-0.5"
            checked={product.available}
            onChange={setAvailable}
            disabled={busy}
            label={<span className="sr-only">Available</span>}
            aria-label={`${product.name}: available`}
            title={product.available ? 'Available. Tap to mark sold out.' : 'Sold out. Tap to make available.'}
          />
          <Button variant="ghost" size="sm" aria-label={`Edit ${product.name}`} icon={<Pencil aria-hidden className="size-4" />} onClick={onEdit} />
        </div>
      </div>
    </li>
  )
}

/* ------------------------------------------------------------------ add photo */

function AddPhotoPanel({ shopId, onAdded, onClose }: { shopId: string; onAdded: (p: Product[]) => void; onClose: () => void }) {
  const [files, setFiles] = useState<File[]>([])
  const [photos, setPhotos] = useState<string[]>([])
  const [phase, setPhase] = useState<ScanPhase | 'idle'>('idle')
  const [result, setResult] = useState<DraftResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const ctrlRef = useRef<AbortController | null>(null)

  useEffect(() => () => photos.forEach((u) => URL.revokeObjectURL(u)), [photos])
  useEffect(() => () => ctrlRef.current?.abort(), [])

  async function upload(list: File[]) {
    const ctrl = new AbortController()
    ctrlRef.current = ctrl
    setPhase('reading')
    const form = new FormData()
    list.forEach((f) => form.append('images', f, f.name))
    try {
      const res = await api<DraftResponse>(`/api/shops/${shopId}/photos`, { method: 'POST', form, timeoutMs: PHOTO_TIMEOUT_MS, signal: ctrl.signal })
      setResult(res)
      setPhase('done')
      onAdded(res.products)
    } catch (err) {
      if (ctrl.signal.aborted) return
      setError(errorText(err))
      setPhase('error')
    }
  }

  return (
    <Card tone="paper" className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-2xl">Add another photo</h2>
        <Button variant="ghost" size="sm" icon={<X aria-hidden className="size-4" />} onClick={onClose}>
          Close
        </Button>
      </div>
      {phase === 'idle' ? (
        <PhotoDrop
          compact
          title="Drop another menu photo"
          onFiles={(list) => {
            setFiles(list)
            setPhotos(list.map((f) => URL.createObjectURL(f)))
            void upload(list)
          }}
        />
      ) : (
        <ScanView
          photos={photos}
          phase={phase}
          products={result?.products ?? []}
          warnings={result?.warnings}
          error={error}
          onRetry={() => void upload(files)}
          onCancel={onClose}
          onContinue={onClose}
          continueLabel="Done, back to my menu"
        />
      )}
    </Card>
  )
}

/* ------------------------------------------------------------------ page */

export function CatalogReview() {
  const { data, setData, shopId } = useShop()
  const [editing, setEditing] = useState<string | null>(null) // product id, or "new:<category>"
  const [addingPhoto, setAddingPhoto] = useState(false)
  const [goingLive, setGoingLive] = useState(false)

  useEffect(() => {
    document.documentElement.style.setProperty('--toast-lift', '4.5rem')
    return () => {
      document.documentElement.style.removeProperty('--toast-lift')
    }
  }, [])

  const detail = data!
  const { shop, products } = detail

  const groups = useMemo(() => {
    const byCat = new Map<string, Product[]>()
    for (const p of products) {
      const c = p.category.trim() || NO_CATEGORY
      byCat.set(c, [...(byCat.get(c) ?? []), p])
    }
    const list = [...byCat.entries()].map(([category, items]) => ({
      category,
      items: [...items].sort((a, b) => Number(needsCheck(b)) - Number(needsCheck(a))),
      checks: items.filter(needsCheck).length,
    }))
    return list.sort((a, b) => Number(b.checks > 0) - Number(a.checks > 0))
  }, [products])
  const categories = groups.map((g) => g.category).filter((c) => c !== NO_CATEGORY)
  const toCheck = products.filter(needsCheck).length

  const update = (fn: (d: ShopDetail) => ShopDetail) => setData((prev) => (prev ? fn(prev) : prev))
  const saved = (p: Product) => {
    update((d) => ({
      ...d,
      products: d.products.some((x) => x.id === p.id) ? d.products.map((x) => (x.id === p.id ? p : x)) : [...d.products, p],
    }))
    setEditing(null)
  }
  const deleted = (id: string) => {
    update((d) => ({ ...d, products: d.products.filter((x) => x.id !== id) }))
    setEditing(null)
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] lg:items-start">
        <div>
          <ShopDetailsForm key={shop.id} shop={shop} onSaved={(s) => update((d) => ({ ...d, shop: s }))} />
        </div>

        <section aria-labelledby="menu-heading" className="flex flex-col gap-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="menu-heading" className="text-3xl">
                Your menu
              </h2>
              <p className="text-ink-soft">
                {toCheck > 0
                  ? toCheck === 1
                    ? "1 item marked CHECK: we weren't sure we read it right."
                    : `${toCheck} items marked CHECK: we weren't sure we read them right.`
                  : 'Tap the pencil to fix a name, price, pack or flavour.'}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" size="sm" icon={<Plus aria-hidden className="size-4" />} onClick={() => setEditing('new:')}>
                Add item
              </Button>
              <Button variant="secondary" size="sm" icon={<ImagePlus aria-hidden className="size-4" />} onClick={() => setAddingPhoto(true)}>
                Add another photo
              </Button>
            </div>
          </div>

          {addingPhoto && (
            <AddPhotoPanel
              shopId={shopId}
              onAdded={(added) => update((d) => ({ ...d, products: [...d.products, ...added] }))}
              onClose={() => setAddingPhoto(false)}
            />
          )}

          {editing === 'new:' && (
            <ReceiptCard>
              <h3 className="text-xl">New item</h3>
              <ProductEditor shopId={shopId} categories={categories} onSaved={saved} onClose={() => setEditing(null)} />
            </ReceiptCard>
          )}

          {products.length === 0 && editing !== 'new:' && (
            <EmptyState
              message="No items yet. Add another photo, or add items by hand."
              action={
                <Button icon={<Plus aria-hidden className="size-4" />} onClick={() => setEditing('new:')}>
                  Add item
                </Button>
              }
            />
          )}

          {groups.map((g) => (
            <ReceiptCard key={g.category} aria-labelledby={`cat-${g.category}`}>
              <div className="flex items-baseline justify-between gap-3">
                <h3 id={`cat-${g.category}`} className="text-xl uppercase">
                  {g.category}
                </h3>
                <span className="font-mono text-xs text-muted">
                  {g.items.length} item{g.items.length === 1 ? '' : 's'}
                </span>
              </div>
              <ReceiptDivider />
              <ul>
                {g.items.map((p) => (
                  <ProductRow
                    key={p.id}
                    shopId={shopId}
                    product={p}
                    categories={categories}
                    editing={editing === p.id}
                    onEdit={() => setEditing(p.id)}
                    onClose={() => setEditing(null)}
                    onSaved={saved}
                    onDeleted={deleted}
                  />
                ))}
              </ul>
              {editing === `new:${g.category}` ? (
                <ProductEditor
                  shopId={shopId}
                  categories={categories}
                  defaultCategory={g.category === NO_CATEGORY ? '' : g.category}
                  onSaved={saved}
                  onClose={() => setEditing(null)}
                />
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-2"
                  icon={<Plus aria-hidden className="size-4" />}
                  onClick={() => setEditing(`new:${g.category}`)}
                >
                  Add to {g.category}
                </Button>
              )}
            </ReceiptCard>
          ))}
        </section>
      </div>

      {/* Sticky go-live bar */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t-2 border-ink bg-receipt">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <p className="min-w-0 font-mono text-sm">
            <span className="font-semibold">{products.length} items</span>
            {toCheck > 0 && <span className="text-ink-soft"> · {toCheck} to check</span>}
            {shop.published && <span className="hidden text-ink-soft sm:inline"> · live at /s/{shop.slug}</span>}
          </p>
          {shop.published ? (
            <Link to={`/shop/${shopId}/live`} className={buttonClass('approve', 'md')}>
              Your shop is live <ArrowRight aria-hidden className="size-4" />
            </Link>
          ) : (
            <Button size="lg" onClick={() => setGoingLive(true)} disabled={!products.length}>
              Go live <ArrowRight aria-hidden className="size-5" />
            </Button>
          )}
        </div>
      </div>
      {goingLive && <GoLiveDialog shopId={shopId} defaultName={shop.name} onClose={() => setGoingLive(false)} onLive={setData} />}
    </>
  )
}
