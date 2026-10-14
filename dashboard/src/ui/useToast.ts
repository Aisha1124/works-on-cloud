import { createContext, useContext, type ReactNode } from 'react'

export type ToastTone = 'success' | 'error' | 'info'

export interface ToastApi {
  show: (message: ReactNode, tone?: ToastTone) => void
}

export const ToastContext = createContext<ToastApi | null>(null)

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}
