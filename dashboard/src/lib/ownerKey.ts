// Owner keys, one per shop, kept in sessionStorage (cleared when the tab closes). A draft
// shop's key is the temporary one from the photo upload; going live replaces it.
// Storage can be blocked (private mode, strict settings), so every access is wrapped and
// falls back to memory.
const STORAGE_KEY = 'kampungcart.ownerKeys'
export const OWNER_KEY_CHANGED = 'kampungcart:owner-key'

let memory: Record<string, string> = {}

function readAll(): Record<string, string> {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? { ...memory, ...(JSON.parse(raw) as Record<string, string>) } : memory
  } catch {
    return memory
  }
}

function writeAll(keys: Record<string, string>): void {
  memory = keys
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(keys))
  } catch {
    // memory only
  }
  window.dispatchEvent(new Event(OWNER_KEY_CHANGED))
}

export function getOwnerKey(shopId: string): string | null {
  return readAll()[shopId] ?? null
}

export function setOwnerKey(shopId: string, key: string): void {
  writeAll({ ...readAll(), [shopId]: key })
}

export function clearOwnerKey(shopId: string): void {
  const { [shopId]: _gone, ...rest } = readAll()
  void _gone
  writeAll(rest)
}

/** The shop id in an owner API path like /api/shops/{id}/orders, or null. */
export function shopIdOf(path: string): string | null {
  const m = /^\/api\/shops\/([^/?#]+)/.exec(path)
  return m && m[1] !== 'draft' ? decodeURIComponent(m[1]) : null
}
