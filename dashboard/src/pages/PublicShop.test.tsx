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

  it('keeps the default banner colour when the shop has not picked one', async () => {
    stubApi((url) => (url === '/api/public/shops/mak-kuih' ? { body: PAGE } : undefined))
    renderAt('/s/mak-kuih', routes)
    const banner = (await screen.findByRole('heading', { level: 1, name: "Mak's Kuih" })).closest('header')!
    expect(banner.style.getPropertyValue('--signboard-bg')).toBe('')
  })

  it("paints the banner in the shop's colour", async () => {
    const page = { ...PAGE, shop: { ...PAGE.shop, theme_colour: 'laut' } }
    stubApi((url) => (url === '/api/public/shops/mak-kuih' ? { body: page } : undefined))
    renderAt('/s/mak-kuih', routes)
    const banner = (await screen.findByRole('heading', { level: 1, name: "Mak's Kuih" })).closest('header')!
    expect(banner.style.getPropertyValue('--signboard-bg')).toBe('#1F5F8B')
  })

  it('says customers can order by chatting here, and AI apps can connect through MCP', async () => {
    stubApi((url) => (url === '/api/public/shops/mak-kuih' ? { body: PAGE } : undefined))
    renderAt('/s/mak-kuih', routes)
    const box = await screen.findByRole('region', { name: 'Ordering with AI' })
    expect(box.textContent).toContain('Order by chatting with our AI assistant on any shop page, no setup needed. AI apps can also connect through MCP.')
    expect(box.textContent).toContain('add https://kc.example/mcp as a connector')
    expect(box.textContent).toContain("Any AI (ChatGPT, Gemini or Claude) can also read this page's link")
    expect(box.textContent).toContain('Order 2 boxes of Kuih Lapis from mak-kuih for Saturday 10am pickup.')
  })

  it('shows the Order with AI chat above the menu and order form', async () => {
    stubApi((url) => (url === '/api/public/shops/mak-kuih' ? { body: PAGE } : undefined))
    renderAt('/s/mak-kuih', routes)
    const chat = await screen.findByRole('region', { name: 'Order with AI' })
    const menu = screen.getByRole('heading', { name: 'Kuih' })
    expect(chat.compareDocumentPosition(menu) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(chat.textContent).toContain('2 boxes of Kuih Lapis 20 pcs for Saturday 10am')
  })

  it('chats with the assistant and shows the order status link', async () => {
    const calls = stubApi((url, init) => {
      if (url === '/api/public/shops/mak-kuih') return { body: PAGE }
      if (url === '/api/public/shops/mak-kuih/chat') {
        const sent = JSON.parse(String(init?.body))
        if (sent.chat_id === null) return { body: { chat_id: 'c1', reply: 'That is S$32.00. Shall I place this order?', orders: [], turns_left: 11 } }
        return {
          body: {
            chat_id: 'c1',
            reply: 'Done! Your order is confirmed.',
            orders: [{ order_id: 'abcdef123456', status: 'confirmed', status_url: 'http://localhost:8000/o/abcdef123456?t=tok', subtotal: '32.00', pickup_time: '2026-10-17T10:00:00+08:00' }],
            turns_left: 10,
          },
        }
      }
      return undefined
    })
    renderAt('/s/mak-kuih', routes)
    const box = await screen.findByLabelText('Message to the shop assistant')
    fireEvent.change(box, { target: { value: '2 boxes of kuih lapis 20 pcs, Siti +65 9123 4567' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('That is S$32.00. Shall I place this order?')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Message to the shop assistant'), { target: { value: 'yes' } })
    fireEvent.keyDown(screen.getByLabelText('Message to the shop assistant'), { key: 'Enter' })
    expect(await screen.findByText('Done! Your order is confirmed.')).toBeTruthy()
    const link = screen.getByRole('link', { name: /See your order status/ })
    expect(link.getAttribute('href')).toBe('/o/abcdef123456?t=tok')
    expect(screen.getByText('Confirmed')).toBeTruthy()
    const chatCalls = calls.filter((c) => c.url.endsWith('/chat')).map((c) => JSON.parse(String(c.init?.body)))
    expect(chatCalls).toEqual([
      { chat_id: null, message: '2 boxes of kuih lapis 20 pcs, Siti +65 9123 4567' },
      { chat_id: 'c1', message: 'yes' },
    ])
  })

  it('shows a friendly message when the assistant is down, and the order form still works', async () => {
    stubApi((url) => {
      if (url === '/api/public/shops/mak-kuih') return { body: PAGE }
      if (url.endsWith('/chat')) return { status: 503, body: { detail: "The AI assistant isn't available right now. You can still order with the form below." } }
      return undefined
    })
    renderAt('/s/mak-kuih', routes)
    fireEvent.click(await screen.findByRole('button', { name: /Try:/ }))
    expect((await screen.findByRole('alert')).textContent).toContain("The AI assistant isn't available right now. You can still order with the form below.")
    expect(screen.getAllByRole('button', { name: /Add/ }).length).toBeGreaterThan(0)
  })

  it('offers a new chat when the old one has ended', async () => {
    stubApi((url) => {
      if (url === '/api/public/shops/mak-kuih') return { body: PAGE }
      if (url.endsWith('/chat')) return { status: 410, body: { detail: 'This chat has ended or timed out. Start a new chat to continue.' } }
      return undefined
    })
    renderAt('/s/mak-kuih', routes)
    fireEvent.click(await screen.findByRole('button', { name: /Try:/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Start a new chat' }))
    expect(screen.getByLabelText('Message to the shop assistant')).toBeTruthy()
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
    await screen.findByRole('region', { name: 'Ordering with AI' })
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

  it('lets anyone report the shop', async () => {
    const calls = stubApi((url, init) => {
      if (url === '/api/public/shops/mak-kuih') return { body: PAGE }
      if (url === '/api/public/shops/mak-kuih/report' && init?.method === 'POST') return { body: { message: "Thank you. We'll look into it." } }
      return undefined
    })
    renderAt('/s/mak-kuih', routes)
    fireEvent.click(await screen.findByRole('button', { name: 'Report this shop' }))
    fireEvent.change(screen.getByLabelText("What's wrong?"), { target: { value: 'not_real' } })
    fireEvent.change(screen.getByLabelText('Details (optional)'), { target: { value: 'No such shop' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send report' }))
    expect(await screen.findByText("Thank you. We'll look into it.")).toBeTruthy()
    const sent = calls.find((c) => c.url.endsWith('/report'))!
    expect(JSON.parse(String(sent.init!.body))).toEqual({ reason: 'not_real', details: 'No such shop', email: '' })
  })

  it('still links home when the shop is not found', async () => {
    stubApi(() => undefined)
    renderAt('/s/nope', routes)
    expect(await screen.findByText(/isn't open on KampungCart/)).toBeTruthy()
    expect(screen.getByRole('link', { name: /Make one for your shop/ }).getAttribute('href')).toBe('/')
  })
})
