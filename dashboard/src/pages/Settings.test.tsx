import { fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ShopLayout } from '../components/ShopLayout'
import { setOwnerKey } from '../lib/ownerKey'
import { renderAt, stubApi } from '../test/render'
import { Settings } from './Settings'

const LINKS = { ucp_profile: 'https://kc.example/.well-known/ucp', mcp: 'https://kc.example/mcp', public_page: 'https://kc.example/s/mak-kuih' }
const SHOP = {
  id: 'shop1', slug: 'mak-kuih', name: "Mak's Kuih", tagline: '', shop_type: '', address: '', hours: 'Mon closed; Tue-Sun 9am-6pm', phone: '',
  currency: 'SGD', auto_approve_limit: '150.00', published: false, owner_email: '', email_verified: false, created_at: '2026-10-16T00:00:00Z',
  approval_timeout_hours: 24, cancel_cutoff_hours: 12, min_notice_hours: 24, daily_capacity: null, paused_until: null,
}
const HOURS = [0, 1, 2, 3, 4, 5, 6].map((day) => ({ day, closed: day === 0, open: '09:00', close: '18:00' }))
const routes = [{ path: '/shop/:id', element: <ShopLayout />, children: [{ path: 'settings', element: <Settings /> }] }]

function setup() {
  setOwnerKey('shop1', 'kc_key')
  return stubApi((url, init) => {
    if (url === '/api/shops/shop1' && init?.method === 'PATCH') return { body: { ...SHOP, ...JSON.parse(String(init.body)) } }
    if (url === '/api/shops/shop1') return { body: { shop: SHOP, products: [], links: LINKS, checks: {}, opening_hours: HOURS, hours_readable: true } }
    return undefined
  })
}

describe('owner settings', () => {
  it('shows the weekly hours and saves every setting in one go', async () => {
    const calls = setup()
    renderAt('/shop/shop1/settings', routes)
    const monday = (await screen.findByText('Monday')).closest('li')!
    expect(within(monday).getByRole('switch').getAttribute('aria-checked')).toBe('false')
    expect((screen.getByLabelText('Tuesday opens') as HTMLInputElement).value).toBe('09:00')

    fireEvent.change(screen.getByLabelText('Most orders per pickup day'), { target: { value: '8' } })
    fireEvent.change(screen.getByLabelText('Minimum notice (hours)'), { target: { value: '48' } })
    fireEvent.change(screen.getByLabelText('Saturday closes'), { target: { value: '13:00' } })
    fireEvent.click(screen.getByRole('switch', { name: /Pause orders/ }))
    fireEvent.change(screen.getByLabelText('Take orders again from'), { target: { value: '2099-01-05' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }))

    expect(await screen.findByText('Settings saved.')).toBeTruthy()
    const patch = calls.find((c) => c.init?.method === 'PATCH')!
    const body = JSON.parse(String(patch.init!.body))
    expect(body).toMatchObject({ min_notice_hours: 48, daily_capacity: 8, approval_timeout_hours: 24, cancel_cutoff_hours: 12, auto_approve_limit: '150.00', paused_until: '2099-01-05' })
    expect(body.opening_hours[5]).toEqual({ day: 5, closed: false, open: '09:00', close: '13:00' })
    expect(body.opening_hours[0].closed).toBe(true)
  })

  it('picks one of the preset shop colours and saves it', async () => {
    const calls = setup()
    renderAt('/shop/shop1/settings', routes)
    const group = await screen.findByRole('group', { name: 'Shop colour' })
    const radios = within(group).getAllByRole('radio') as HTMLInputElement[]
    expect(radios.map((r) => r.value)).toEqual(['chili', 'pandan', 'kopi', 'laut', 'bunga', 'charcoal'])
    expect((within(group).getByRole('radio', { name: 'Chili red' }) as HTMLInputElement).checked).toBe(true)
    expect(within(group).queryByRole('textbox')).toBeNull()

    fireEvent.click(within(group).getByRole('radio', { name: 'Pandan green' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(await screen.findByText('Settings saved.')).toBeTruthy()
    const body = JSON.parse(String(calls.find((c) => c.init?.method === 'PATCH')!.init!.body))
    expect(body.theme_colour).toBe('pandan')
  })

  it('checks the numbers before saving', async () => {
    const calls = setup()
    renderAt('/shop/shop1/settings', routes)
    fireEvent.change(await screen.findByLabelText('Minimum notice (hours)'), { target: { value: 'soon' } })
    fireEvent.click(screen.getByRole('switch', { name: /Pause orders/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(await screen.findByText('A whole number of hours, 0 to 336.')).toBeTruthy()
    expect(screen.getByText('Pick the day you take orders again.')).toBeTruthy()
    expect(calls.some((c) => c.init?.method === 'PATCH')).toBe(false)
  })
})
