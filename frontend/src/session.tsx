import { createContext, useContext, useState, type ReactNode } from 'react'
import { getSession, logout as apiLogout } from './api/client'
import type { Role, Session } from './api/types'

const Ctx = createContext<{ session: Session | null; refresh: () => void; logout: () => void }>(null!)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState(getSession)
  const refresh = () => setSession(getSession())
  const logout = () => { apiLogout(); setSession(null) }
  return <Ctx.Provider value={{ session, refresh, logout }}>{children}</Ctx.Provider>
}
export const useSession = () => useContext(Ctx)

export const STAFF_ROLES: Role[] = ['bank_manager', 'hospital_lead', 'donor_coordinator', 'admin', 'auditor']

/** Landing route per role, so nobody lands on a screen they cannot use. */
export function homeFor(s: Session) {
  switch (s.role) {
    case 'bank_manager': case 'admin': return '/staff'
    case 'hospital_lead': return `/staff/sites/${s.site_ids[0]}/stock`
    case 'donor_coordinator': return '/staff/donors'
    case 'auditor': return '/staff/audit'
    case 'donor': return '/app/donor'
    case 'requester': return '/app/requests'
  }
}
