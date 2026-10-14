import { CircleCheck, Info, TriangleAlert, X } from 'lucide-react'
import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react'
import { cx } from './cx'
import { ToastContext, type ToastTone } from './useToast'

interface ToastItem {
  id: number
  tone: ToastTone
  message: ReactNode
}

const toneStyle: Record<ToastTone, { bar: string; Icon: typeof Info; label: string }> = {
  success: { bar: 'border-l-pandan', Icon: CircleCheck, label: 'Done' },
  error: { bar: 'border-l-chili', Icon: TriangleAlert, label: 'Problem' },
  info: { bar: 'border-l-turmeric', Icon: Info, label: 'Note' },
}

const iconColor: Record<ToastTone, string> = {
  success: 'text-pandan',
  error: 'text-chili',
  info: 'text-ink',
}

export function ToastProvider({ children, duration = 4500 }: { children: ReactNode; duration?: number }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((all) => all.filter((t) => t.id !== id))
  }, [])

  const show = useCallback(
    (message: ReactNode, tone: ToastTone = 'info') => {
      const id = nextId.current++
      setToasts((all) => [...all.slice(-3), { id, tone, message }])
      window.setTimeout(() => dismiss(id), duration)
    },
    [dismiss, duration],
  )

  const api = useMemo(() => ({ show }), [show])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col items-end gap-3 sm:inset-x-auto sm:right-6 sm:bottom-6 sm:w-96"
      >
        {toasts.map((t) => {
          const { bar, Icon, label } = toneStyle[t.tone]
          return (
            <div
              key={t.id}
              role="status"
              className={cx(
                'toast-enter pointer-events-auto flex w-full items-start gap-3 border-2 border-l-8 border-ink bg-receipt p-3 shadow-hard',
                bar,
              )}
            >
              <Icon aria-hidden className={cx('mt-0.5 size-5 flex-none', iconColor[t.tone])} />
              <div className="min-w-0 flex-1">
                <span className="sr-only">{label}: </span>
                {t.message}
              </div>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                className="focus-ring -m-1 p-1 hover:bg-paper"
                aria-label="Dismiss"
              >
                <X aria-hidden className="size-4" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}
