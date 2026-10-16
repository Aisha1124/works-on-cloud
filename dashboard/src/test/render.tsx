import { render } from '@testing-library/react'
import { RouterProvider, createMemoryRouter, type RouteObject } from 'react-router'
import { vi } from 'vitest'
import { ToastProvider } from '../ui'

/** Render routes at `path`, inside the same providers as the app. */
export function renderAt(path: string, routes: RouteObject[]) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <ToastProvider>
      <RouterProvider router={router} />
    </ToastProvider>,
  )
  return router
}

type Handler = (url: string, init?: RequestInit) => { status?: number; body: unknown } | undefined

/** Stub fetch: `handler` answers by URL; anything it doesn't answer is a 404. */
export function stubApi(handler: Handler) {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push({ url, init })
      const res = handler(url, init) ?? { status: 404, body: { detail: 'Not found.' } }
      return new Response(JSON.stringify(res.body), { status: res.status ?? 200, headers: { 'Content-Type': 'application/json' } })
    }),
  )
  return calls
}
