import { Check, Copy, Download, ExternalLink } from 'lucide-react'
import { QRCodeCanvas } from 'qrcode.react'
import { useRef, useState } from 'react'
import type { Shop, ShopLinks } from '../lib/types'
import { Button, Card, buttonClass, useToast } from '../ui'

/** A label, the value in a mono box, and a Copy button. */
export function CopyLine({ label, value, explain }: { label: string; value: string; explain?: string }) {
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
    <div className="flex min-w-0 flex-col gap-2">
      <p className="font-mono text-xs tracking-widest text-muted uppercase">{label}</p>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
        <code className="min-w-0 flex-1 border-2 border-ink bg-paper px-3 py-2.5 font-mono text-sm break-all">{value}</code>
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

/** The shop link as a QR code, with a PNG download (512px, good for printing). */
export function QrDownload({ url, slug, name, size = 176 }: { url: string; slug: string; name: string; size?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const toast = useToast()

  function download() {
    const canvas = canvasRef.current
    try {
      if (!canvas) throw new Error('no canvas')
      const link = document.createElement('a')
      link.href = canvas.toDataURL('image/png')
      link.download = `${slug}-qr.png`
      link.click()
    } catch {
      toast.show("Couldn't save the QR code. Take a screenshot instead.", 'error')
    }
  }

  return (
    <div className="flex flex-col items-start gap-3">
      <div className="border-2 border-ink bg-receipt p-2 shadow-hard-sm">
        <QRCodeCanvas
          ref={canvasRef}
          value={url}
          size={512}
          marginSize={2}
          bgColor="#FFFDF8"
          fgColor="#1C1A17"
          level="M"
          title={`QR code for ${name}`}
          style={{ width: size, height: size }}
        />
      </div>
      <Button variant="secondary" size="sm" onClick={download} icon={<Download aria-hidden className="size-4" />}>
        Download QR code
      </Button>
    </div>
  )
}

/** Top of the owner dashboard: everything an owner shares, in one place. */
export function ShareCard({ shop, links }: { shop: Shop; links: ShopLinks }) {
  return (
    <Card role="region" className="grid grid-cols-1 gap-5 sm:grid-cols-[auto_minmax(0,1fr)] sm:items-start" aria-labelledby="share-shop">
      <QrDownload url={links.public_page} slug={shop.slug} name={shop.name} size={112} />
      <div className="flex min-w-0 flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="share-shop" className="text-2xl">
            Share your shop
          </h2>
          <a href={`/s/${shop.slug}`} target="_blank" rel="noreferrer" className={buttonClass('ghost', 'sm')}>
            Open shop page <ExternalLink aria-hidden className="size-4" />
          </a>
        </div>
        <CopyLine label="Shop link" value={links.public_page} />
        <CopyLine label="MCP link for AI assistants" value={links.mcp} />
      </div>
    </Card>
  )
}
