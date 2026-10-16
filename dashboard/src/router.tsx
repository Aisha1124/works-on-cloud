import { createBrowserRouter } from 'react-router'
import { ShopLayout } from './components/ShopLayout'
import { Audit } from './pages/Audit'
import { CatalogReview } from './pages/CatalogReview'
import { Live } from './pages/Live'
import { LinkLanding } from './pages/LinkLanding'
import { Login } from './pages/Login'
import { NotFound } from './pages/NotFound'
import { Onboarding } from './pages/Onboarding'
import { OrderStatus } from './pages/OrderStatus'
import { Orders } from './pages/Orders'
import { PublicShop } from './pages/PublicShop'
import { Settings } from './pages/Settings'
import { Styleguide } from './pages/Styleguide'

export const router = createBrowserRouter([
  { path: '/', element: <Onboarding /> },
  { path: '/login', element: <Login /> },
  { path: '/signin', element: <LinkLanding kind="signin" /> },
  { path: '/verify', element: <LinkLanding kind="verify" /> },
  {
    path: '/shop/:id',
    element: <ShopLayout />,
    children: [
      { index: true, element: <CatalogReview /> },
      { path: 'live', element: <Live /> },
      { path: 'orders', element: <Orders /> },
      { path: 'audit', element: <Audit /> },
      { path: 'settings', element: <Settings /> },
    ],
  },
  { path: '/s/:slug', element: <PublicShop /> },
  { path: '/o/:id', element: <OrderStatus /> },
  { path: '/styleguide', element: <Styleguide /> },
  { path: '*', element: <NotFound /> },
])
