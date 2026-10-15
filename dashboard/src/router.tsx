import { createBrowserRouter } from 'react-router'
import { ShopLayout } from './components/ShopLayout'
import { Audit } from './pages/Audit'
import { CatalogReview } from './pages/CatalogReview'
import { Live } from './pages/Live'
import { NotFound } from './pages/NotFound'
import { Onboarding } from './pages/Onboarding'
import { Orders } from './pages/Orders'
import { PublicShop } from './pages/PublicShop'
import { Styleguide } from './pages/Styleguide'

export const router = createBrowserRouter([
  { path: '/', element: <Onboarding /> },
  {
    path: '/shop/:id',
    element: <ShopLayout />,
    children: [
      { index: true, element: <CatalogReview /> },
      { path: 'live', element: <Live /> },
      { path: 'orders', element: <Orders /> },
      { path: 'audit', element: <Audit /> },
    ],
  },
  { path: '/s/:slug', element: <PublicShop /> },
  { path: '/styleguide', element: <Styleguide /> },
  { path: '*', element: <NotFound /> },
])
