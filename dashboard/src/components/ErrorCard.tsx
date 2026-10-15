import { RotateCcw, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button, Card, cx } from '../ui'

/** A friendly problem, printed on a chili-edged slip, with an optional retry. */
export function ErrorCard({
  message,
  onRetry,
  action,
  className,
}: {
  message: ReactNode
  onRetry?: () => void
  action?: ReactNode
  className?: string
}) {
  return (
    <Card role="alert" className={cx('flex flex-col gap-4 border-l-8 border-l-chili sm:flex-row sm:items-center', className)}>
      <TriangleAlert aria-hidden className="size-7 flex-none text-chili" />
      <p className="flex-1 text-lg font-semibold">{message}</p>
      <div className="flex flex-wrap gap-3">
        {onRetry && (
          <Button variant="secondary" icon={<RotateCcw aria-hidden className="size-4" />} onClick={onRetry}>
            Try again
          </Button>
        )}
        {action}
      </div>
    </Card>
  )
}
