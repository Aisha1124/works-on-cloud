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

export interface ShopDetail {
  shop: Shop
  products: Product[]
  links: ShopLinks
}

export interface ShopSummary {
  id: string
  name: string
  slug: string
  published: boolean
}

export interface DraftResponse {
  shop: Shop
  products: Product[]
  warnings: string[]
}

export type OrderStatus = 'auto_approved' | 'pending_approval' | 'approved' | 'rejected' | 'ready' | 'done'
export type Channel = 'mcp' | 'ucp' | 'dashboard'

export interface OrderItem {
  product_id: string
  name: string
  variant: string | null
  options: Record<string, string>
  qty: number
  unit_price: Money
  line_total: Money
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
  pickup_at: string
  note: string
  channel: Channel
  agent_name: string
  risk: Risk | null
  status: OrderStatus
  rejection_reason: string
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

export type PublicShop = Pick<Shop, 'slug' | 'name' | 'tagline' | 'shop_type' | 'address' | 'hours' | 'phone' | 'currency'>

export interface PublicShopPage {
  shop: PublicShop
  products: Product[]
  links: ShopLinks
}
