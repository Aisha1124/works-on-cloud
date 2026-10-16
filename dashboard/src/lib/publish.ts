import { api } from './api'
import { setOwnerKey } from './ownerKey'
import type { PublishResponse, ShopDetail } from './types'

/** Go live. The first time, the server swaps the draft key for the real owner key: keep it
 *  for this tab and hand it back so the next screen can show it once. */
export async function goLive(shopId: string): Promise<{ detail: ShopDetail; ownerKey: string | null }> {
  const { owner_key: ownerKey, ...detail } = await api<PublishResponse>(`/api/shops/${encodeURIComponent(shopId)}/publish`, { method: 'POST' })
  if (ownerKey) setOwnerKey(shopId, ownerKey)
  return { detail, ownerKey }
}

/** Where to go after going live: the success screen, with the key in router state (shown once). */
export function liveScreen(shopId: string, ownerKey: string | null) {
  return { to: `/shop/${shopId}/live`, options: { state: ownerKey ? { ownerKey } : null } }
}
