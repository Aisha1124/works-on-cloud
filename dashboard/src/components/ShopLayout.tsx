import { MailWarning } from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink, Outlet, useMatch, useNavigate, useParams } from 'react-router'
import { api, errorText } from '../lib/api'
import { useLoad } from '../lib/hooks'
import type { ShopContext } from '../lib/shop'
import type { Shop, ShopDetail } from '../lib/types'
import { Button, EmptyState, Signboard, Skeleton, buttonClass, cx, useToast } from '../ui'
import { ErrorCard } from './ErrorCard'
import { OwnerSignIn } from './OwnerKeyForm'
import { OwnerBar } from './OwnerShell'
import { ShareCard } from './Share'

const tabs = [
  { to: '', label: 'Menu', end: true },
  { to: 'orders', label: 'Orders' },
  { to: 'audit', label: 'Audit log' },
  { to: 'live', label: 'Go live' },
]

/** Until the owner taps the link in the "confirm your email" message. */
function ConfirmEmailBanner({ shop }: { shop: Shop }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  async function resend() {
    setBusy(true)
    try {
      await api(`/api/shops/${encodeURIComponent(shop.id)}/verify-email`, { method: 'POST' })
      toast.show(`Sent again to ${shop.owner_email}.`, 'success')
    } catch (err) {
      toast.show(errorText(err), 'error')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div role="status" className="flex flex-col gap-3 border-2 border-ink bg-turmeric-tint p-4 shadow-hard-sm sm:flex-row sm:items-center sm:justify-between">
      <p className="flex items-start gap-2">
        <MailWarning aria-hidden className="mt-0.5 size-5 flex-none" />
        <span>
          <b>Check your email to confirm.</b> We sent a link to <b className="break-all">{shop.owner_email}</b>. Your shop is already live. Check your spam folder if you don't see our email.
        </span>
      </p>
      <Button variant="secondary" size="sm" loading={busy} onClick={resend} className="self-start sm:self-auto">
        Send it again
      </Button>
    </div>
  )
}

function ShopFrame() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const loaded = useLoad((signal) => api<ShopDetail>(`/api/shops/${encodeURIComponent(id)}`, { signal }), id)
  const shop = loaded.data?.shop
  // The Live tab already shows the link, QR and MCP link (and, once, the owner key).
  const onLiveTab = useMatch('/shop/:id/live') !== null

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 pt-4 pb-32 sm:px-6 sm:pt-6">
      <OwnerBar shopId={id} signedIn={!!shop} showLogin={false} />
      {loaded.error && !loaded.data ? (
        loaded.errorStatus === 401 ? (
          // Not signed in to this shop (or signed in to another one): sign in right here.
          <div className="mx-auto flex w-full max-w-xl flex-col gap-3">
            {loaded.error !== 'Please sign in to manage this shop.' && <p role="alert" className="font-semibold">{loaded.error}</p>}
            <OwnerSignIn onSignedIn={(s) => (s.shop_id === id ? loaded.reload() : navigate(s.next || `/shop/${s.shop_id}/orders`))} />
          </div>
        ) : loaded.errorStatus === 404 ? (
          <EmptyState
            message="We can't find that shop."
            action={
              <Link to="/" className={buttonClass('secondary')}>
                Back to start
              </Link>
            }
          />
        ) : (
          <ErrorCard message={loaded.error} onRetry={loaded.reload} />
        )
      ) : !shop ? (
        <Skeleton rows={3} label="Loading your shop" />
      ) : (
        <>
          <Signboard
            title={shop.name}
            subtitle={shop.tagline || undefined}
            plate={shop.published ? `Live · /s/${shop.slug}` : 'Draft · not live yet'}
          />
          {shop.published && shop.owner_email && !shop.email_verified && <ConfirmEmailBanner shop={shop} />}
          {shop.published && !onLiveTab && loaded.data && <ShareCard shop={shop} links={loaded.data.links} />}
          <nav aria-label="Shop sections">
            <ul className="grid grid-cols-4 gap-1.5 sm:flex sm:gap-2">
              {tabs.map((t) => (
                <li key={t.label}>
                  <NavLink
                    to={t.to}
                    end={t.end}
                    className={({ isActive }) =>
                      cx(
                        'focus-ring flex min-h-11 items-center justify-center border-2 border-ink px-1 text-sm font-semibold whitespace-nowrap sm:px-4 sm:text-base',
                        isActive ? 'bg-ink text-receipt' : 'bg-receipt shadow-hard-sm hover:bg-turmeric-tint',
                      )
                    }
                  >
                    {t.label === 'Go live' && shop.published ? 'Live' : t.label === 'Audit log' ? <>Audit<span className="hidden sm:inline">&nbsp;log</span></> : t.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <Outlet context={{ ...loaded, shopId: id } satisfies ShopContext} />
        </>
      )}
    </div>
  )
}

export function ShopLayout() {
  return <ShopFrame />
}
