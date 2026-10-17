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
    const customer = screen.getByRole('link', { name: /See what customers see.*Try Mak's Kuih/i })
    expect(owner).toBeTruthy()
    expect(customer.getAttribute('href')).toBe('/s/mak-kuih')
    expect(screen.queryByText(/See a live shop/)).toBeNull()
  })

  it('"Upload my menu" scrolls to and focuses the upload box', () => {
    renderAt('/', routes)
    const heading = screen.getByRole('heading', { name: 'Upload your menu' })
    const scroll = vi.spyOn(heading, 'scrollIntoView')
    fireEvent.click(screen.getByRole('button', { name: /Upload my menu/i }))
    expect(scroll).toHaveBeenCalled()
    expect(document.activeElement).toBe(heading)
  })

  it('"Try Mak\'s Kuih" opens the sample shop', async () => {
    renderAt('/', routes)
    fireEvent.click(screen.getByRole('link', { name: /Try Mak's Kuih/i }))
    expect((await screen.findByTestId('landed')).dataset.path).toBe('/s/mak-kuih')
  })

  it('explains the whole journey once, in four steps', () => {
    renderAt('/', routes)
    const strip = screen.getByRole('region', { name: 'How KampungCart works' })
    const steps = within(strip).getAllByRole('listitem')
    expect(steps).toHaveLength(4)
    expect(steps[0].textContent).toMatch(/menu photo.*Gemini/i)
    expect(steps[1].textContent).toMatch(/Go live.*shop link, QR code and owner key/i)
    expect(steps[2].textContent).toMatch(/Any AI can read the menu.*AI apps connected through MCP can also order/)
    expect(steps[3].textContent).toMatch(/confirm automatically.*owner's OK/i)
    expect(screen.queryByText('How it works')).toBeNull()
  })

  it('has a shop owner login link at the top', () => {
    renderAt('/', routes)
    expect(screen.getByRole('link', { name: /Shop owner login/i }).getAttribute('href')).toBe('/login')
  })
})

describe('after the menu is read', () => {
  const live = { shop: { ...DRAFT.shop, published: true }, products: DRAFT.products, links: {}, owner_key: 'kc_backup', verify_sent_to: 'siti@example.sg' }

  it('says no account is needed to start', () => {
    renderAt('/', routes)
    expect(screen.getByText("Free. No account needed to start. You'll create your shop at the end.")).toBeTruthy()
  })

  it('shows a sticky "Looks right? Go live" bar', async () => {
    stubApi((url) => (url === '/api/shops/draft' ? { body: DRAFT } : undefined))
    renderAt('/', routes)
    uploadPhoto()
    const bar = await screen.findByRole('region', { name: 'Next step' })
    expect(bar.className).toMatch(/fixed/)
    expect(within(bar).getByText('2 items read')).toBeTruthy()
    expect(within(bar).getByRole('link', { name: 'Fix something first' }).getAttribute('href')).toBe('/shop/shop1')
    expect(getOwnerKey('shop1')).toBe('kc_draft')
  })

  it('Go live asks for shop name and email, creates the shop and shows the backup key once', async () => {
    const calls = stubApi((url) => {
      if (url === '/api/shops/draft') return { body: DRAFT }
      if (url === '/api/shops/shop1/publish') return { body: live }
    })
    renderAt('/', routes)
    uploadPhoto()
    fireEvent.click(await screen.findByRole('button', { name: /Looks right\? Go live/ }))

    const dialog = screen.getByRole('dialog', { name: 'Create your shop' })
    const name = within(dialog).getByLabelText('Shop name') as HTMLInputElement
    expect(name.value).toBe("Auntie Lim's Bakes")
    fireEvent.click(within(dialog).getByRole('button', { name: /Go live/ }))
    expect(within(dialog).getByText('Your email, so we can send you orders.')).toBeTruthy()
    expect(calls.some((c) => c.url.endsWith('/publish'))).toBe(false)

    fireEvent.change(within(dialog).getByLabelText('Your email'), { target: { value: 'siti@example.sg' } })
    fireEvent.click(within(dialog).getByRole('button', { name: /Go live/ }))
    const landed = await screen.findByTestId('landed')
    expect(landed.dataset.path).toBe('/shop/shop1/live')
    expect(JSON.parse(landed.dataset.state!)).toEqual({ ownerKey: 'kc_backup' })

    const publish = calls.find((c) => c.url.endsWith('/publish'))!
    expect(JSON.parse(String(publish.init?.body))).toEqual({ name: "Auntie Lim's Bakes", email: 'siti@example.sg' })
    expect(publish.init?.headers).toMatchObject({ 'X-Owner-Key': 'kc_draft' })
    // The browser is now signed in by cookie; the dead draft key is dropped from the tab.
    expect(getOwnerKey('shop1')).toBeNull()
  })

  it('shows the server problem in the dialog if going live fails', async () => {
    stubApi((url) => {
      if (url === '/api/shops/draft') return { body: DRAFT }
      if (url.endsWith('/publish')) return { status: 400, body: { detail: 'Add at least one available item with a price first.' } }
    })
    renderAt('/', routes)
    uploadPhoto()
    fireEvent.click(await screen.findByRole('button', { name: /Looks right\? Go live/ }))
    const dialog = screen.getByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Your email'), { target: { value: 'siti@example.sg' } })
    fireEvent.click(within(dialog).getByRole('button', { name: /Go live/ }))
    expect(await within(dialog).findByText('Add at least one available item with a price first.')).toBeTruthy()
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
