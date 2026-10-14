import { ChevronDown, TriangleAlert } from 'lucide-react'
import {
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import { cx } from './cx'

interface FieldChrome {
  label: ReactNode
  hint?: ReactNode
  error?: ReactNode
  className?: string
}

function useFieldIds(id?: string) {
  const auto = useId()
  const base = id ?? auto
  return { id: base, hintId: `${base}-hint`, errorId: `${base}-error` }
}

function describedBy(ids: ReturnType<typeof useFieldIds>, hint?: ReactNode, error?: ReactNode) {
  return [hint && ids.hintId, error && ids.errorId].filter(Boolean).join(' ') || undefined
}

function Shell({
  ids,
  label,
  hint,
  error,
  className,
  children,
}: FieldChrome & { ids: ReturnType<typeof useFieldIds>; children: ReactNode }) {
  return (
    <div className={cx('flex flex-col gap-1.5', className)}>
      <label htmlFor={ids.id} className="text-sm font-semibold">
        {label}
      </label>
      {children}
      {hint && !error && (
        <p id={ids.hintId} className="text-sm text-ink-soft">
          {hint}
        </p>
      )}
      {error && (
        <p id={ids.errorId} className="flex items-start gap-1.5 text-sm font-medium text-ink">
          <TriangleAlert aria-hidden className="mt-0.5 size-4 flex-none text-chili" />
          <span>{error}</span>
        </p>
      )}
    </div>
  )
}

export type InputProps = FieldChrome & Omit<InputHTMLAttributes<HTMLInputElement>, 'className'>

export function Input({ label, hint, error, className, id, ...rest }: InputProps) {
  const ids = useFieldIds(id)
  return (
    <Shell ids={ids} label={label} hint={hint} error={error} className={className}>
      <input
        id={ids.id}
        className="control"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(ids, hint, error)}
        {...rest}
      />
    </Shell>
  )
}

export type TextareaProps = FieldChrome & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'className'>

export function Textarea({ label, hint, error, className, id, ...rest }: TextareaProps) {
  const ids = useFieldIds(id)
  return (
    <Shell ids={ids} label={label} hint={hint} error={error} className={className}>
      <textarea
        id={ids.id}
        className="control"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(ids, hint, error)}
        {...rest}
      />
    </Shell>
  )
}

export type SelectProps = FieldChrome & Omit<SelectHTMLAttributes<HTMLSelectElement>, 'className'>

export function Select({ label, hint, error, className, id, children, ...rest }: SelectProps) {
  const ids = useFieldIds(id)
  return (
    <Shell ids={ids} label={label} hint={hint} error={error} className={className}>
      <div className="relative">
        <select
          id={ids.id}
          className="control"
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(ids, hint, error)}
          {...rest}
        >
          {children}
        </select>
        <ChevronDown aria-hidden className="pointer-events-none absolute top-1/2 right-3 size-5 -translate-y-1/2" />
      </div>
    </Shell>
  )
}
