import { Check, Printer, RotateCcw, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import {
  Button,
  Card,
  EmptyState,
  Input,
  PriceTag,
  ReceiptCard,
  ReceiptDivider,
  ReceiptRow,
  ReceiptTotal,
  RiskMeter,
  Select,
  Signboard,
  Skeleton,
  Stamp,
  Textarea,
  TimelineRow,
  Toggle,
  buttonClass,
  useToast,
  type Actor,
  type ButtonVariant,
  type StampKind,
} from '../ui'

const sections = [
  ['tokens', 'Colours & type'],
  ['buttons', 'Button'],
  ['fields', 'Input, Textarea, Select'],
  ['toggle', 'Toggle'],
  ['cards', 'Card & ReceiptCard'],
  ['stamps', 'Stamp'],
  ['risk', 'RiskMeter'],
  ['prices', 'PriceTag'],
  ['feedback', 'Toast, Skeleton, EmptyState'],
  ['timeline', 'Timeline'],
  ['signboard', 'Signboard'],
] as const

const swatches = [
  ['--paper', '#F4EDE1', 'Page background'],
  ['--receipt', '#FFFDF8', 'Cards, receipts, inputs'],
  ['--ink', '#1C1A17', 'Text, borders, shadows'],
  ['--chili', '#D7261E', 'Primary, danger, rejected'],
  ['--pandan', '#2F7D4F', 'Approved, success'],
  ['--turmeric', '#F2B705', 'Pending, highlight, focus ring'],
  ['--muted', '#7A7064', 'Secondary text on receipt only'],
] as const

// Clearly sample data for the styleguide. Not a real shop or real orders.
const sampleAudit: Array<{ at: string; actor: Actor; action: string; summary: string }> = [
  { at: '2026-10-17T02:14:09Z', actor: 'owner', action: 'order.approved', summary: 'Owner approved order 7f3a9c after a call.' },
  { at: '2026-10-17T02:11:52Z', actor: 'risk_agent', action: 'risk.scored', summary: 'Scored 82 (high): new phone number, pickup in 40 minutes, note asks to skip checks.' },
  { at: '2026-10-17T02:11:50Z', actor: 'external_agent', action: 'order.placed', summary: 'Order for 300 pcs kuih lapis received through UCP.' },
  { at: '2026-10-17T01:40:03Z', actor: 'shopper_agent', action: 'order.placed', summary: 'Demo shopper ordered 50 pcs kuih lapis for Saturday pickup.' },
  { at: '2026-10-17T01:02:31Z', actor: 'catalog_agent', action: 'catalog.extracted', summary: 'Read 14 items from the price-list photo; 2 marked for review.' },
  { at: '2026-10-17T01:00:00Z', actor: 'system', action: 'shop.created', summary: 'Shop created.' },
]

function Section({ id, title, note, children }: { id: string; title: string; note?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="scroll-mt-6">
      <h2 id={`${id}-h`} className="text-2xl sm:text-3xl">
        {title}
      </h2>
      {note && <p className="mt-1 max-w-2xl text-ink-soft">{note}</p>}
      <div className="mt-4">{children}</div>
    </section>
  )
}

/** A labelled example of one state. */
function State({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <figure className={className}>
      <figcaption className="mb-2 font-mono text-xs tracking-widest text-ink-soft uppercase">{label}</figcaption>
      {children}
    </figure>
  )
}

function ButtonRow({ variant }: { variant: ButtonVariant }) {
  return (
    <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
      <State label="default"><Button variant={variant}>Publish shop</Button></State>
      <State label="hover"><Button variant={variant} data-force="hover">Publish shop</Button></State>
      <State label="pressed"><Button variant={variant} data-force="active">Publish shop</Button></State>
      <State label="focus"><Button variant={variant} data-force="focus">Publish shop</Button></State>
      <State label="disabled"><Button variant={variant} disabled>Publish shop</Button></State>
      <State label="loading"><Button variant={variant} loading>Publishing</Button></State>
      <State label="small + icon"><Button variant={variant} size="sm" icon={<Check aria-hidden className="size-4" />}>Approve</Button></State>
    </div>
  )
}

export function Styleguide() {
  const toast = useToast()
  const [toggles, setToggles] = useState({ a: true, b: false })
  const [stampKey, setStampKey] = useState(0)
  const [meterKey, setMeterKey] = useState(0)

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-10">
      <Signboard
        plate="Design system"
        title="Hawker Receipt"
        subtitle="Every KampungCart component, in every state."
        actions={<Link to="/" className={buttonClass('secondary', 'sm')}>Home</Link>}
      />

      <div className="mt-8 grid gap-10 lg:grid-cols-[13rem_1fr]">
        <nav aria-label="Styleguide sections" className="lg:sticky lg:top-6 lg:self-start">
          <ul className="flex flex-wrap gap-2 lg:flex-col lg:gap-1">
            {sections.map(([id, label]) => (
              <li key={id}>
                <a href={`#${id}`} className="inline-block border-2 border-ink bg-receipt px-2 py-1 text-sm font-medium hover:bg-turmeric lg:border-0 lg:bg-transparent lg:px-1">
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <main className="flex min-w-0 flex-col gap-14">
          <Section id="tokens" title="Colours & type" note="Turmeric and muted never carry text on paper; they fail AA there.">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 xl:grid-cols-7">
              {swatches.map(([name, hex, use]) => (
                <div key={name} className="border-2 border-ink bg-receipt shadow-hard-sm">
                  <div className="h-16 border-b-2 border-ink" style={{ background: `var(${name})` }} />
                  <div className="p-2">
                    <div className="font-mono text-sm font-semibold">{name}</div>
                    <div className="font-mono text-xs text-muted">{hex}</div>
                    <div className="mt-1 text-xs">{use}</div>
                  </div>
                </div>
              ))}
            </div>
            <Card className="mt-6 flex flex-col gap-3">
              <p className="font-display text-4xl font-extrabold">Bricolage Grotesque 800</p>
              <p className="font-display text-2xl font-bold">Bricolage Grotesque 700 for headings</p>
              <p className="text-lg">Instrument Sans for body copy. Kuih lapis, 九层糕, kueh, கேக்.</p>
              <p className="font-mono">IBM Plex Mono · S$42.50 · ORDER 7f3a9c · 17 Oct 10:14:09 SGT</p>
            </Card>
          </Section>

          <Section id="buttons" title="Button" note="Hard shadow, lifts on hover, presses into its shadow on click.">
            <div className="flex flex-col gap-8">
              <div><h3 className="mb-3 text-lg">Primary</h3><ButtonRow variant="primary" /></div>
              <div><h3 className="mb-3 text-lg">Secondary</h3><ButtonRow variant="secondary" /></div>
              <div><h3 className="mb-3 text-lg">Ghost</h3><ButtonRow variant="ghost" /></div>
            </div>
          </Section>

          <Section id="fields" title="Input, Textarea, Select">
            <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
              <State label="default"><Input label="Shop name" placeholder="e.g. Ah Ma Kuih" hint="Shown to AI agents and customers." /></State>
              <State label="hover"><Input label="Shop name" defaultValue="Ah Ma Kuih" data-force="hover" /></State>
              <State label="focus"><Input label="Shop name" defaultValue="Ah Ma Kuih" data-force="focus" /></State>
              <State label="error"><Input label="Phone" defaultValue="9123" error="Singapore numbers have 8 digits." /></State>
              <State label="disabled"><Input label="Currency" defaultValue="SGD" disabled /></State>
              <State label="loading"><Input label="Slug" defaultValue="ah-ma-kuih" readOnly aria-busy="true" hint="Checking if the name is free…" /></State>
              <State label="textarea default"><Textarea label="Tagline" placeholder="One line about your shop" /></State>
              <State label="textarea focus"><Textarea label="Note to customers" defaultValue="Order 2 days ahead for big trays." data-force="focus" /></State>
              <State label="textarea disabled"><Textarea label="Note" defaultValue="Locked while publishing" disabled /></State>
              <State label="select default">
                <Select label="Shop type" defaultValue="bakery">
                  <option value="bakery">Home bakery</option>
                  <option value="hawker">Hawker stall</option>
                  <option value="provision">Provision shop</option>
                </Select>
              </State>
              <State label="select hover">
                <Select label="Category" defaultValue="kuih" data-force="hover">
                  <option value="kuih">Kuih</option>
                </Select>
              </State>
              <State label="select error">
                <Select label="Unit" defaultValue="" error="Pick a unit for this item.">
                  <option value="">Choose…</option>
                  <option value="pc">per piece</option>
                </Select>
              </State>
            </div>
          </Section>

          <Section id="toggle" title="Toggle">
            <div className="flex flex-wrap gap-x-10 gap-y-6">
              <State label="on"><Toggle label="Available" checked={toggles.a} onChange={(a) => setToggles((t) => ({ ...t, a }))} /></State>
              <State label="off"><Toggle label="Published" hint="AI agents can find this shop" checked={toggles.b} onChange={(b) => setToggles((t) => ({ ...t, b }))} /></State>
              <State label="hover"><Toggle label="Available" checked={false} onChange={() => {}} data-force="hover" /></State>
              <State label="focus"><Toggle label="Available" checked onChange={() => {}} data-force="focus" /></State>
              <State label="disabled"><Toggle label="Available" checked={false} onChange={() => {}} disabled /></State>
            </div>
          </Section>

          <Section id="cards" title="Card & ReceiptCard" note="Sample data. The receipt's torn edge is a CSS mask; the outline and hard shadow follow it.">
            <div className="grid items-start gap-8 md:grid-cols-2">
              <State label="card">
                <Card>
                  <h3 className="text-xl">Today</h3>
                  <p className="mt-1 text-muted">2 orders waiting for you. Tap one to approve or reject.</p>
                </Card>
              </State>
              <State label="card · paper tone">
                <Card tone="paper">
                  <h3 className="text-xl">Auto-approve limit</h3>
                  <p className="mt-1 text-ink-soft">Orders up to <PriceTag value="150.00" /> go through on their own.</p>
                </Card>
              </State>
              <State label="receipt · bottom edge">
                <ReceiptCard>
                  <p className="text-center font-display text-xl font-extrabold">AH MA KUIH</p>
                  <p className="text-center font-mono text-xs text-muted">SAMPLE · ORDER 7f3a9c</p>
                  <ReceiptDivider />
                  <ReceiptRow label="Kuih lapis 九层糕 × 5" hint="10 pcs" value={<PriceTag value="42.50" />} />
                  <ReceiptRow label="Ondeh ondeh × 2" hint="6 pcs · pandan" value={<PriceTag value="9.00" />} />
                  <ReceiptRow label="Kueh dadar with an extra long name that wraps on phones × 1" value={<PriceTag value="5.50" />} />
                  <ReceiptDivider />
                  <ReceiptTotal value="S$57.00" />
                  <p className="mt-3 text-center font-mono text-xs text-muted">Pickup Sat 18 Oct · 10:00</p>
                </ReceiptCard>
              </State>
              <State label="receipt · both edges">
                <ReceiptCard edge="both">
                  <ReceiptRow label="Subtotal" value="S$57.00" />
                  <ReceiptRow label="Delivery" value="Pickup" />
                  <ReceiptTotal label="TO PAY" value="S$57.00" />
                  <div className="mt-4 flex justify-center"><Stamp kind="approved" size="lg" /></div>
                </ReceiptCard>
              </State>
            </div>
          </Section>

          <Section id="stamps" title="Stamp">
            <div className="flex flex-wrap items-center gap-8">
              {(['approved', 'held', 'rejected', 'check'] as StampKind[]).map((k) => (
                <State key={k} label={k}><Stamp kind={k} /></State>
              ))}
              <State label="small"><Stamp kind="held" size="sm" /></State>
              <State label="large"><Stamp kind="rejected" size="lg" /></State>
            </div>
            <div className="mt-6 flex flex-wrap items-center gap-6">
              <div key={stampKey} className="flex flex-wrap gap-6">
                <Stamp kind="approved" animate size="lg" />
                <Stamp kind="held" animate size="lg" />
              </div>
              <Button variant="secondary" size="sm" icon={<RotateCcw aria-hidden className="size-4" />} onClick={() => setStampKey((k) => k + 1)}>
                Replay landing
              </Button>
            </div>
          </Section>

          <Section id="risk" title="RiskMeter" note="Bands: low 0–39, medium 40–69, high 70+. The score comes from rules in Python.">
            <div key={meterKey} className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
              <State label="low · 12"><RiskMeter score={12} /></State>
              <State label="medium · 55"><RiskMeter score={55} /></State>
              <State label="high · 88"><RiskMeter score={88} /></State>
              <State label="loading"><RiskMeter score={null} /></State>
            </div>
            <Button className="mt-5" variant="secondary" size="sm" icon={<Printer aria-hidden className="size-4" />} onClick={() => setMeterKey((k) => k + 1)}>
              Reprint
            </Button>
          </Section>

          <Section id="prices" title="PriceTag" note="Display only. Totals are computed in Python as Decimal.">
            <div className="flex flex-wrap items-end gap-8">
              <State label="small"><PriceTag value="1.8" size="sm" /></State>
              <State label="default"><PriceTag value="42.50" /></State>
              <State label="large"><PriceTag value="1250" size="lg" /></State>
              <State label="boxed"><PriceTag value="8.50" boxed /></State>
              <State label="no price"><PriceTag value={null} /></State>
            </div>
          </Section>

          <Section id="feedback" title="Toast, Skeleton, EmptyState">
            <div className="flex flex-wrap gap-3">
              <Button variant="secondary" size="sm" icon={<Check aria-hidden className="size-4" />} onClick={() => toast.show('Order 7f3a9c approved. The shopper agent has been told.', 'success')}>
                Success toast
              </Button>
              <Button variant="secondary" size="sm" icon={<X aria-hidden className="size-4" />} onClick={() => toast.show("Couldn't read that photo. Try one with less glare.", 'error')}>
                Error toast
              </Button>
              <Button variant="secondary" size="sm" onClick={() => toast.show('Your shop is saved as a draft.', 'info')}>
                Info toast
              </Button>
            </div>
            <div className="mt-8 grid items-start gap-8 md:grid-cols-2">
              <State label="skeleton · printing"><Skeleton label="Loading catalog" /></State>
              <div className="flex flex-col gap-6">
                <State label="empty"><EmptyState message="No orders yet. They'll print here." /></State>
                <State label="empty + action">
                  <EmptyState message="No menu photo yet." action={<Button size="sm">Upload photo</Button>} />
                </State>
              </div>
            </div>
          </Section>

          <Section id="timeline" title="Timeline" note="Sample audit log. Times shown in Singapore time.">
            <Card>
              <ol>
                {sampleAudit.map((e, i) => (
                  <TimelineRow key={e.at + e.action} {...e} last={i === sampleAudit.length - 1} />
                ))}
              </ol>
            </Card>
          </Section>

          <Section id="signboard" title="Signboard">
            <div className="flex flex-col gap-6">
              <Signboard title="Ah Ma Kuih" subtitle="Sample shop · Nyonya kuih, made fresh" plate="#01-23" />
              <Signboard
                title="Orders"
                actions={
                  <>
                    <Button variant="secondary" size="sm">Export</Button>
                    <Button variant="secondary" size="sm">Settings</Button>
                  </>
                }
              />
            </div>
          </Section>
        </main>
      </div>
    </div>
  )
}
