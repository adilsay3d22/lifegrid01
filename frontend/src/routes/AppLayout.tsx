import { NavLink, Outlet, ScrollRestoration, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ClipboardText, EnvelopeSimple, House, Plus, ShieldCheck, SignOut, type Icon } from '@phosphor-icons/react'
import { useSession } from '../session'
import { cx } from '../components/ui'
import { Logo } from '../components/Logo'

/** Phone-first shell for donors and requesters (NFR-12: works at 360 px). */
export function AppLayout() {
  const { t } = useTranslation()
  const { session, logout } = useSession()
  const nav = useNavigate()
  const tabs: [string, string, Icon][] = session?.role === 'requester'
    ? [['/app/requests', 'myRequests', ClipboardText], ['/app/requests/new', 'newRequest', Plus]]
    : [['/app/donor', 'home', House], ['/app/invitations', 'invitations', EnvelopeSimple], ['/app/privacy', 'privacy', ShieldCheck]]

  return (
    <div className="mx-auto flex min-h-[100dvh] max-w-md flex-col bg-canvas">
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-zinc-200 bg-canvas/90 px-4 backdrop-blur">
        <Logo compact />
        <button type="button" onClick={() => { logout(); nav('/app') }} className="flex h-9 items-center gap-1.5 rounded-md px-2 -mr-2 text-sm text-zinc-600 hover:bg-zinc-100 focus-visible:outline-2 focus-visible:outline-brand">
          <SignOut size={16} aria-hidden />{t('auth.signOut')}
        </button>
      </header>
      <main id="main" className="flex-1 px-4 pt-5 pb-28"><Outlet /></main>
      <ScrollRestoration />
      <nav aria-label={t('nav.label')} className="fixed inset-x-0 bottom-0 z-30 mx-auto max-w-md border-t border-zinc-200 bg-white/95 backdrop-blur pb-[env(safe-area-inset-bottom)]">
        <ul className="grid" style={{ gridTemplateColumns: `repeat(${tabs.length}, 1fr)` }}>
          {tabs.map(([to, key, I]) => (
            <li key={key}>
              <NavLink to={to} end className={({ isActive }) => cx('flex h-16 flex-col items-center justify-center gap-1 text-xs font-medium focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand', isActive ? 'text-brand' : 'text-zinc-500')}>
                {({ isActive }) => <><I size={22} weight={isActive ? 'fill' : 'regular'} aria-hidden />{t(`appNav.${key}`)}</>}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  )
}
