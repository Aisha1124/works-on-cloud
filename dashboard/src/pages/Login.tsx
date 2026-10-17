import { Link, useNavigate } from 'react-router'
import { OwnerSignIn } from '../components/OwnerKeyForm'
import { OwnerBar } from '../components/OwnerShell'

/** /login: email link (or backup key) -> that shop's dashboard. */
export function Login() {
  const navigate = useNavigate()
  return (
    <main className="mx-auto flex max-w-xl flex-col gap-6 px-4 py-6 sm:py-10">
      <OwnerBar showLogin={false} />
      <OwnerSignIn onSignedIn={(s) => navigate(s.next || `/shop/${s.shop_id}/orders`)} />
      <p className="text-sm text-ink-soft">
        New here? You create your shop when it goes live.{' '}
        <Link to="/" className="focus-ring font-semibold underline">
          Start with a photo of your menu
        </Link>
        .
      </p>
    </main>
  )
}
