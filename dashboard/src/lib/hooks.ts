import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { ApiError, errorText } from './api'
import { OWNER_KEY_CHANGED, getOwnerKey } from './ownerKey'

function subscribe(cb: () => void) {
  window.addEventListener(OWNER_KEY_CHANGED, cb)
  return () => window.removeEventListener(OWNER_KEY_CHANGED, cb)
}

/** The owner key, re-rendering when it is set or cleared (e.g. after a 401). */
export function useOwnerKey(): string | null {
  return useSyncExternalStore(subscribe, getOwnerKey, () => null)
}

export interface Loaded<T> {
  data: T | null
  error: string | null
  /** HTTP status of the last failure (0 = network or timeout). */
  errorStatus: number | null
  loading: boolean
  reload: () => void
  setData: (update: T | ((prev: T | null) => T | null)) => void
}

interface LoadState<T> {
  key: string
  data: T | null
  error: string | null
  errorStatus: number | null
  loading: boolean
}

/** Load when `key` changes (or on reload). Data from an older key is never shown. */
export function useLoad<T>(load: (signal: AbortSignal) => Promise<T>, key: string): Loaded<T> {
  const [state, setState] = useState<LoadState<T>>({ key, data: null, error: null, errorStatus: null, loading: true })
  const [nonce, setNonce] = useState(0)
  const loadRef = useRef(load)
  useEffect(() => {
    loadRef.current = load
  })

  useEffect(() => {
    const ctrl = new AbortController()
    loadRef.current(ctrl.signal).then(
      (data) => !ctrl.signal.aborted && setState({ key, data, error: null, errorStatus: null, loading: false }),
      (err) =>
        !ctrl.signal.aborted &&
        setState((s) => ({
          key,
          data: s.key === key ? s.data : null,
          error: errorText(err),
          errorStatus: err instanceof ApiError ? err.status : null,
          loading: false,
        })),
    )
    return () => ctrl.abort()
  }, [key, nonce])

  const reload = useCallback(() => {
    setState((s) => ({ ...s, loading: true }))
    setNonce((n) => n + 1)
  }, [])
  const setData = useCallback((update: T | ((prev: T | null) => T | null)) => {
    setState((s) => ({
      ...s,
      data: typeof update === 'function' ? (update as (prev: T | null) => T | null)(s.data) : update,
    }))
  }, [])

  const current = state.key === key
  return {
    data: current ? state.data : null,
    error: current ? state.error : null,
    errorStatus: current ? state.errorStatus : null,
    loading: !current || state.loading,
    reload,
    setData,
  }
}

/** Call fn every `ms` while the tab is visible (and once right away). */
export function usePoll(fn: () => Promise<void> | void, ms: number, enabled = true) {
  const fnRef = useRef(fn)
  useEffect(() => {
    fnRef.current = fn
  })
  useEffect(() => {
    if (!enabled) return
    let timer: number | undefined
    let stopped = false
    let running = false
    const tick = async () => {
      if (stopped || running) return
      window.clearTimeout(timer)
      if (document.visibilityState === 'visible') {
        running = true
        try {
          await fnRef.current()
        } catch {
          // the page shows its own error state
        } finally {
          running = false
        }
      }
      if (!stopped) timer = window.setTimeout(tick, ms)
    }
    void tick()
    const onVisible = () => {
      if (document.visibilityState === 'visible') void tick()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      stopped = true
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [ms, enabled])
}
