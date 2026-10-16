import { clearOwnerKey, getOwnerKey, shopIdOf } from './ownerKey'

/** str(error) is always a friendly sentence that is safe to show. */
export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const OFFLINE = "Can't reach KampungCart right now. Check your connection and try again."
const SLOW = 'This is taking longer than expected. Please try again.'
const GENERIC = 'Something went wrong on our side. Please try again.'

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  json?: unknown
  form?: FormData
  /** Owner routes (/api/shops/{id}/...) send that shop's X-Owner-Key. Public routes don't. */
  owner?: boolean
  timeoutMs?: number
  signal?: AbortSignal
}

function friendly(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string' && detail.length < 300) return detail
  if (Array.isArray(detail)) {
    // FastAPI validation errors: name the fields, never dump the raw list.
    const fields = detail
      .map((e) => (e as { loc?: unknown[] }).loc?.filter((p) => typeof p === 'string' && p !== 'body').join(' '))
      .filter(Boolean)
    const unique = [...new Set(fields)].slice(0, 3).map((f) => String(f).replace(/_/g, ' '))
    return unique.length ? `Please check: ${unique.join(', ')}.` : 'Please check the details and try again.'
  }
  if (status === 404) return 'Not found.'
  return GENERIC
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', json, form, owner = true, timeoutMs = 15000, signal } = opts
  const headers: Record<string, string> = { Accept: 'application/json' }
  const shopId = owner ? shopIdOf(path) : null
  if (shopId) headers['X-Owner-Key'] = getOwnerKey(shopId) ?? ''
  if (json !== undefined) headers['Content-Type'] = 'application/json'

  const timeout = AbortSignal.timeout(timeoutMs)
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout

  let res: Response
  try {
    res = await fetch(path, {
      method,
      headers,
      body: form ?? (json !== undefined ? JSON.stringify(json) : undefined),
      signal: combined,
    })
  } catch (err) {
    if (signal?.aborted) throw err // the caller cancelled; not an error to show
    if (timeout.aborted) throw new ApiError(0, SLOW)
    throw new ApiError(0, OFFLINE)
  }

  if (res.status === 204) return undefined as T
  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    // not JSON (e.g. a proxy error page): fall through to a generic message
  }
  if (!res.ok) {
    if (res.status === 401 && shopId) clearOwnerKey(shopId)
    throw new ApiError(res.status, friendly(res.status, body))
  }
  return body as T
}

export function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : GENERIC
}

/** Photo reading can take up to ~90s (45s per try, one retry). */
export const PHOTO_TIMEOUT_MS = 120_000
