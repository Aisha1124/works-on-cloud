import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderAt, stubApi } from '../test/render'
import type { WebOrder } from '../lib/types'
import { OrderStatus } from './OrderStatus'

const ORDER: WebOrder = {
  order_id: 'abc123',
  shop_slug: 'mak-kuih',
  shop_name: "Mak's Kuih",
  status: 'confirmed',
  message: 'Order confirmed. See you at pickup.',
  rejection_reason: '',
  expired: false,
  items: [{ name: 'Kuih Lapis', variant: '20 pcs', options: {}, qty: 2, unit_price: '16.00', line_total: '32.00' }],
  total: '32.00',
  currency: 'SGD',
  pickup_time: '2026-10-24T10:00:00+08:00',
  status_url: 'https://kc.example/o/abc123?t=secret-token',
  can_cancel: true,
  cancel_until: '2026-10-23T22:00:00+08:00',
  email_updates_to: 's***@example.sg',
}

const routes = [{ path: '/o/:id', element: <OrderStatus /> }]
const URL_OK = '/api/public/orders/abc123?t=secret-token'

describe('customer order status page', () => {
  it('shows the order, the link to save, and where updates go', async () => {
    stubApi((url) => (url === URL_OK ? { body: ORDER } : undefined))
    renderAt('/o/abc123?t=secret-token', routes)
    expect(await screen.findByRole('heading', { name: 'Confirmed' })).toBeTruthy()
    expect(screen.getByText('Save this link to check your order')).toBeTruthy()
    expect(screen.getByText(/\/o\/abc123\?t=secret-token$/)).toBeTruthy()
    expect(screen.getByText(/s\*\*\*@example\.sg/)).toBeTruthy()
    expect(screen.getByRole('link', { name: /Back to Mak's Kuih/ }).getAttribute('href')).toBe('/s/mak-kuih')
  })

  it('cancels only after a second tap', async () => {
    const calls = stubApi((url, init) => {
      if (url === URL_OK) return { body: ORDER }
      if (url === '/api/public/orders/abc123/cancel?t=secret-token' && init?.method === 'POST')
        return { body: { ...ORDER, status: 'cancelled', can_cancel: false, message: 'This order was cancelled by the customer.' } }
      return undefined
    })
    renderAt('/o/abc123?t=secret-token', routes)
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel order' }))
    expect(calls.some((c) => c.url.includes('/cancel'))).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Yes, cancel it' }))
    expect(await screen.findByRole('heading', { name: 'You cancelled this order' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Cancel order' })).toBeNull()
  })

  it('shows an expired order plainly', async () => {
    stubApi((url) =>
      url === URL_OK
        ? { body: { ...ORDER, status: 'rejected', expired: true, can_cancel: false, message: "The shop didn't respond in time, so this order is cancelled." } }
        : undefined,
    )
    renderAt('/o/abc123?t=secret-token', routes)
    expect(await screen.findByRole('heading', { name: "The shop didn't respond in time" })).toBeTruthy()
    expect(screen.getByText('Expired')).toBeTruthy()
  })

  it('says it cannot find the order when the link is wrong', async () => {
    stubApi(() => undefined)
    renderAt('/o/abc123?t=wrong', routes)
    expect(await screen.findByText(/We can't find that order/)).toBeTruthy()
  })
})
