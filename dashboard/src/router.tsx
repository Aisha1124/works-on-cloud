import { createBrowserRouter } from 'react-router'
import { Home } from './pages/Home'
import { NotFound } from './pages/NotFound'
import { Styleguide } from './pages/Styleguide'

export const router = createBrowserRouter([
  { path: '/', element: <Home /> },
  { path: '/styleguide', element: <Styleguide /> },
  { path: '*', element: <NotFound /> },
])
