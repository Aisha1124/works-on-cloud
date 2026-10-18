// Mirrors backend/models.py. Money is a string ("12.50"): the backend computes it as Decimal.
import type { Actor, RiskLevel } from '../ui'
import type { ShopColour } from './shopColours'

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
  approval_timeout_hours: number
  cancel_cutoff_hours: number
  min_notice_hours: number
  /** Max orders per pickup day; null = no limit. */
  daily_capacity: number | null
  /** "2026-10-26": no new orders until that day. */
  paused_until: string | null
  /** Header colour of the public shop page (one of SHOP_COLOURS). Missing = chili. */
  theme_colour?: ShopColour
  created_at: string
}

/** One row of the weekly hours table (day 0 = Monday, times "HH:MM"). */
export interface DayHours {
  day: number
  closed: boolean
  open: string
  close: string
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
  /** The hours as a weekly table (9am-6pm daily when the hours text can't be read). */
  opening_hours?: DayHours[]
  hours_readable?: boolean
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

export type PublicShop = Pick<Shop, 'slug' | 'name' | 'tagline' | 'shop_type' | 'address' | 'hours' | 'phone' | 'currency' | 'theme_colour'> & {
  /** Only the sample shop: it shows an "Example shop" label. */
  example?: boolean
  min_notice_hours?: number
  paused_until?: string | null
  /** "Not taking orders until ..." while paused, else "". */
  ordering_message?: string
}

/** Pickup times the shop page offers (computed by the server, Singapore time). */
export interface PickupSlots {
  days: { date: string; label: string; times: { value: string; label: string }[] }[]
  /** Why there are no days ("" when there are some). */
  message: string
  min_notice_hours: number
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
