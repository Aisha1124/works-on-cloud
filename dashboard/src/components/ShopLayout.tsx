import { Link, NavLink, Outlet, useMatch, useParams } from 'react-router'
import { api } from '../lib/api'
import { useLoad } from '../lib/hooks'
import type { ShopContext } from '../lib/shop'
import type { ShopDetail } from '../lib/types'
import { EmptyState, Signboard, Skeleton, buttonClass, cx } from '../ui'
import { ErrorCard } from './ErrorCard'
import { OwnerBar, RequireOwner } from './OwnerShell'
import { ShareCard } from './Share'

const tabs = [
  { to: '', label: 'Menu', end: true },
  { to: 'orders', label: 'Orders' },
  { to: 'audit', label: 'Audit log' },
  { to: 'live', label: 'Go live' },
]

function ShopFrame() {
  const { id = '' } = useParams()
  const loaded = useLoad((signal) => api<ShopDetail>(`/api/shops/${encodeURIComponent(id)}`, { signal }), id)
  const shop = loaded.data?.shop
  // The Live tab already shows the link, QR and MCP link (and, once, the owner key).
  const onLiveTab = useMatch('/shop/:id/live') !== null

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 pt-4 pb-32 sm:px-6 sm:pt-6">
      <OwnerBar shopId={id} />
      {loaded.error && !loaded.data ? (
        loaded.errorStatus === 404 ? (
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
  const { id = '' } = useParams()
  return (
    <RequireOwner shopId={id}>
      <ShopFrame />
    </RequireOwner>
  )
}
