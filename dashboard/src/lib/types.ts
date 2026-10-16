// Mirrors backend/models.py. Money is a string ("12.50"): the backend computes it as Decimal.
import type { Actor, RiskLevel } from '../ui'

export type Money = string

export interface Shop {
  id: string
  slug: string
  name: string
  tagline: string
  shop_type: string
  address: string
  hours: string
  phone: string
  currency: string
  published: boolean
  auto_approve_limit: Money
  owner_email: string
  email_verified: boolean
  created_at: string
}

export interface Variant {
  label: string
  price: Money
}

export interface ProductOption {
  name: string
  choices: string[]
}

export interface Product {
  id: string
  shop_id: string
  name: string
  name_local: string
  category: string
  base_price: Money | null
  unit: string
  variants: Variant[]
  options: ProductOption[]
  available: boolean
  description: string
  confidence: number
}

/** What the owner sends when creating or editing an item. */
export type ProductInput = Omit<Product, 'id' | 'shop_id' | 'confidence'>

export interface ShopLinks {
  ucp_profile: string
  mcp: string
  public_page: string
}

/** Product id -> why the owner should check it (unclear read, odd price, ...). Guidance only. */
export type MenuChecks = Record<string, string[]>

export interface ShopDetail {
  shop: Shop
  products: Product[]
  links: ShopLinks
  checks: MenuChecks
}

/** Going live: owner_key is only set the first time, and is shown to the owner once. */
export interface PublishResponse extends ShopDetail {
  /** The backup key, shown once. */
  owner_key: string | null
  /** Where the "confirm your email" link went (the owner's own address). */
  verify_sent_to: string | null
}

/** After any sign-in (email link, backup key, confirm email): the shop and where to go next. */
export interface SignedIn {
  shop_id: string
  name: string
  slug: string
  published: boolean
  next: string
}

export interface DraftResponse {
  shop: Shop
  products: Product[]
  warnings: string[]
  checks: MenuChecks
  /** Temporary key for this browser until the shop goes live. */
  draft_key?: string | null
}

export type OrderStatus = 'auto_approved' | 'pending_approval' | 'approved' | 'rejected' | 'ready' | 'done' | 'cancelled'
export type Channel = 'mcp' | 'ucp' | 'dashboard' | 'web'

export interface OrderItem {
  product_id: string
  name: string
  variant: string | null
  options: Record<string, string>
  qty: number
  unit_price: Money
  line_total: Money
  /** Buyer's custom request for this line (untrusted text). */
  request?: string
}

/** A line the buyer asked for that is not on the menu: no price until the owner sets one. */
export interface UnpricedRequest {
  name: string
  qty: number
  request: string
}

export interface Risk {
  score: number
  level: RiskLevel
  reasons: string[]
  explanation: string
}

export interface Order {
  id: string
  shop_id: string
  items: OrderItem[]
  total: Money
  customer_name: string
  customer_phone: string
  /** Optional: the customer gets status emails. */
  customer_email?: string
  pickup_at: string
  note: string
  channel: Channel
  agent_name: string
  risk: Risk | null
  status: OrderStatus
  rejection_reason: string
  /** Rejected automatically: the owner didn't decide in time. */
  expired?: boolean
  unpriced_requests?: UnpricedRequest[]
  /** Why the owner must approve it (off-menu items, custom requests, limits, hours). */
  review_reasons?: string[]
  created_at: string
}

export interface AuditEvent {
  id: string
  shop_id: string
  at: string
  actor: Actor
  action: string
  entity_type: string
  entity_id: string
  summary: string
  details: Record<string, unknown>
}

export interface AuditPage {
  events: AuditEvent[]
  limit: number
  offset: number
}

export type PublicShop = Pick<Shop, 'slug' | 'name' | 'tagline' | 'shop_type' | 'address' | 'hours' | 'phone' | 'currency'> & {
  /** Only the sample shop: it shows an "Example shop" label. */
  example?: boolean
}

export interface PublicShopPage {
  shop: PublicShop
  products: Product[]
  links: ShopLinks
}

/** A cart line on the shop page. */
export interface CartLine {
  product_id: string
  variant: string | null
  options: Record<string, string>
  qty: number
}

export interface PricedLine {
  name: string
  variant: string | null
  options: Record<string, string>
  qty: number
  unit_price: Money
  line_total: Money
}

export interface WebQuote {
  items: PricedLine[]
  total: Money
  currency: string
}

/** What a customer sees about their order (buyer words, no risk details). */
export type BuyerStatus = 'confirmed' | 'pending_owner_approval' | 'rejected' | 'ready' | 'done' | 'cancelled'

export interface WebOrder {
  order_id: string
  shop_slug: string
  shop_name: string
  status: BuyerStatus
  message: string
  rejection_reason: string
  /** Rejected because the shop didn't respond in time. */
  expired: boolean
  items: PricedLine[]
  total: Money
  currency: string
  pickup_time: string
  /** The customer's private link to their status page /o/{id}?t={token}. */
  status_url: string
  can_cancel: boolean
  /** ISO time: cancelling closes then. */
  cancel_until: string
  /** Masked, e.g. "s***@gmail.com"; "" when no email was given. */
  email_updates_to: string
}
