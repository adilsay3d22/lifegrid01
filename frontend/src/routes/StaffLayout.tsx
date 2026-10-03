import { useEffect, useState } from 'react'
import { Navigate, NavLink, Outlet, ScrollRestoration, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import {
  Bell, ChartLineUp, ClipboardText, Drop, FileCsv, Gear, List, MapTrifold, ShieldCheck, SignOut, Truck, UsersThree, ArrowsLeftRight, X,
  type Icon,
} from '@phosphor-icons/react'
import type { Role } from '../api/types'
import { listAlerts } from '../api/client'
import { STAFF_ROLES, useSession } from '../session'
import { cx } from '../components/ui'
import { Logo } from '../components/Logo'

type Item = { to: string; key: string; icon: Icon; roles: Role[]; end?: boolean }

export function StaffLayout() {
  const { t } = useTranslation()
  const { session, logout } = useSession()
  const nav = useNavigate()
  const loc = useLocation()
  const [open, setOpen] = useState(false)
  useEffect(() => { setOpen(false) }, [loc.pathname])
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])
  const alerts = useQuery({ queryKey: ['alerts'], queryFn: listAlerts, enabled: !!session })

  if (!session || !STAFF_ROLES.includes(session.role)) return <Navigate to="/staff/login" replace />

  const items: Item[] = [
    { to: '/staff', key: 'overview', icon: MapTrifold, roles: ['bank_manager', 'admin'], end: true },
    { to: `/staff/sites/${session.site_ids[0]}/stock`, key: 'stock', icon: Drop, roles: ['bank_manager', 'hospital_lead'] },
    { to: '/staff/forecasts', key: 'forecasts', icon: ChartLineUp, roles: STAFF_ROLES },
    { to: '/staff/plans', key: 'plan', icon: ArrowsLeftRight, roles: ['bank_manager'] },
    { to: '/staff/transfers', key: 'transfers', icon: Truck, roles: ['bank_manager', 'hospital_lead'] },
    { to: '/staff/requests', key: 'requests', icon: ClipboardText, roles: ['hospital_lead', 'bank_manager', 'donor_coordinator'] },
    { to: '/staff/donors', key: 'donors', icon: UsersThree, roles: ['donor_coordinator'] },
    { to: '/staff/alerts', key: 'alerts', icon: Bell, roles: STAFF_ROLES },
    { to: '/staff/reports', key: 'reports', icon: FileCsv, roles: ['bank_manager', 'admin', 'auditor'] },
    { to: '/staff/admin', key: 'admin', icon: Gear, roles: ['admin'] },
    { to: '/staff/audit', key: 'audit', icon: ShieldCheck, roles: ['admin', 'auditor'] },
  ]
  const openAlerts = alerts.data?.filter((a) => a.status === 'open').length ?? 0

  const sidebar = (
    <nav aria-label={t('nav.label')} className="flex h-full flex-col">
      <div className="flex h-16 items-center px-5 border-b border-zinc-200"><Logo /></div>
      <ul className="flex-1 overflow-y-auto px-3 py-4 grid content-start gap-0.5">
        {items.filter((i) => i.roles.includes(session.role)).map(({ to, key, icon: I, end }) => (
          <li key={key}>
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) => cx(
                'group relative flex h-9 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-brand',
                isActive ? 'bg-zinc-100 text-zinc-950' : 'text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900',
              )}
            >
              {({ isActive }) => (
                <>
                  {isActive && <span className="absolute -left-3 top-2 bottom-2 w-0.5 rounded-full bg-brand" aria-hidden />}
                  <I size={18} weight={isActive ? 'fill' : 'regular'} aria-hidden className={isActive ? 'text-brand' : ''} />
                  <span className="flex-1">{t(`nav.${key}`)}</span>
                  {key === 'alerts' && openAlerts > 0 && (
                    <span className="flex items-center gap-1.5 font-mono text-xs tabular-nums text-red-700">
                      <span className="live-dot size-1.5 rounded-full bg-red-600" aria-hidden />
                      {openAlerts}<span className="sr-only">{t('nav.openAlerts')}</span>
                    </span>
                  )}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="border-t border-zinc-200 p-4 grid gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-zinc-900">{session.email}</p>
          <p className="text-xs text-zinc-500">{t(`roles.${session.role}`)}</p>
        </div>
        <button
          type="button"
          onClick={() => { logout(); nav('/staff/login') }}
          className="flex h-8 items-center gap-2 rounded-md px-2 -mx-2 text-sm text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-brand"
        >
          <SignOut size={16} aria-hidden />{t('auth.signOut')}
        </button>
        <p className="text-[11px] leading-snug text-zinc-500">{t('common.syntheticNotice')}</p>
      </div>
    </nav>
  )

  return (
    <div className="min-h-[100dvh] lg:grid lg:grid-cols-[248px_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:ring-2 focus:ring-brand">{t('common.skip')}</a>
      <aside className="hidden lg:block sticky top-0 h-[100dvh] border-r border-zinc-200 bg-white">{sidebar}</aside>

      <header className="lg:hidden sticky top-0 z-30 flex h-14 items-center justify-between border-b border-zinc-200 bg-white/90 px-4 backdrop-blur">
        <Logo />
        <button type="button" onClick={() => setOpen(true)} aria-label={t('nav.open')} aria-expanded={open} className="rounded-md p-2 -mr-2 text-zinc-700 hover:bg-zinc-100 focus-visible:outline-2 focus-visible:outline-brand">
          <List size={22} aria-hidden />
        </button>
      </header>
      {open && (
        <div className="lg:hidden fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label={t('nav.label')}>
          <div className="absolute inset-0 bg-zinc-900/40" onClick={() => setOpen(false)} aria-hidden />
          <div className="reveal absolute inset-y-0 left-0 w-72 max-w-[85vw] bg-white shadow-xl">
            <button type="button" onClick={() => setOpen(false)} aria-label={t('common.close')} className="absolute right-3 top-4 rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 focus-visible:outline-2 focus-visible:outline-brand">
              <X size={20} aria-hidden />
            </button>
            {sidebar}
          </div>
        </div>
      )}

      <main id="main" className="min-w-0 px-4 py-6 md:px-8 md:py-8">
        <div className="mx-auto max-w-[1400px]"><Outlet /></div>
        <ScrollRestoration />
      </main>
    </div>
  )
}
