import { createBrowserRouter, Navigate, Outlet, useLocation } from 'react-router-dom'
import type { Role } from '../api/types'
import { STAFF_ROLES, homeFor, useSession } from '../session'
import { StaffLayout } from './StaffLayout'
import { AppLayout } from './AppLayout'

/** UI-side guard only; the API enforces role and site scope on every endpoint (SEC-05). */
function Require({ roles }: { roles: Role[] }) {
  const { session } = useSession()
  const loc = useLocation()
  if (!session) return <Navigate to={loc.pathname.startsWith('/staff') ? '/staff/login' : '/app'} replace />
  if (!roles.includes(session.role)) return <Navigate to={homeFor(session)} replace />
  return <Outlet />
}

const STAFF_SCREENS: [string, Role[], () => Promise<{ Component: React.ComponentType }>][] = [
  ['', ['bank_manager', 'admin'], () => import('../features/stock/Overview')],
  ['sites/:id/stock', ['bank_manager', 'hospital_lead'], () => import('../features/stock/SiteStock')],
  ['units/:id', STAFF_ROLES, () => import('../features/stock/UnitDetail')],
  ['forecasts', STAFF_ROLES, () => import('../features/forecasts/Forecasts')],
  ['plans', ['bank_manager'], () => import('../features/transfers/PlanRedirect')],
  ['plans/:id', ['bank_manager'], () => import('../features/transfers/Plan')],
  ['transfers', ['bank_manager', 'hospital_lead'], () => import('../features/transfers/Transfers')],
  ['requests', ['hospital_lead', 'bank_manager', 'donor_coordinator'], () => import('../features/requests/StaffRequests')],
  ['donors', ['donor_coordinator'], () => import('../features/donors/Donors')],
  ['alerts', STAFF_ROLES, () => import('../features/alerts/Alerts')],
  ['reports', ['bank_manager', 'admin', 'auditor'], () => import('../features/admin/Reports')],
  ['admin', ['admin'], () => import('../features/admin/Admin')],
  ['audit', ['admin', 'auditor'], () => import('../features/admin/Audit')],
]

const APP_SCREENS: [string, Role[], () => Promise<{ Component: React.ComponentType }>][] = [
  ['register', ['donor'], () => import('../features/app/Register')],
  ['donor', ['donor'], () => import('../features/app/DonorHome')],
  ['invitations', ['donor'], () => import('../features/app/Invitations')],
  ['matches/:id', ['donor', 'requester'], () => import('../features/app/MatchChat')],
  ['requests', ['requester'], () => import('../features/app/MyRequests')],
  ['requests/new', ['requester'], () => import('../features/app/NewRequest')],
  ['requests/:id', ['requester'], () => import('../features/app/RequestStatus')],
  ['privacy', ['donor'], () => import('../features/app/Privacy')],
]

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/app" replace /> },
  { path: '/staff/login', lazy: () => import('../features/auth/StaffLogin') },
  {
    path: '/staff',
    element: <StaffLayout />,
    children: STAFF_SCREENS.map(([path, roles, load]) => ({
      element: <Require roles={roles} />,
      children: [path ? { path, lazy: load } : { index: true, lazy: load }],
    })),
  },
  { path: '/app', lazy: () => import('../features/app/Welcome') },
  {
    path: '/app',
    element: <AppLayout />,
    children: APP_SCREENS.map(([path, roles, load]) => ({ element: <Require roles={roles} />, children: [{ path, lazy: load }] })),
  },
  { path: '*', lazy: () => import('../features/NotFound') },
])
