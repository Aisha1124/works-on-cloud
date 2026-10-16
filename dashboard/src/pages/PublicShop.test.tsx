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
    expect(screen.getByRole('link', { name: 'Privacy' }).getAttribute('href')).toBe('/privacy')
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

  it('labels only the sample shop as an example', async () => {
    stubApi((url) => (url === '/api/public/shops/mak-kuih' ? { body: { ...PAGE, shop: { ...PAGE.shop, example: true } } } : undefined))
    renderAt('/s/mak-kuih', routes)
    expect(await screen.findByText('Example shop')).toBeTruthy()
    expect(screen.getByText(/It is not a real business/)).toBeTruthy()
  })

  it('shows no example label on a real shop', async () => {
    stubApi((url) => (url === '/api/public/shops/mak-kuih' ? { body: PAGE } : undefined))
    renderAt('/s/mak-kuih', routes)
    await screen.findByRole('region', { name: /Order with your AI assistant/ })
    expect(screen.queryByText('Example shop')).toBeNull()
  })

  it('says when the shop is paused and takes no orders', async () => {
    const paused = { ...PAGE, shop: { ...PAGE.shop, ordering_message: 'Not taking orders until Mon 26 Oct 2026.' } }
    stubApi((url) => (url === '/api/public/shops/mak-kuih' ? { body: paused } : undefined))
    renderAt('/s/mak-kuih', routes)
    expect(await screen.findByText('Not taking orders until Mon 26 Oct 2026.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Add Kuih Lapis/ })).toBeNull()
  })

  it('offers only the pickup times the shop can take', async () => {
    const SLOTS = {
      min_notice_hours: 24,
      message: '',
      days: [
        { date: '2026-10-20', label: 'Tue 20 Oct', times: [{ value: '2026-10-20T09:00', label: '09:00' }, { value: '2026-10-20T09:30', label: '09:30' }] },
        { date: '2026-10-21', label: 'Wed 21 Oct', times: [{ value: '2026-10-21T14:00', label: '14:00' }] },
      ],
    }
    stubApi((url) => {
      if (url === '/api/public/shops/mak-kuih') return { body: PAGE }
      if (url === '/api/public/shops/mak-kuih/slots') return { body: SLOTS }
      if (url === '/api/public/shops/mak-kuih/quote') return { body: { items: [], total: '16.00', currency: 'SGD' } }
      return undefined
    })
    renderAt('/s/mak-kuih', routes)
    fireEvent.click(await screen.findByRole('button', { name: 'Add Kuih Lapis' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Add to order' }))
    const day = (await screen.findByLabelText('Day')) as HTMLSelectElement
    expect([...day.options].map((o) => o.text)).toEqual(['Tue 20 Oct', 'Wed 21 Oct'])
    const time = screen.getByLabelText('Time') as HTMLSelectElement
    expect([...time.options].map((o) => o.text)).toEqual(['Choose a time', '09:00', '09:30'])
    fireEvent.change(day, { target: { value: '2026-10-21' } })
    expect([...(screen.getByLabelText('Time') as HTMLSelectElement).options].map((o) => o.value)).toEqual(['', '2026-10-21T14:00'])
    expect(screen.getByText("This shop needs 24 hours' notice. Only open times are shown.")).toBeTruthy()
  })

  it('still links home when the shop is not found', async () => {
    stubApi(() => undefined)
    renderAt('/s/nope', routes)
    expect(await screen.findByText(/isn't open on KampungCart/)).toBeTruthy()
    expect(screen.getByRole('link', { name: /Make one for your shop/ }).getAttribute('href')).toBe('/')
  })
})
