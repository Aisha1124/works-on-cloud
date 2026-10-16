import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { setOwnerKey } from '../lib/ownerKey'
import { renderAt, stubApi } from '../test/render'
import { ShopLayout } from './ShopLayout'

const LINKS = { ucp_profile: 'https://kc.example/.well-known/ucp', mcp: 'https://kc.example/mcp', public_page: 'https://kc.example/s/mak-kuih' }
const SHOP = {
  id: 'mak-kuih', slug: 'mak-kuih', name: "Mak's Kuih", tagline: '', shop_type: '', address: '', hours: '', phone: '',
  currency: 'SGD', auto_approve_limit: '150', created_at: '2026-10-16T00:00:00Z',
}

const routes = [
  {
    path: '/shop/:id',
    element: <ShopLayout />,
    children: [
      { path: 'orders', element: <p>orders here</p> },
      { path: 'live', element: <p>live here</p> },
    ],
  },
]

function shopApi(published: boolean) {
  setOwnerKey('mak-kuih', 'kc_owner')
  return stubApi((url) => (url === '/api/shops/mak-kuih' ? { body: { shop: { ...SHOP, published }, products: [], links: LINKS } } : undefined))
}

describe('owner dashboard', () => {
  it('starts with a "Share your shop" card: shop link, QR download and MCP link', async () => {
    shopApi(true)
    renderAt('/shop/mak-kuih/orders', routes)
    const card = await screen.findByRole('region', { name: 'Share your shop' })
    expect(card.textContent).toContain('https://kc.example/s/mak-kuih')
    expect(card.textContent).toContain('https://kc.example/mcp')
    expect(within(card).getByRole('button', { name: /Download QR code/ })).toBeTruthy()
    expect(within(card).getByRole('button', { name: 'Copy Shop link' })).toBeTruthy()
    expect(within(card).getByRole('button', { name: 'Copy MCP link for AI assistants' })).toBeTruthy()
    expect(within(card).getByRole('link', { name: /Open shop page/ }).getAttribute('href')).toBe('/s/mak-kuih')
    // It sits above the tabs.
    const nav = screen.getByRole('navigation', { name: 'Shop sections' })
    expect(card.compareDocumentPosition(nav) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('has nothing to share before the shop is live', async () => {
    shopApi(false)
    renderAt('/shop/mak-kuih/orders', routes)
    await screen.findByText('orders here')
    expect(screen.queryByRole('region', { name: 'Share your shop' })).toBeNull()
  })

  it('is not repeated on the Live tab, which shows the same links', async () => {
    shopApi(true)
    renderAt('/shop/mak-kuih/live', routes)
    await screen.findByText('live here')
    expect(screen.queryByRole('region', { name: 'Share your shop' })).toBeNull()
  })
})
