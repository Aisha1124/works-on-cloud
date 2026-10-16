// Browser APIs jsdom doesn't have. Tests never touch the network: each one stubs fetch.
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  sessionStorage.clear()
})

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} }),
})
Element.prototype.scrollIntoView = function scrollIntoView() {}
window.scrollTo = () => {}
URL.createObjectURL = () => 'blob:photo'
URL.revokeObjectURL = () => {}
// QR codes draw on a canvas; jsdom has none. Nothing is drawn in tests.
HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement['getContext']
