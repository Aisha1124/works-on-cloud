import { Link } from 'react-router'
import { EmptyState, buttonClass } from '../ui'

export function NotFound() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <EmptyState
        message="Nothing here, lah."
        action={
          <Link to="/" className={buttonClass('secondary')}>
            Back to home
          </Link>
        }
      />
    </main>
  )
}
