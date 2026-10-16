import { fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Landed } from '../test/Landed'
import { renderAt, stubApi } from '../test/render'
import { LinkLanding } from './LinkLanding'
import { Login } from './Login'

const routes = [
  { path: '/login', element: <Login /> },
  { path: '/signin', element: <LinkLanding kind="signin" /> },
  { path: '/verify', element: <LinkLanding kind="verify" /> },
  { path: '/shop/:id/orders', element: <Landed /> },
  { path: '/', element: <Landed /> },
]
const SIGNED_IN = { shop_id: 'mak-kuih', name: "Mak's Kuih", slug: 'mak-kuih', published: true, next: '/shop/mak-kuih/orders' }

describe('shop owner login', () => {
  it('asks for an email only and sends a sign-in link', async () => {
    const calls = stubApi((url) => (url === '/api/owner/email-link' ? { body: { message: 'If that email has a shop on KampungCart, we sent a link.' } } : undefined))
    renderAt('/login', routes)
    expect(screen.queryByLabelText('Backup key')).toBeNull()
    fireEvent.change(screen.getByLabelText('Your email'), { target: { value: 'siti@example.sg' } })
    fireEvent.click(screen.getByRole('button', { name: 'Email me a sign-in link' }))
    expect(await screen.findByRole('heading', { name: 'Check your email' })).toBeTruthy()
    expect(screen.getByRole('status').textContent).toContain('siti@example.sg')
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ email: 'siti@example.sg' })
  })

  it('keeps the backup key as a second way in', async () => {
    stubApi((url) => (url === '/api/owner/login' ? { body: SIGNED_IN } : undefined))
    renderAt('/login', routes)
    fireEvent.click(screen.getByRole('button', { name: 'Use backup key instead' }))
    fireEvent.change(screen.getByLabelText('Backup key'), { target: { value: 'kc_sample' } })
    fireEvent.click(screen.getByRole('button', { name: 'Open my shop' }))
    expect((await screen.findByTestId('landed')).dataset.path).toBe('/shop/mak-kuih/orders')
  })

  it('a sign-in link waits for a tap, then opens the dashboard', async () => {
    const calls = stubApi((url) => (url === '/api/owner/signin' ? { body: SIGNED_IN } : undefined))
    renderAt('/signin?token=abc123', routes)
    expect(calls).toHaveLength(0) // opening the link alone uses nothing up
    fireEvent.click(screen.getByRole('button', { name: /Open my dashboard/ }))
    expect((await screen.findByTestId('landed')).dataset.path).toBe('/shop/mak-kuih/orders')
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ token: 'abc123' })
  })

  it('an expired link says so and offers a new one', async () => {
    stubApi((url) => (url === '/api/owner/signin' ? { status: 400, body: { detail: 'This link has expired or was already used. Ask for a new one below.' } } : undefined))
    renderAt('/signin?token=old', routes)
    fireEvent.click(screen.getByRole('button', { name: /Open my dashboard/ }))
    expect(await screen.findByText(/expired or was already used/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Email me a sign-in link' })).toBeTruthy()
  })

  it('the confirm link confirms the email with a tap and signs in', async () => {
    stubApi((url) => (url === '/api/owner/verify' ? { body: SIGNED_IN } : undefined))
    renderAt('/verify?token=v1', routes)
    expect(screen.getByRole('heading', { name: 'Confirm your email' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Confirm my email/ }))
    expect((await screen.findByTestId('landed')).dataset.path).toBe('/shop/mak-kuih/orders')
  })
})

describe('home header', () => {
  it('login page has no login link to itself', () => {
    renderAt('/login', routes)
    expect(within(screen.getByRole('banner')).queryByRole('link', { name: /Shop owner login/ })).toBeNull()
  })
})
