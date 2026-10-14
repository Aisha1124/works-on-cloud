import { Bot, Cog, ScanText, ShieldAlert, ShoppingBag, User } from 'lucide-react'
import { cx } from './cx'

export type Actor = 'owner' | 'system' | 'catalog_agent' | 'risk_agent' | 'shopper_agent' | 'external_agent'

const actorInfo: Record<Actor, { label: string; Icon: typeof Bot; chip: string }> = {
  owner: { label: 'Owner', Icon: User, chip: 'bg-ink text-receipt border-ink' },
  system: { label: 'System', Icon: Cog, chip: 'bg-paper text-ink border-ink' },
  catalog_agent: { label: 'Catalog agent', Icon: ScanText, chip: 'bg-turmeric text-ink border-ink' },
  risk_agent: { label: 'Risk agent', Icon: ShieldAlert, chip: 'bg-chili text-receipt border-ink' },
  shopper_agent: { label: 'Shopper agent', Icon: ShoppingBag, chip: 'bg-pandan text-receipt border-ink' },
  external_agent: { label: 'External agent', Icon: Bot, chip: 'bg-receipt text-ink border-ink border-dashed' },
}

const timeFmt = new Intl.DateTimeFormat('en-SG', {
  timeZone: 'Asia/Singapore',
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

export interface TimelineRowProps {
  /** ISO timestamp from the backend. */
  at: string
  actor: Actor
  action: string
  summary: string
  /** Hide the connector line under the dot (last row). */
  last?: boolean
  className?: string
}

/** One audit-log event. Render a list of these inside an <ol>. */
export function TimelineRow({ at, actor, action, summary, last = false, className }: TimelineRowProps) {
  const { label, Icon, chip } = actorInfo[actor]
  const date = new Date(at)
  return (
    <li className={cx('grid grid-cols-[1.25rem_1fr] gap-x-3 sm:grid-cols-[9.5rem_1.25rem_1fr]', className)}>
      <time
        dateTime={at}
        className="col-span-2 pl-8 font-mono text-xs text-muted sm:col-span-1 sm:pt-1 sm:pl-0 sm:text-right"
      >
        {timeFmt.format(date)} SGT
      </time>
      <div className="relative flex justify-center" aria-hidden>
        <span className="relative z-10 mt-1.5 size-3 border-2 border-ink bg-receipt" />
        {!last && <span className="absolute top-5 bottom-0 border-l-2 border-dotted border-ink" />}
      </div>
      <div className={cx('min-w-0', last ? 'pb-1' : 'pb-5')}>
        <div className="flex flex-wrap items-center gap-2">
          <span className={cx('inline-flex items-center gap-1 border-2 px-1.5 py-0.5 text-xs font-semibold', chip)}>
            <Icon aria-hidden className="size-3.5" />
            {label}
          </span>
          <code className="font-mono text-xs">{action}</code>
        </div>
        <p className="mt-1 break-words">{summary}</p>
      </div>
    </li>
  )
}
