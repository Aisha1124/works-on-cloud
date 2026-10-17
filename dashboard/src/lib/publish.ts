import { api } from './api'
import { clearOwnerKey } from './ownerKey'
import type { PublishResponse, ShopDetail } from './types'

export interface Account {
  name: string
  email: string
}

/** Go live = create the owner's account (shop name + email). The server signs this browser in
 *  with a session cookie and retires the draft key, so the tab drops it too. The backup key
 *  comes back once, for the next screen to show. */
export async function goLive(shopId: string, account: Account): Promise<{ detail: ShopDetail; ownerKey: string | null }> {
  const { owner_key: ownerKey, ...detail } = await api<PublishResponse>(`/api/shops/${encodeURIComponent(shopId)}/publish`, {
    method: 'POST',
    json: account,
  })
  clearOwnerKey(shopId)
  return { detail, ownerKey }
}

/** Where to go after going live: the success screen, with the key in router state (shown once). */
export function liveScreen(shopId: string, ownerKey: string | null) {
  return { to: `/shop/${shopId}/live`, options: { state: ownerKey ? { ownerKey } : null } }
}
