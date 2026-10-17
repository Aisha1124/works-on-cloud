import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderAt, stubApi } from '../test/render'
import { Privacy } from './Privacy'

const routes = [{ path: '/privacy', element: <Privacy /> }]

describe('privacy page', () => {
  it('says what is kept, for how long, and who to ask for deletion', async () => {
    stubApi((url) => (url === '/api/public/site' ? { body: { admin_email: 'help@kc.example', retention_days: 90 } } : undefined))
    renderAt('/privacy', routes)
    const link = await screen.findByRole('link', { name: 'help@kc.example' })
    expect(link.getAttribute('href')).toBe('mailto:help@kc.example')
    expect(screen.getByText(/90 days after the pickup time/)).toBeTruthy()
    expect(screen.getByText(/only shared with the shop you order from/)).toBeTruthy()
  })

  it('points to the shop when no contact email is set', async () => {
    stubApi((url) => (url === '/api/public/site' ? { body: { admin_email: '', retention_days: 90 } } : undefined))
    renderAt('/privacy', routes)
    expect(await screen.findByText(/Contact the shop you ordered from/)).toBeTruthy()
  })
})
