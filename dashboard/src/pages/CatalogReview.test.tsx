import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ShopLayout } from '../components/ShopLayout'
import { setOwnerKey } from '../lib/ownerKey'
import { renderAt, stubApi } from '../test/render'
import { CatalogReview } from './CatalogReview'

const LINKS = { ucp_profile: 'https://kc.example/.well-known/ucp', mcp: 'https://kc.example/mcp', public_page: 'https://kc.example/s/draft-ab12' }
const SHOP = {
  id: 'shop1', slug: 'draft-ab12', name: 'Draft', tagline: '', shop_type: '', address: '', hours: '', phone: '',
  currency: 'SGD', auto_approve_limit: '150', published: false, created_at: '2026-10-16T00:00:00Z',
}
const item = (id: string, name: string, base_price: string | null, unit = '') => ({
  id, shop_id: 'shop1', name, name_local: '', category: 'Kuih', base_price, unit, variants: [], options: [],
  available: true, description: '', confidence: 0.9,
})
const routes = [{ path: '/shop/:id', element: <ShopLayout />, children: [{ path: 'catalog', element: <CatalogReview /> }] }]

function shopApi(checks: Record<string, string[]>) {
  setOwnerKey('shop1', 'kc_draft')
  stubApi((url) =>
    url === '/api/shops/shop1'
      ? {
          body: {
            shop: SHOP,
            products: [item('lapis', 'Kuih Lapis', '16', '20 pcs'), item('ondeh', 'Ondeh Ondeh', null), item('salat', 'Kueh Salat', '20', '1 tray')],
            links: LINKS,
            checks,
          },
        }
      : undefined,
  )
}

describe('Check your menu', () => {
  it('highlights flagged items with the reason and counts them next to Go live', async () => {
    shopApi({ lapis: ['Price smudged.'], ondeh: ["No price yet. Add one, or customers can't order it."] })
    renderAt('/shop/shop1/catalog', routes)
    const lapis = (await screen.findByText('Kuih Lapis')).closest('li')!
    expect(within(lapis).getByText('Please check this')).toBeTruthy()
    expect(within(lapis).getByText('Price smudged.')).toBeTruthy()
    expect(lapis.className).toContain('bg-turmeric-tint')
    const salat = screen.getByText('Kueh Salat').closest('li')!
    expect(within(salat).queryByText('Please check this')).toBeNull()
    expect(salat.className).not.toContain('bg-turmeric-tint')
    // The Go live bar says how many, and Go live still works.
    const bar = screen.getByRole('button', { name: /Go live/ }).parentElement!
    expect(bar.textContent).toContain('2 items need a quick check')
    expect((screen.getByRole('button', { name: /Go live/ }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('shows no count when nothing needs a check', async () => {
    shopApi({})
    renderAt('/shop/shop1/catalog', routes)
    await screen.findByText('Kuih Lapis')
    expect(screen.queryByText('Please check this')).toBeNull()
    expect(screen.queryByText(/need a quick check|needs a quick check/)).toBeNull()
  })
})
