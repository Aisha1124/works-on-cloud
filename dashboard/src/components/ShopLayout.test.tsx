import { fireEvent, screen, within } from '@testing-library/react'
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

describe('owner account in the dashboard', () => {
  it('asks the owner to confirm their email until they do, and can send it again', async () => {
    const calls = stubApi((url) => {
      if (url === '/api/shops/mak-kuih')
        return { body: { shop: { ...SHOP, published: true, owner_email: 'siti@example.sg', email_verified: false }, products: [], links: LINKS } }
      if (url === '/api/shops/mak-kuih/verify-email') return { body: { sent_to: 'siti@example.sg', verified: false } }
    })
    renderAt('/shop/mak-kuih/orders', routes)
    const banner = await screen.findByText('Check your email to confirm.')
    expect(banner.closest('[role="status"]')?.textContent).toContain('siti@example.sg')
    fireEvent.click(screen.getByRole('button', { name: 'Send it again' }))
    expect(await screen.findByText('Sent again to siti@example.sg.')).toBeTruthy()
    expect(calls.some((c) => c.url.endsWith('/verify-email') && c.init?.method === 'POST')).toBe(true)
  })

  it('has no banner once the email is confirmed', async () => {
    stubApi((url) =>
      url === '/api/shops/mak-kuih'
        ? { body: { shop: { ...SHOP, published: true, owner_email: 'siti@example.sg', email_verified: true }, products: [], links: LINKS } }
        : undefined,
    )
    renderAt('/shop/mak-kuih/orders', routes)
    await screen.findByText('orders here')
    expect(screen.queryByText('Check your email to confirm.')).toBeNull()
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeTruthy()
  })

  it('shows the email sign-in when this browser is not signed in to the shop', async () => {
    stubApi((url) => (url === '/api/shops/mak-kuih' ? { status: 401, body: { detail: 'Please sign in to manage this shop.' } } : undefined))
    renderAt('/shop/mak-kuih/orders', routes)
    expect(await screen.findByRole('button', { name: 'Email me a sign-in link' })).toBeTruthy()
    expect(screen.queryByText('orders here')).toBeNull()
  })
})
