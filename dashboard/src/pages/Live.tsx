import { ArrowRight, Check, Copy, ExternalLink } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { useState } from 'react'
import { Link } from 'react-router'
import { useShop } from '../lib/shop'
import { Button, Card, EmptyState, ReceiptCard, ReceiptDivider, Stamp, buttonClass, useToast } from '../ui'

function CopyLine({ label, url, explain }: { label: string; url: string; explain: string }) {
  const toast = useToast()
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
      toast.show(`${label} copied.`, 'success')
    } catch {
      toast.show("Couldn't copy. Select the link and copy it by hand.", 'error')
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="font-mono text-xs tracking-widest text-muted uppercase">{label}</p>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
        <code className="min-w-0 flex-1 border-2 border-ink bg-paper px-3 py-2.5 font-mono text-sm break-all">{url}</code>
        <Button
          variant="secondary"
          onClick={copy}
          icon={copied ? <Check aria-hidden className="size-4" /> : <Copy aria-hidden className="size-4" />}
          aria-label={`Copy ${label}`}
        >
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>
      <p className="text-ink-soft">{explain}</p>
    </div>
  )
}

export function Live() {
  const { data, shopId } = useShop()
  const { shop, links } = data!

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
      <ReceiptCard>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-3xl sm:text-4xl">Your shop is AI‑ready</h2>
          <Stamp kind="approved" label="Live" size="lg" animate />
        </div>
        <p className="mt-2 text-ink-soft">
          AI shopping agents can now find {shop.name}, read your menu and place pickup orders. Share these two links with any agent or
          developer.
        </p>
        <ReceiptDivider />
        <div className="flex flex-col gap-6">
          <CopyLine
            label="UCP profile"
            url={links.ucp_profile}
            explain="Agents that use Google's Universal Commerce Protocol start here to discover KampungCart shops and check out."
          />
          <CopyLine
            label="MCP endpoint"
            url={links.mcp}
            explain="AI assistants that connect to MCP servers use this to search your menu, get a quote and order."
          />
        </div>
      </ReceiptCard>

      <Card className="flex flex-col items-start gap-4">
        <h2 className="text-2xl">Your shop page</h2>
        <div className="border-2 border-ink bg-receipt p-3 shadow-hard-sm">
          <QRCodeSVG value={links.public_page} size={176} bgColor="#FFFDF8" fgColor="#1C1A17" level="M" title={`QR code for ${links.public_page}`} />
        </div>
        <p className="text-ink-soft">Print this for your stall or post it on Instagram. It opens your menu for people and AI agents.</p>
        <a href={publicPath} target="_blank" rel="noreferrer" className={buttonClass('secondary')}>
          Open {publicPath} <ExternalLink aria-hidden className="size-4" />
        </a>
        <Link to={`/shop/${shopId}/orders`} className={buttonClass('primary')}>
          Watch for orders <ArrowRight aria-hidden className="size-4" />
        </Link>
      </Card>
    </div>
  )
}
