import { ArrowRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Card, Signboard, Stamp, buttonClass } from '../ui'

type ApiState = 'checking' | 'ok' | 'offline'

function useApiHealth(): ApiState {
  const [state, setState] = useState<ApiState>('checking')
  useEffect(() => {
    const ctrl = new AbortController()
    fetch('/api/health', { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((body: { ok?: boolean }) => setState(body.ok ? 'ok' : 'offline'))
      .catch(() => {
        if (!ctrl.signal.aborted) setState('offline')
      })
    return () => ctrl.abort()
  }, [])
  return state
}

export function Home() {
  const api = useApiHealth()

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-6 sm:px-6 sm:py-10">
      <Signboard title="KampungCart" subtitle="Make any shop AI-ready from one photo." />

      <Card className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl">Owner dashboard</h2>
          <p className="mt-1 text-muted">The shop screens are being built. The design system is ready to look at.</p>
        </div>
        <div className="flex flex-wrap items-center gap-5">
          <span aria-live="polite">
            {api === 'checking' && <Stamp kind="check" label="Checking API" size="sm" />}
            {api === 'ok' && <Stamp kind="approved" label="API OK" size="sm" animate />}
            {api === 'offline' && <Stamp kind="rejected" label="API offline" size="sm" animate />}
          </span>
          <Link to="/styleguide" className={buttonClass('primary')}>
            Open styleguide <ArrowRight aria-hidden className="size-4" />
          </Link>
        </div>
      </Card>
    </main>
  )
}
