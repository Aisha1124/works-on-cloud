import { PauseCircle, Save } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { api, errorText } from '../lib/api'
import { useShop } from '../lib/shop'
import type { DayHours, Shop, ShopDetail } from '../lib/types'
import { Button, Card, Input, Skeleton, Toggle, cx, useToast } from '../ui'

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

interface Form {
  hours: DayHours[]
  minNotice: string
  capacity: string
  timeout: string
  cutoff: string
  limit: string
  paused: boolean
  pausedUntil: string
}

function formOf(detail: ShopDetail): Form {
  const s = detail.shop
  return {
    hours: detail.opening_hours ?? DAY_NAMES.map((_, day) => ({ day, closed: false, open: '09:00', close: '18:00' })),
    minNotice: String(s.min_notice_hours),
    capacity: s.daily_capacity == null ? '' : String(s.daily_capacity),
    timeout: String(s.approval_timeout_hours),
    cutoff: String(s.cancel_cutoff_hours),
    limit: s.auto_approve_limit,
    paused: !!s.paused_until,
    pausedUntil: s.paused_until ?? '',
  }
}

/** "2026-10-17" for today in Singapore, so the pause date can't be in the past. */
function todaySg(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Singapore' }).format(new Date())
}

const whole = (v: string, min: number, max: number) => /^\d+$/.test(v.trim()) && +v >= min && +v <= max

function check(f: Form): Record<string, string> {
  const e: Record<string, string> = {}
  if (!whole(f.minNotice, 0, 336)) e.minNotice = 'A whole number of hours, 0 to 336.'
  if (f.capacity.trim() && !whole(f.capacity, 1, 1000)) e.capacity = 'Leave empty for no limit, or 1 to 1000.'
  if (!whole(f.timeout, 1, 168)) e.timeout = 'A whole number of hours, 1 to 168.'
  if (!whole(f.cutoff, 0, 168)) e.cutoff = 'A whole number of hours, 0 to 168.'
  if (!/^\d{1,6}(\.\d{1,2})?$/.test(f.limit.trim())) e.limit = 'An amount like 150 or 150.00.'
  if (f.hours.every((d) => d.closed)) e.hours = 'Open at least one day. To stop orders for a while, pause orders below.'
  else if (f.hours.some((d) => !d.closed && d.open === d.close)) e.hours = "Opening and closing time can't be the same."
  if (f.paused && !f.pausedUntil) e.pausedUntil = 'Pick the day you take orders again.'
  return e
}

/** Owner settings that decide which orders come in: opening hours, notice, daily limit,
 *  approval timeout, cancel cutoff, auto-approve limit, and pausing orders. */
export function Settings() {
  const { data, shopId, setData, reload } = useShop()
  const [form, setForm] = useState<Form | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  if (!data) return <Skeleton rows={6} label="Loading settings" />
  const f = form ?? formOf(data)
  const set = (patch: Partial<Form>) => setForm({ ...f, ...patch })
  const setDay = (day: number, patch: Partial<DayHours>) => set({ hours: f.hours.map((d) => (d.day === day ? { ...d, ...patch } : d)) })

  async function save(e: FormEvent) {
    e.preventDefault()
    const errs = check(f)
    setErrors(errs)
    if (Object.keys(errs).length) return
    setBusy(true)
    try {
      const shop = await api<Shop>(`/api/shops/${encodeURIComponent(shopId)}`, {
        method: 'PATCH',
        json: {
          opening_hours: f.hours,
          min_notice_hours: +f.minNotice,
          daily_capacity: f.capacity.trim() ? +f.capacity : null,
          approval_timeout_hours: +f.timeout,
          cancel_cutoff_hours: +f.cutoff,
          auto_approve_limit: f.limit.trim(),
          paused_until: f.paused ? f.pausedUntil : null,
        },
      })
      setData((prev) => (prev ? { ...prev, shop } : prev))
      setForm(null)
      reload() // the hours table comes back from the server, as saved
      toast.show('Settings saved.', 'success')
    } catch (err) {
      toast.show(errorText(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={save} noValidate className="flex flex-col gap-6" aria-labelledby="settings-heading">
      <h2 id="settings-heading" className="text-3xl">
        Ordering settings
      </h2>

      <Card className="flex flex-col gap-4" role="group" aria-labelledby="pause-heading">
        <h3 id="pause-heading" className="flex items-center gap-2 text-xl">
          <PauseCircle aria-hidden className="size-5" /> Pause orders
        </h3>
        <Toggle
          checked={f.paused}
          onChange={(paused) => set({ paused })}
          label="Pause orders until a date"
          hint="Your shop page, AI agents and llms.txt will say you're not taking orders until then. Orders you already have stay."
        />
        {f.paused && (
          <Input
            label="Take orders again from"
            type="date"
            min={todaySg()}
            value={f.pausedUntil}
            onChange={(e) => set({ pausedUntil: e.target.value })}
            error={errors.pausedUntil}
            className="max-w-xs"
          />
        )}
      </Card>

      <Card className="flex flex-col gap-3" role="group" aria-labelledby="hours-heading">
        <h3 id="hours-heading" className="text-xl">
          Opening hours
        </h3>
        <p className="text-sm text-ink-soft">Customers and AI agents can only pick a pickup time inside these hours (Singapore time).</p>
        {data.hours_readable === false && (
          <p className="border-2 border-ink bg-turmeric-tint p-3 text-sm">
            We couldn't read your hours{data.shop.hours ? ` (“${data.shop.hours}”)` : ''}, so we use 9am to 6pm every day until you save hours here.
          </p>
        )}
        <ul className="flex flex-col divide-y-2 divide-dashed divide-ink/30">
          {f.hours.map((d) => (
            <li key={d.day} className="grid grid-cols-[7.5rem_1fr] items-center gap-x-3 gap-y-2 py-2 sm:grid-cols-[9rem_auto_1fr]">
              <span className="font-semibold">{DAY_NAMES[d.day]}</span>
              <Toggle checked={!d.closed} onChange={(open) => setDay(d.day, { closed: !open })} label={d.closed ? 'Closed' : 'Open'} aria-label={`${DAY_NAMES[d.day]} open`} />
              <div className={cx('col-span-2 flex items-center gap-2 sm:col-span-1', d.closed && 'invisible')}>
                <input
                  type="time"
                  className="control max-w-36 font-mono"
                  aria-label={`${DAY_NAMES[d.day]} opens`}
                  value={d.open}
                  onChange={(e) => setDay(d.day, { open: e.target.value })}
                  disabled={d.closed}
                />
                <span aria-hidden>to</span>
                <input
                  type="time"
                  className="control max-w-36 font-mono"
                  aria-label={`${DAY_NAMES[d.day]} closes`}
                  value={d.close}
                  onChange={(e) => setDay(d.day, { close: e.target.value })}
                  disabled={d.closed}
                />
              </div>
            </li>
          ))}
        </ul>
        {errors.hours && (
          <p role="alert" className="font-semibold text-chili">
            {errors.hours}
          </p>
        )}
      </Card>

      <Card className="grid grid-cols-1 gap-4 sm:grid-cols-2" role="group" aria-labelledby="rules-heading">
        <h3 id="rules-heading" className="text-xl sm:col-span-2">
          Order rules
        </h3>
        <Input label="Minimum notice (hours)" inputMode="numeric" value={f.minNotice} onChange={(e) => set({ minNotice: e.target.value })} error={errors.minNotice} hint="How long before pickup an order must come in. 24 = order by this time tomorrow." />
        <Input label="Most orders per pickup day" inputMode="numeric" placeholder="No limit" value={f.capacity} onChange={(e) => set({ capacity: e.target.value })} error={errors.capacity} hint="When a day is full, it isn't offered. Leave empty for no limit." />
        <Input label="Auto-approve orders up to (S$)" inputMode="decimal" className="font-mono" value={f.limit} onChange={(e) => set({ limit: e.target.value })} error={errors.limit} hint="Bigger orders wait for your OK." />
        <Input label="Answer held orders within (hours)" inputMode="numeric" value={f.timeout} onChange={(e) => set({ timeout: e.target.value })} error={errors.timeout} hint="If you don't approve or reject in time, the order is rejected and the customer is told." />
        <Input label="Customers can cancel until (hours before pickup)" inputMode="numeric" value={f.cutoff} onChange={(e) => set({ cutoff: e.target.value })} error={errors.cutoff} hint="You get an email when someone cancels." />
      </Card>

      <div className="sticky bottom-4 flex justify-end">
        <Button type="submit" size="lg" loading={busy} icon={<Save aria-hidden className="size-5" />}>
          Save settings
        </Button>
      </div>
    </form>
  )
}
