import { useOutletContext } from 'react-router'
import type { Loaded } from './hooks'
import type { ShopDetail } from './types'

/** What ShopLayout hands to the screens under /shop/:id. */
export type ShopContext = Loaded<ShopDetail> & { shopId: string }

export function useShop(): ShopContext {
  return useOutletContext<ShopContext>()
}
