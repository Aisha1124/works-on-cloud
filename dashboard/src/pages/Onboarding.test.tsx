import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { getOwnerKey } from '../lib/ownerKey'
import { Landed } from '../test/Landed'
import { renderAt, stubApi } from '../test/render'
import { Onboarding } from './Onboarding'

const routes = [
  { path: '/', element: <Onboarding /> },
  { path: '/s/:slug', element: <Landed /> },
  { path: '/login', element: <Landed /> },
  { path: '/shop/:id', element: <Landed /> },
  { path: '/shop/:id/live', element: <Landed /> },
]

const DRAFT = {
  shop: { id: 'shop1', slug: 'auntie-lim-ab12', name: "Auntie Lim's Bakes", published: false },
  products: [
    { id: 'p1', shop_id: 'shop1', name: 'Pandan Chiffon', name_local: '', category: 'Cakes', base_price: '18.00', unit: '1 whole', variants: [], options: [], available: true, description: '', confidence: 0.95 },
    { id: 'p2', shop_id: 'shop1', name: 'Kaya Puff', name_local: '', category: 'Pastries', base_price: '7.20', unit: '6 pcs', variants: [], options: [], available: true, description: '', confidence: 0.9 },
  ],
  warnings: [],
  draft_key: 'kc_draft',
}

function uploadPhoto() {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
  fireEvent.change(input, { target: { files: [new File(['x'], 'menu.jpg', { type: 'image/jpeg' })] } })
}

describe('home page', () => {
  it('has one door for shop owners and one for customers, and no small text link', () => {
    renderAt('/', routes)
    const owner = screen.getByRole('button', { name: /I run a shop.*Upload my menu/i })
    const customer = screen.getByRole('link', { name: /I'm a customer.*See a live shop/i })
    expect(owner).toBeTruthy()
    expect(customer.getAttribute('href')).toBe('/s/mak-kuih')
    expect(screen.queryByText(/See a live shop:/)).toBeNull()
  })

  it('"Upload my menu" scrolls to and focuses the upload box', () => {
    renderAt('/', routes)
    const heading = screen.getByRole('heading', { name: 'Upload your menu' })
    const scroll = vi.spyOn(heading, 'scrollIntoView')
    fireEvent.click(screen.getByRole('button', { name: /Upload my menu/i }))
    expect(scroll).toHaveBeenCalled()
    expect(document.activeElement).toBe(heading)
  })

  it('"See a live shop" opens the sample shop', async () => {
    renderAt('/', routes)
    fireEvent.click(screen.getByRole('link', { name: /See a live shop/i }))
    expect((await screen.findByTestId('landed')).dataset.path).toBe('/s/mak-kuih')
  })

  it('explains the whole journey once, in four steps', () => {
    renderAt('/', routes)
    const strip = screen.getByRole('region', { name: 'How KampungCart works' })
    const steps = within(strip).getAllByRole('listitem')
    expect(steps).toHaveLength(4)
    expect(steps[0].textContent).toMatch(/menu photo.*Gemini/i)
    expect(steps[1].textContent).toMatch(/Go live.*shop link, QR code and owner key/i)
    expect(steps[2].textContent).toMatch(/AI assistant \(Claude, Gemini\)/)
    expect(steps[3].textContent).toMatch(/confirm automatically.*owner's OK/i)
    expect(screen.queryByText('How it works')).toBeNull()
  })

  it('has a shop owner login link at the top', () => {
    renderAt('/', routes)
    expect(screen.getByRole('link', { name: /Shop owner login/i }).getAttribute('href')).toBe('/login')
  })
})

describe('after the menu is read', () => {
  it('shows a sticky "Looks right? Go live" bar that publishes and shows the key once', async () => {
    const calls = stubApi((url) => {
      if (url === '/api/shops/draft') return { body: DRAFT }
      if (url === '/api/shops/shop1/publish')
        return { body: { shop: { ...DRAFT.shop, published: true }, products: DRAFT.products, links: {}, owner_key: 'kc_owner' } }
    })
    renderAt('/', routes)
    uploadPhoto()

    const bar = await screen.findByRole('region', { name: 'Next step' })
    expect(bar.className).toMatch(/fixed/)
    expect(within(bar).getByText('2 items read')).toBeTruthy()
    expect(within(bar).getByRole('link', { name: 'Fix something first' }).getAttribute('href')).toBe('/shop/shop1')
    expect(getOwnerKey('shop1')).toBe('kc_draft')

    fireEvent.click(within(bar).getByRole('button', { name: /Looks right\? Go live/ }))
    const landed = await screen.findByTestId('landed')
    expect(landed.dataset.path).toBe('/shop/shop1/live')
    expect(JSON.parse(landed.dataset.state!)).toEqual({ ownerKey: 'kc_owner' })
    expect(getOwnerKey('shop1')).toBe('kc_owner')
    expect(calls.find((c) => c.url.endsWith('/publish'))?.init?.headers).toMatchObject({ 'X-Owner-Key': 'kc_draft' })
  })

  it('keeps the owner on the page with a friendly message if going live fails', async () => {
    stubApi((url) => {
      if (url === '/api/shops/draft') return { body: DRAFT }
      if (url.endsWith('/publish')) return { status: 400, body: { detail: 'Add at least one available item with a price first.' } }
    })
    renderAt('/', routes)
    uploadPhoto()
    fireEvent.click(await screen.findByRole('button', { name: /Looks right\? Go live/ }))
    expect(await screen.findByText('Add at least one available item with a price first.')).toBeTruthy()
    expect(screen.queryByTestId('landed')).toBeNull()
  })

  it('offers to add items by hand when nothing was read, instead of going live', async () => {
    stubApi((url) => (url === '/api/shops/draft' ? { body: { ...DRAFT, products: [] } } : undefined))
    renderAt('/', routes)
    uploadPhoto()
    await waitFor(() => expect(screen.getByRole('button', { name: /Add items by hand/ })).toBeTruthy())
    expect(screen.queryByRole('region', { name: 'Next step' })).toBeNull()
  })
})
