import { ArrowRight, ExternalLink, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { CopyLine, QrDownload } from '../components/Share'
import { useShop } from '../lib/shop'
import { Card, EmptyState, ReceiptCard, ReceiptDivider, Stamp, buttonClass } from '../ui'

/** The backup key, straight after going live. It is never shown again. Owners normally sign in
 *  with an email link; this key is for when email isn't available. */
function OwnerKeyCard({ ownerKey }: { ownerKey: string }) {
  return (
    <section aria-labelledby="owner-key" className="flex flex-col gap-3 border-2 border-ink bg-turmeric-tint p-4 shadow-hard sm:p-5">
      <h2 id="owner-key" className="text-2xl">
        Backup key, save it somewhere safe
      </h2>
      <p role="note" className="flex items-start gap-2 font-semibold">
        <TriangleAlert aria-hidden className="mt-0.5 size-5 flex-none text-chili" />
        We only show it once. You normally sign in with your email; this key gets you in if email doesn't work.
      </p>
      <CopyLine label="Backup key" value={ownerKey} />
      <p className="text-sm text-ink-soft">
        Keep it in your phone's notes or password manager. To use it: “Shop owner login”, then “Use backup key instead”.
      </p>
    </section>
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

      <Card className="flex flex-col items-start gap-4">
        <h2 className="text-2xl">Your shop QR code</h2>
        <QrDownload url={links.public_page} slug={shop.slug} name={shop.name} />
        <p className="text-ink-soft">Print it for your stall or post it on Instagram. It opens your menu so customers can order.</p>
      </Card>
    </div>
  )
}
