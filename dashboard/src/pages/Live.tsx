import { ArrowRight, Check, Copy, Download, ExternalLink, TriangleAlert } from 'lucide-react'
import { QRCodeCanvas } from 'qrcode.react'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { useShop } from '../lib/shop'
import { Button, Card, EmptyState, ReceiptCard, ReceiptDivider, Stamp, buttonClass, useToast } from '../ui'

function CopyLine({ label, value, explain, mono = true }: { label: string; value: string; explain?: string; mono?: boolean }) {
  const toast = useToast()
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
      toast.show(`${label} copied.`, 'success')
    } catch {
      toast.show("Couldn't copy. Select it and copy it by hand.", 'error')
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="font-mono text-xs tracking-widest text-muted uppercase">{label}</p>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
        <code className={`min-w-0 flex-1 border-2 border-ink bg-paper px-3 py-2.5 text-sm break-all ${mono ? 'font-mono' : ''}`}>{value}</code>
        <Button
          variant="secondary"
          onClick={copy}
          icon={copied ? <Check aria-hidden className="size-4" /> : <Copy aria-hidden className="size-4" />}
          aria-label={`Copy ${label}`}
        >
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>
      {explain && <p className="text-ink-soft">{explain}</p>}
    </div>
  )
}

/** The new owner key, straight after going live. It is never shown again. */
function OwnerKeyCard({ ownerKey }: { ownerKey: string }) {
  return (
    <section aria-labelledby="owner-key" className="flex flex-col gap-3 border-2 border-ink bg-turmeric-tint p-4 shadow-hard sm:p-5">
      <h2 id="owner-key" className="text-2xl">
        Your owner key
      </h2>
      <p role="note" className="flex items-start gap-2 font-semibold">
        <TriangleAlert aria-hidden className="mt-0.5 size-5 flex-none text-chili" />
        Save this, you need it to manage orders. We only show it once and can't show it again.
      </p>
      <CopyLine label="Owner key" value={ownerKey} />
      <p className="text-sm text-ink-soft">
        Keep it somewhere safe, like your phone's password manager. To get back in later, tap “Shop owner login” and paste it.
      </p>
    </section>
  )
}

function QrCard({ url, slug, name }: { url: string; slug: string; name: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const toast = useToast()

  function download() {
    const canvas = canvasRef.current
    if (!canvas) return
    try {
      const link = document.createElement('a')
      link.href = canvas.toDataURL('image/png')
      link.download = `${slug}-qr.png`
      link.click()
    } catch {
      toast.show("Couldn't save the QR code. Take a screenshot instead.", 'error')
    }
  }

  return (
    <Card className="flex flex-col items-start gap-4">
      <h2 className="text-2xl">Your shop QR code</h2>
      <div className="border-2 border-ink bg-receipt p-3 shadow-hard-sm">
        <QRCodeCanvas
          ref={canvasRef}
          value={url}
          size={512}
          marginSize={2}
          bgColor="#FFFDF8"
          fgColor="#1C1A17"
          level="M"
          title={`QR code for ${name}`}
          style={{ width: 176, height: 176 }}
        />
      </div>
      <p className="text-ink-soft">Print it for your stall or post it on Instagram. It opens your menu so customers can order.</p>
      <Button variant="secondary" onClick={download} icon={<Download aria-hidden className="size-4" />}>
        Download QR code
      </Button>
    </Card>
  )
}

export function Live() {
  const { data, shopId } = useShop()
  const { shop, links } = data!
  const location = useLocation()
  const navigate = useNavigate()
  // The key arrives once in router state from "Go live". Keep it for this visit only and
  // drop it from history, so a reload or Back doesn't show it again.
  const [ownerKey] = useState<string | null>(() => (location.state as { ownerKey?: string } | null)?.ownerKey ?? null)
  useEffect(() => {
    if (ownerKey) navigate(location.pathname, { replace: true, state: null })
  }, [ownerKey, navigate, location.pathname])

  if (!shop.published) {
    return (
      <EmptyState
        message="Your shop isn't live yet. Check your menu, then tap Go live."
        action={
          <Link to={`/shop/${shopId}`} className={buttonClass('primary')}>
            Back to my menu <ArrowRight aria-hidden className="size-4" />
          </Link>
        }
      />
    )
  }

  const publicPath = `/s/${shop.slug}`

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:items-start">
      <div className="flex min-w-0 flex-col gap-6">
        <ReceiptCard>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 className="text-3xl sm:text-4xl">{ownerKey ? 'You’re live!' : 'Your shop is live'}</h2>
            <Stamp kind="approved" label="Live" size="lg" animate={!!ownerKey} />
          </div>
          <p className="mt-2 text-ink-soft">
            Customers can order from your shop page, and AI shopping assistants can find {shop.name}, read your menu and place pickup
            orders. You approve anything unusual.
          </p>
          <ReceiptDivider />
          <div className="flex flex-col gap-6">
            {ownerKey && <OwnerKeyCard ownerKey={ownerKey} />}
            <CopyLine label="Your shop link" value={links.public_page} explain="Share it on WhatsApp or Instagram. No app or signup needed." />
            <div className="flex flex-wrap gap-3">
              <Link to={`/shop/${shopId}/orders`} className={buttonClass('primary', 'lg')}>
                Go to my dashboard <ArrowRight aria-hidden className="size-5" />
              </Link>
              <a href={publicPath} target="_blank" rel="noreferrer" className={buttonClass('secondary', 'lg')}>
                Open my shop page <ExternalLink aria-hidden className="size-4" />
              </a>
            </div>
          </div>
        </ReceiptCard>

        <Card className="flex flex-col gap-5">
          <h2 className="text-2xl">For AI agents</h2>
          <CopyLine
            label="MCP endpoint"
            value={links.mcp}
            explain="AI assistants that connect to MCP servers (like Claude) use this to read your menu, get a quote and order."
          />
          <CopyLine
            label="UCP profile"
            value={links.ucp_profile}
            explain="Agents that use Google's Universal Commerce Protocol start here to discover KampungCart shops and check out."
          />
        </Card>
      </div>

      <QrCard url={links.public_page} slug={shop.slug} name={shop.name} />
    </div>
  )
}
