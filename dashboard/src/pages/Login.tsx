import { Link, useNavigate } from 'react-router'
import { OwnerBar } from '../components/OwnerShell'
import { OwnerKeyForm } from '../components/OwnerKeyForm'

/** /login: owner key -> that shop's orders. */
export function Login() {
  const navigate = useNavigate()
  return (
    <main className="mx-auto flex max-w-xl flex-col gap-6 px-4 py-6 sm:py-10">
      <OwnerBar showLogin={false} />
      <OwnerKeyForm onSignedIn={(shop) => navigate(`/shop/${shop.shop_id}/orders`)} />
      <p className="text-sm text-ink-soft">
        New here? Your owner key is created when your shop goes live.{' '}
        <Link to="/" className="focus-ring font-semibold underline">
          Start with a photo of your menu
        </Link>
        .
      </p>
    </main>
  )
}
