// Live API client: typed from the generated OpenAPI schema (npm run gen:api). Used when VITE_API=live.
import createClient from 'openapi-fetch'
import type { paths } from './schema'
import type {
  AuditEvent, BloodRequest, BloodUnit, ChainCheck, Component, CompatRule, Donor, ForecastSeries, Invitation, LowStock, MatchThread,
  RequestMatch, Rh, Abo, Session, Setting, SettingChange,
  Site, StaffUser, StockCell, Transfer, TransferPlan, UnitMovement, UnitStatus,
} from './types'
import {
  ApiError, getSession, setSession, type AppealBody, type DonorFilter, type NewRequest, type NewUnit, type ProfilePatch, type UnitFilter,
} from './mockClient'

const api = createClient<paths>({ baseUrl: '', credentials: 'same-origin' })

// Access token lives in memory only; the refresh token is an HttpOnly cookie (SEC-04, SEC-12).
let token: string | null = null
let pendingChallenge: string | null = null
let refreshing: Promise<boolean> | null = null

type TokenBody = { access_token: string; user: { id: string; role: Session['role']; email?: string | null; site_ids: string[] } }

function adopt(b: TokenBody) {
  token = b.access_token
  setSession({ user_id: b.user.id, role: b.user.role, email: b.user.email ?? null, site_ids: b.user.site_ids })
}

function refresh(): Promise<boolean> {
  refreshing ??= fetch('/api/v1/auth/refresh', { method: 'POST', credentials: 'same-origin' })
    .then(async (r) => (r.ok ? (adopt(await r.json()), true) : false))
    .catch(() => false)
    .finally(() => { refreshing = null })
  return refreshing
}

api.use({
  async onRequest({ request }) {
    if (!request.url.includes('/auth/') && !token && getSession()) await refresh()
    if (token) request.headers.set('Authorization', `Bearer ${token}`)
    return request
  },
})

type Res<T> = { data?: T; error?: unknown; response: Response }

/** Unwrap a response; on 401 refresh once and retry, then sign the user out. */
async function call<T>(fn: () => Promise<Res<T>>): Promise<T> {
  // Server down or proxy can't reach it: say so instead of a generic failure.
  const attempt = async () => {
    try {
      const res = await fn()
      if ([502, 503, 504].includes(res.response.status)) throw new ApiError(503, 'unavailable', 'The LifeGrid server is not reachable.')
      return res
    } catch (e) {
      if (e instanceof ApiError) throw e
      throw new ApiError(503, 'unavailable', 'The LifeGrid server is not reachable.')
    }
  }
  let r = await attempt()
  if (r.response.status === 401 && getSession() && (await refresh())) r = await attempt()
  if (r.error !== undefined || !r.response.ok) {
    const e = (r.error ?? {}) as { code?: string; detail?: string }
    if (r.response.status === 401) { token = null; setSession(null) }
    throw new ApiError(r.response.status, e.code ?? 'error', e.detail ?? r.response.statusText)
  }
  return r.data as T
}

const groupParts = (g?: string) => (g ? { abo: g.replace(/pos|neg/, '') as Abo, rh: (g.endsWith('neg') ? 'neg' : 'pos') as Rh } : {})

// ---------- auth ----------
export async function login(email: string, password: string) {
  const b = await call(() => api.POST('/api/v1/auth/login', { body: { email, password } }))
  if (b.totp_required) { pendingChallenge = b.challenge ?? null; return { totp_required: true } }
  adopt(b.session as TokenBody)
  return { totp_required: false }
}
export async function verifyTotp(code: string) {
  adopt(await call(() => api.POST('/api/v1/auth/totp', { body: { challenge: pendingChallenge ?? '', code } })) as TokenBody)
  pendingChallenge = null
}
export async function requestOtp(phone: string) {
  const r = await call(() => api.POST('/api/v1/auth/otp/request', { body: { phone } }))
  return { dev_code: r.dev_code ?? null } // development only: the API returns the code because SMS is mocked
}
export async function verifyOtp(phone: string, code: string, role: 'donor' | 'requester') {
  adopt(await call(() => api.POST('/api/v1/auth/otp/verify', { body: { phone, code, role } })) as TokenBody)
}
export function logout() {
  void fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'same-origin' })
  token = null
  setSession(null)
}

// ---------- sites & stock ----------
export const listSites = () => call(() => api.GET('/api/v1/sites')) as Promise<Site[]>
export const stockSummary = (component: Component) =>
  call(() => api.GET('/api/v1/stock/summary', { params: { query: { component } } })) as Promise<StockCell[]>

export async function listUnits(f: UnitFilter): Promise<BloodUnit[]> {
  const out: BloodUnit[] = []
  let cursor: string | undefined
  for (let page = 0; page < 10; page++) { // ponytail: up to 5,000 units client-side; switch the table to server paging past that
    const q = { site_id: f.site_id, status: f.status || undefined, component: f.component || undefined, band: f.band || undefined, ...groupParts(f.group), limit: 500, cursor }
    const p = await call(() => api.GET('/api/v1/units', { params: { query: q } }))
    out.push(...(p.items as BloodUnit[]))
    if (!p.next_cursor) break
    cursor = p.next_cursor
  }
  return out
}

export async function getUnit(id: string): Promise<{ unit: BloodUnit; movements: UnitMovement[] }> {
  const d = await call(() => api.GET('/api/v1/units/{unit_id}', { params: { path: { unit_id: id } } }))
  return { unit: d.unit as BloodUnit, movements: d.movements.map((m) => ({ ...m, unit_id: id })) as UnitMovement[] }
}

const ACTION: Partial<Record<UnitStatus, 'issue' | 'quarantine' | 'clear' | 'discard'>> = {
  issued: 'issue', quarantined: 'quarantine', available: 'clear', discarded: 'discard',
}
export async function transitionUnits(ids: string[], to: UnitStatus, reason: string) {
  const action = ACTION[to]
  if (!action) throw new ApiError(409, 'invalid_transition', 'This change is made by the system.')
  return (await call(() => api.POST('/api/v1/units/transition', { body: { unit_ids: ids, action, reason } }))).changed
}

export async function receiveUnit(n: NewUnit) {
  await call(() => api.POST('/api/v1/units', {
    body: { ...n, collected_at: new Date(n.collected_at).toISOString(), expires_at: new Date(n.expires_at).toISOString() },
  }))
}

export async function importUnits(siteId: string, csv: string) {
  const form = new FormData()
  form.set('site_id', siteId)
  form.set('file', new Blob([csv], { type: 'text/csv' }), 'units.csv')
  const r = await fetch('/api/v1/units/import', { method: 'POST', body: form, headers: token ? { Authorization: `Bearer ${token}` } : {} })
  const b = await r.json()
  if (!r.ok) throw new ApiError(r.status, b.code ?? 'error', b.missing?.join(', ') ?? b.detail)
  return b as { imported: number; errors: { row: number; reason: string }[] }
}

// ---------- forecasts ----------
export async function forecast(siteId: string, component: Component, abo: Abo, rh: Rh): Promise<ForecastSeries> {
  const s = await call(() => api.GET('/api/v1/forecasts', { params: { query: { site_id: siteId, component, abo, rh } } }))
  return {
    model: s.model ?? 'none', model_version: s.model_version ?? '-', mae: s.mae ?? 0, coverage: s.coverage ?? null, baseline_mae: s.baseline_mae ?? 0,
    points: s.points.map((p) => ({ day: p.day, actual: p.actual ?? undefined, point: p.point ?? undefined, low: p.low ?? undefined, high: p.high ?? undefined })),
  }
}

// ---------- redistribution ----------
export const listPlans = () => call(() => api.GET('/api/v1/plans')) as unknown as Promise<(Omit<TransferPlan, 'recommendations'> & { count?: number })[]>
export const getPlan = (id: string) =>
  call(() => api.GET('/api/v1/plans/{plan_id}', { params: { path: { plan_id: id } } })) as unknown as Promise<TransferPlan>
export async function runPlan() {
  const r = await call(() => api.POST('/api/v1/plans'))
  return { accepted: r.queued, plan_id: r.plan_id ?? null }
}
export async function decide(recId: string, approve: boolean, units?: number) {
  await call(() => api.POST('/api/v1/recommendations/{rec_id}/decision', { params: { path: { rec_id: recId } }, body: { approve, units } }))
}
export const listTransfers = () => call(() => api.GET('/api/v1/transfers')) as unknown as Promise<Transfer[]>
export const previewPick = (id: string) =>
  call(() => api.GET('/api/v1/transfers/{transfer_id}/pick', { params: { path: { transfer_id: id } } })) as Promise<BloodUnit[]>
export async function dispatchTransfer(id: string) {
  await call(() => api.POST('/api/v1/transfers/{transfer_id}/dispatch', { params: { path: { transfer_id: id } } }))
}
export async function receiveTransfer(id: string) {
  await call(() => api.POST('/api/v1/transfers/{transfer_id}/receive', { params: { path: { transfer_id: id } } }))
}

// ---------- admin & audit ----------
export const listUsers = () => call(() => api.GET('/api/v1/admin/users')) as Promise<StaffUser[]>
export async function updateUser(id: string, patch: { active?: boolean; role?: StaffUser['role']; site_ids?: string[] }) {
  await call(() => api.PATCH('/api/v1/admin/users/{user_id}', { params: { path: { user_id: id } }, body: patch }))
}
export const listSettings = () =>
  call(() => api.GET('/api/v1/admin/settings')) as unknown as Promise<{ settings: Setting[]; history: SettingChange[] }>
export async function updateSetting(key: string, value: unknown) {
  await call(() => api.PUT('/api/v1/admin/settings/{key}', { params: { path: { key } }, body: { value } }))
}
export const listCompatRules = (component: Component) =>
  call(() => api.GET('/api/v1/admin/compat-rules', { params: { query: { component } } })) as unknown as Promise<CompatRule[]>
export async function listAudit(q: string): Promise<AuditEvent[]> {
  const p = await call(() => api.GET('/api/v1/audit', { params: { query: { q, limit: 200 } } }))
  return p.items
}
export const verifyAudit = () => call(() => api.GET('/api/v1/audit/verify')) as Promise<ChainCheck>

// ---------- requests, donors, matching (phase 6) ----------
const hhmm = (t?: string | null) => (t ? t.slice(0, 5) : null)
const donorOut = (d: Record<string, unknown>) => ({ ...d, quiet_start: hhmm(d.quiet_start as string), quiet_end: hhmm(d.quiet_end as string) }) as unknown as Donor
const path = (id: string) => ({ params: { path: { request_id: id } } })
const mpath = (id: string) => ({ params: { path: { match_id: id } } })

export const listRequests = () => call(() => api.GET('/api/v1/requests')) as unknown as Promise<BloodRequest[]>
export const getRequest = (id: string) => call(() => api.GET('/api/v1/requests/{request_id}', path(id))) as unknown as Promise<BloodRequest>
export const createRequest = (n: NewRequest) =>
  call(() => api.POST('/api/v1/requests', { body: { ...n, needed_by: new Date(n.needed_by).toISOString() } })) as unknown as Promise<BloodRequest>
export const confirmRequest = (id: string) => call(() => api.POST('/api/v1/requests/{request_id}/confirm', path(id))) as unknown as Promise<BloodRequest>
export const cancelRequest = async (id: string) => { await call(() => api.POST('/api/v1/requests/{request_id}/cancel', path(id))) }
export const listRequestMatches = (id: string) =>
  call(() => api.GET('/api/v1/requests/{request_id}/matches', path(id))) as unknown as Promise<RequestMatch[]>
export async function recordMatchOutcome(matchId: string, outcome: 'donated' | 'no_show' | 'deferred_on_site') {
  await call(() => api.POST('/api/v1/matches/{match_id}/outcome', { ...mpath(matchId), body: { outcome } }))
}
export const lowStock = () => call(() => api.GET('/api/v1/stock/low')) as unknown as Promise<LowStock[]>
export const createAppeal = (b: AppealBody) => call(() => api.POST('/api/v1/appeals', { body: b })) as unknown as Promise<BloodRequest>

export async function listDonors(f: DonorFilter) {
  const query = { group: f.group || undefined, eligible: f.eligible || undefined, q: f.q || undefined }
  const rows = await call(() => api.GET('/api/v1/donors', { params: { query } }))
  return (rows as unknown as Record<string, unknown>[]).map(donorOut)
}
export async function addDeferral(id: string, category: string, eligible_again_on: string) {
  await call(() => api.POST('/api/v1/donors/{donor_id}/deferrals', { params: { path: { donor_id: id } }, body: { category, eligible_again_on } }))
}
export async function verifyGroup(id: string) {
  await call(() => api.POST('/api/v1/donors/{donor_id}/verify-group', { params: { path: { donor_id: id } } }))
}
export const getDonorProfile = async () => donorOut(await call(() => api.GET('/api/v1/donor/profile')) as unknown as Record<string, unknown>)
export async function updateDonorProfile(p: ProfilePatch) {
  const keys = ['abo', 'rh', 'area_lat', 'area_lng', 'birth_year', 'weight_ok', 'availability', 'quiet_start', 'quiet_end', 'emergency_override',
    'max_invites_30d', 'consent', 'consent_version'] as const
  const body = Object.fromEntries(keys.filter((k) => k in p).map((k) => [k, p[k as keyof ProfilePatch]]))
  return donorOut(await call(() => api.PUT('/api/v1/donor/profile', { body })) as unknown as Record<string, unknown>)
}
export const exportDonorData = () => call(() => api.GET('/api/v1/donor/export')) as Promise<Record<string, unknown>>
export async function deleteDonorData() {
  await call(() => api.DELETE('/api/v1/donor/profile'))
  token = null
  setSession(null)
}
export const listInvitations = () => call(() => api.GET('/api/v1/donor/invitations')) as unknown as Promise<Invitation[]>
export async function respondInvitation(id: string, accept: boolean) {
  await call(() => api.POST('/api/v1/matches/{match_id}/respond', { ...mpath(id), body: { accept } }))
}
export const getThread = (id: string) => call(() => api.GET('/api/v1/matches/{match_id}/messages', mpath(id))) as unknown as Promise<MatchThread>
export async function sendMessage(id: string, body: string) {
  await call(() => api.POST('/api/v1/matches/{match_id}/messages', { ...mpath(id), body: { body } }))
}
export async function sharePhone(id: string) {
  await call(() => api.POST('/api/v1/matches/{match_id}/share-phone', mpath(id)))
}

// Phase 7 endpoints are not served yet; lists stay empty and actions explain why.
export const notYet = () => Promise.reject(new ApiError(501, 'not_available', 'This part of LifeGrid arrives in a later phase.'))
