// The owner key lives in sessionStorage (cleared when the tab closes). Storage can be
// blocked (private mode, strict settings), so every access is wrapped and falls back to memory.
const STORAGE_KEY = 'kampungcart.ownerKey'
export const OWNER_KEY_CHANGED = 'kampungcart:owner-key'

let memory: string | null = null

export function getOwnerKey(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY) ?? memory
  } catch {
    return memory
  }
}

export function setOwnerKey(key: string): void {
  memory = key
  try {
    sessionStorage.setItem(STORAGE_KEY, key)
  } catch {
    // memory only
  }
  window.dispatchEvent(new Event(OWNER_KEY_CHANGED))
}

export function clearOwnerKey(): void {
  memory = null
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // nothing stored
  }
  window.dispatchEvent(new Event(OWNER_KEY_CHANGED))
}
