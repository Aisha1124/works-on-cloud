import { KeyRound, LockKeyhole } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'
import { useOwnerKey } from '../lib/hooks'
import { clearOwnerKey } from '../lib/ownerKey'
import { Button, buttonClass } from '../ui'
import { OwnerKeyForm } from './OwnerKeyForm'

/** Top strip: wordmark home link on the left. On the right, "Lock" inside a shop the owner
 *  has opened, otherwise a small "Shop owner login" link. */
export function OwnerBar({ shopId, showLogin = true }: { shopId?: string; showLogin?: boolean }) {
  const key = useOwnerKey(shopId ?? '')
  return (
    <header className="flex items-center justify-between gap-3">
      <Link to="/" className="focus-ring font-display text-xl font-extrabold tracking-tight">
        Kampung<span className="text-chili">Cart</span>
      </Link>
      {shopId && key ? (
        <Button variant="ghost" size="sm" icon={<LockKeyhole aria-hidden className="size-4" />} onClick={() => clearOwnerKey(shopId)}>
          Lock
        </Button>
      ) : (
        showLogin && (
          <Link to="/login" className={buttonClass('ghost', 'sm')}>
            <KeyRound aria-hidden className="size-4" /> Shop owner login
          </Link>
        )
      )}
    </header>
  )
}

/** A shop's owner pages render only with that shop's key. Without it: the login form. */
export function RequireOwner({ shopId, children }: { shopId: string; children: ReactNode }) {
  const key = useOwnerKey(shopId)
  const navigate = useNavigate()
  if (!key) {
    return (
      <main className="mx-auto flex max-w-xl flex-col gap-6 px-4 py-6 sm:py-10">
        <OwnerBar showLogin={false} />
        <OwnerKeyForm onSignedIn={(shop) => shop.shop_id !== shopId && navigate(`/shop/${shop.shop_id}/orders`)} />
      </main>
    )
  }
  return <>{children}</>
}
