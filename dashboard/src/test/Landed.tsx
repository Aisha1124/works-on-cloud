import type { ReactNode } from 'react'
import { useLocation } from 'react-router'

/** A route element that prints where it landed, for navigation checks. */
export function Landed({ children }: { children?: ReactNode }) {
  const loc = useLocation()
  return (
    <div data-testid="landed" data-path={loc.pathname} data-state={JSON.stringify(loc.state ?? null)}>
      {children}
    </div>
  )
}
