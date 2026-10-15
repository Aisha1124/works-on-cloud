import { LockKeyhole } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { useOwnerKey } from '../lib/hooks'
import { clearOwnerKey } from '../lib/ownerKey'
import { Button } from '../ui'
import { OwnerKeyForm } from './OwnerKeyForm'

/** Top strip for owner pages: wordmark home link and a lock button. */
export function OwnerBar() {
  const key = useOwnerKey()
  return (
    <div className="flex items-center justify-between gap-3">
      <Link to="/" className="focus-ring font-display text-xl font-extrabold tracking-tight">
        Kampung<span className="text-chili">Cart</span>
      </Link>
      {key && (
        <Button variant="ghost" size="sm" icon={<LockKeyhole aria-hidden className="size-4" />} onClick={clearOwnerKey}>
          Lock
        </Button>
      )}
    </div>
  )
}

/** Owner pages render their children only once a key is entered. */
export function RequireOwner({ children }: { children: ReactNode }) {
  const key = useOwnerKey()
  if (!key) {
    return (
      <main className="mx-auto flex max-w-xl flex-col gap-6 px-4 py-6 sm:py-10">
        <OwnerBar />
        <OwnerKeyForm />
      </main>
    )
  }
  return <>{children}</>
}
