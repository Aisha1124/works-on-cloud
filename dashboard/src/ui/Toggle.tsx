import { useId, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { cx } from './cx'

export interface ToggleProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onChange'> {
  checked: boolean
  onChange: (checked: boolean) => void
  label: ReactNode
  /** Small text under the label. */
  hint?: ReactNode
}

export function Toggle({ checked, onChange, label, hint, disabled, className, id, ...rest }: ToggleProps) {
  const auto = useId()
  const switchId = id ?? auto
  return (
    <div className={cx('flex items-center gap-3', className)}>
      <button
        id={switchId}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-describedby={hint ? `${switchId}-hint` : undefined}
        disabled={disabled}
        className="toggle-track"
        onClick={() => onChange(!checked)}
        {...rest}
      />
      <label htmlFor={switchId} className={cx('flex flex-col', disabled ? 'cursor-not-allowed' : 'cursor-pointer')}>
        <span className="font-semibold">{label}</span>
        {hint && (
          <span id={`${switchId}-hint`} className="text-sm text-ink-soft">
            {hint}
          </span>
        )}
      </label>
    </div>
  )
}
