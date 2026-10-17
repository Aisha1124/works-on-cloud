import { ArrowRight } from 'lucide-react'
import { useEffect } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { ErrorCard } from '../components/ErrorCard'
import { OrderStatusCard } from '../components/OrderStatusCard'
import { api } from '../lib/api'
import { useLoad } from '../lib/hooks'
import type { WebOrder } from '../lib/types'
import { EmptyState, Skeleton, buttonClass } from '../ui'

/** /o/{id}?t={token}: a customer's private order page, from the link they saved or were emailed. */
export function OrderStatus() {
  const { id = '' } = useParams()
  const [params] = useSearchParams()
  const token = params.get('t') ?? ''
  const order = useLoad(
    (signal) => api<WebOrder>(`/api/public/orders/${encodeURIComponent(id)}?t=${encodeURIComponent(token)}`, { owner: false, signal }),
    `${id}:${token}`,
  )

  useEffect(() => {
    document.title = order.data ? `Your order · ${order.data.shop_name}` : 'Your order · KampungCart'
  }, [order.data])

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 pt-6 pb-16 sm:pt-10">
      {order.error && !order.data ? (
        order.errorStatus === 404 ? (
          <EmptyState message="We can't find that order. Check that you opened the full link from your confirmation." />
        ) : (
          <ErrorCard message={order.error} onRetry={order.reload} />
        )
      ) : !order.data ? (
        <Skeleton rows={6} label="Loading your order" />
      ) : (
        <OrderStatusCard
          key={order.data.order_id}
          initial={order.data}
          token={token}
          footer={
            <Link to={`/s/${order.data.shop_slug}`} className={buttonClass('secondary')}>
              Back to {order.data.shop_name} <ArrowRight aria-hidden className="size-4" />
            </Link>
          }
        />
      )}
      <footer className="border-t-2 border-dashed border-ink pt-4 text-center text-sm text-ink-soft">
        Orders by <span className="font-semibold text-ink">KampungCart</span> · pay the shop at pickup ·{' '}
        <Link to="/privacy" className="focus-ring font-semibold text-ink underline underline-offset-4">
          Privacy
        </Link>
      </footer>
    </main>
  )
}
