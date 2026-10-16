import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Landed } from '../test/Landed'
import { renderAt, stubApi } from '../test/render'
import { PublicShop } from './PublicShop'

const PAGE = {
  shop: { slug: 'mak-kuih', name: "Mak's Kuih", tagline: '', shop_type: 'Home baker', address: '', hours: 'Tue-Sun 9am-6pm', phone: '', currency: 'SGD' },
  products: [
    { id: 'kuih-lapis', shop_id: 'mak-kuih', name: 'Kuih Lapis', name_local: '', category: 'Kuih', base_price: null, unit: '', available: true, description: '', confidence: 1, options: [], variants: [{ label: '20 pcs', price: '16.00' }, { label: '40 pcs', price: '30.00' }] },
  ],
  links: { ucp_profile: 'https://kc.example/.well-known/ucp', mcp: 'https://kc.example/mcp', public_page: 'https://kc.example/s/mak-kuih' },
}

const routes = [
  { path: '/s/:slug', element: <PublicShop /> },
  { path: '/', element: <Landed /> },
]

describe('customer shop page', () => {
  it('says it was made with KampungCart and links home', async () => {
    stubApi((url) => (url === '/api/public/shops/mak-kuih' ? { body: PAGE } : undefined))
    renderAt('/s/mak-kuih', routes)
    const link = await screen.findByRole('link', { name: /Make one for your shop/ })
    expect(link.getAttribute('href')).toBe('/')
    expect(link.closest('footer')?.textContent).toMatch(/Shop page made with KampungCart/)
    fireEvent.click(link)
    expect((await screen.findByTestId('landed')).dataset.path).toBe('/')
  })

  it('gives one example sentence to type to an AI assistant, with a real item', async () => {
    stubApi((url) => (url === '/api/public/shops/mak-kuih' ? { body: PAGE } : undefined))
    renderAt('/s/mak-kuih', routes)
    const box = await screen.findByRole('region', { name: /Order with your AI assistant/ })
    expect(box.textContent).toContain('https://kc.example/mcp')
    expect(box.textContent).toContain('Order 2 boxes of Kuih Lapis from mak-kuih for Saturday 10am pickup.')
  })

  it('still links home when the shop is not found', async () => {
    stubApi(() => undefined)
    renderAt('/s/nope', routes)
    expect(await screen.findByText(/isn't open on KampungCart/)).toBeTruthy()
    expect(screen.getByRole('link', { name: /Make one for your shop/ }).getAttribute('href')).toBe('/')
  })
})
