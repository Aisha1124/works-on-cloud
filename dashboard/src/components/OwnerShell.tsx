import { KeyRound, LogOut } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { api } from '../lib/api'
import { clearOwnerKey } from '../lib/ownerKey'
import { Button, buttonClass } from '../ui'

/** Top strip: wordmark home link on the left. On the right, "Sign out" inside a shop the owner
 *  has open, otherwise a small "Shop owner login" link. */
export function OwnerBar({ shopId, signedIn = false, showLogin = true }: { shopId?: string; signedIn?: boolean; showLogin?: boolean }) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)

  async function signOut() {
    setBusy(true)
    try {
      await api('/api/owner/logout', { method: 'POST', owner: false })
    } catch {
      // signed out locally anyway
    }
    if (shopId) clearOwnerKey(shopId)
    navigate('/')
  }

  return (
    <header className="flex items-center justify-between gap-3">
      <Link to="/" className="focus-ring font-display text-xl font-extrabold tracking-tight">
        Kampung<span className="text-chili">Cart</span>
      </Link>
      {shopId && signedIn ? (
        <Button variant="ghost" size="sm" loading={busy} icon={<LogOut aria-hidden className="size-4" />} onClick={signOut}>
          Sign out
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
