import { useEffect, useState } from 'react'
import { api, errorText } from './api'
import type { CartLine, WebQuote } from './types'

export function lineKey(l: CartLine): string {
  return JSON.stringify([l.product_id, l.variant, Object.entries(l.options).sort()])
}

export function addLine(cart: CartLine[], line: CartLine): CartLine[] {
  const key = lineKey(line)
  const found = cart.find((l) => lineKey(l) === key)
  return found ? cart.map((l) => (l === found ? { ...l, qty: Math.min(500, l.qty + line.qty) } : l)) : [...cart, line]
}

/** The cart priced by the server (Decimal, from the menu). The page never adds up money. */
export function useCartQuote(slug: string, cart: CartLine[]) {
  const [quote, setQuote] = useState<WebQuote | null>(null)
  const [error, setError] = useState<string | null>(null)
  const key = JSON.stringify(cart)
  useEffect(() => {
    if (!cart.length) {
      setQuote(null)
      setError(null)
      return
    }
    const ctrl = new AbortController()
    const timer = window.setTimeout(() => {
      api<WebQuote>(`/api/public/shops/${encodeURIComponent(slug)}/quote`, { method: 'POST', json: { items: cart }, owner: false, signal: ctrl.signal }).then(
        (q) => {
          setQuote(q)
          setError(null)
        },
        (err) => !ctrl.signal.aborted && setError(errorText(err)),
      )
    }, 250)
    return () => {
      window.clearTimeout(timer)
      ctrl.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, key])
  return { quote: cart.length ? quote : null, error }
}
