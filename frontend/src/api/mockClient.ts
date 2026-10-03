// One function per spec section 12 endpoint. Swap the bodies for the generated OpenAPI client; signatures stay.
import type {
  Abo, Alert, BloodRequest, BloodUnit, ChainCheck, Component, Donor, ForecastSeries, LowStock, MatchThread, RequestMatch, Rh, Role, Session,
  Setting, StockCell, TransferPlan, UnitMovement, UnitStatus, Urgency,
} from './types'
import { DAY, NOW, appendAudit, auditPayload, db, dayIso, fnv, iso, mulberry32 } from './mock'

/** RFC 9457 problem details, as the API returns them. */
export class ApiError extends Error {
  constructor(public status: number, public code: string, detail: string) { super(detail) }
}

const wait = (ms = 180 + Math.random() * 260) => new Promise((r) => setTimeout(r, ms))
async function read<T>(value: () => T): Promise<T> {
  await wait()
  if (new URLSearchParams(location.search).has('fail')) throw new ApiError(503, 'unavailable', 'The service did not respond.')
  return structuredClone(value())
}
async function write<T>(fn: () => T): Promise<T> {
  await wait(320)
  return structuredClone(fn())
}

let session: Session | null = JSON.parse(sessionStorage.getItem('lg.session') ?? 'null')
export const getSession = () => session
export function setSession(s: Session | null) {
  session = s
  if (s) sessionStorage.setItem('lg.session', JSON.stringify(s))
  else sessionStorage.removeItem('lg.session')
}
const actor = () => session?.email ?? session?.user_id ?? 'system'
const daysLeft = (u: BloodUnit) => (Date.parse(u.expires_at) - NOW) / DAY

// ---------- auth ----------
let pendingTotp: Session | null = null
export async function login(email: string, password: string): Promise<{ totp_required: boolean }> {
  await wait(400)
  const user = db.staff.find((u) => u.email === email.trim().toLowerCase())
  if (!user || password.length < 12) { appendAudit(email, 'auth.sign_in_failed', 'user', email); throw new ApiError(401, 'invalid_credentials', 'Email or password is incorrect.') }
  if (!user.active) throw new ApiError(403, 'user_disabled', 'This account is disabled.')
  const s: Session = { user_id: user.id, role: user.role, email: user.email, site_ids: user.site_ids }
  if (user.totp) { pendingTotp = s; return { totp_required: true } }
  setSession(s); appendAudit(user.email, 'auth.sign_in', 'user', user.id)
  return { totp_required: false }
}
export async function verifyTotp(code: string) {
  await wait(300)
  if (!pendingTotp || !/^\d{6}$/.test(code)) throw new ApiError(401, 'invalid_code', 'That code is not valid.')
  setSession(pendingTotp); appendAudit(pendingTotp.email!, 'auth.sign_in', 'user', pendingTotp.user_id); pendingTotp = null
}
const otpAttempts = new Map<string, number>()
export async function requestOtp(phone: string): Promise<{ dev_code: string | null }> {
  await wait(350)
  if (!/^\+?\d[\d\s-]{8,15}$/.test(phone)) throw new ApiError(422, 'invalid_phone', 'Enter a valid phone number.')
  return { dev_code: null } // mock accepts any 6 digits
}
export async function verifyOtp(phone: string, code: string, role: 'donor' | 'requester') {
  await wait(350)
  const n = (otpAttempts.get(phone) ?? 0) + 1
  otpAttempts.set(phone, n)
  if (n > 5) throw new ApiError(429, 'locked', 'Too many attempts. Try again in 15 minutes.')
  if (!/^\d{6}$/.test(code)) throw new ApiError(401, 'invalid_code', 'That code is not valid.')
  otpAttempts.delete(phone)
  const id = role === 'donor' ? db.appUsers.donor.id : db.appUsers.requester.id
  setSession({ user_id: id, role, email: null, site_ids: [] })
}
export function logout() { setSession(null) }

// ---------- sites & stock ----------
export const listSites = () => read(() => db.sites)
export function inScope(siteId: string) {
  const s = session
  if (!s) return false
  return s.role === 'bank_manager' || s.role === 'admin' || s.role === 'auditor' || s.site_ids.includes(siteId)
}

export const stockSummary = (component: Component) => read<StockCell[]>(() => {
  const cells = new Map<string, StockCell>()
  for (const u of db.units) {
    if (u.status !== 'available' || u.component !== component) continue
    const k = `${u.site_id}|${u.abo}|${u.rh}`
    const c = cells.get(k) ?? { site_id: u.site_id, component, abo: u.abo, rh: u.rh, band_0_2: 0, band_3_7: 0, band_8: 0 }
    const d = daysLeft(u)
    if (d <= 2) c.band_0_2++; else if (d <= 7) c.band_3_7++; else c.band_8++
    cells.set(k, c)
  }
  return [...cells.values()]
})

export interface UnitFilter { site_id: string; status?: UnitStatus | ''; component?: Component | ''; group?: string; band?: '' | '0_2' | '3_7' | '8' }
export const listUnits = (f: UnitFilter) => read(() => {
  if (!inScope(f.site_id)) throw new ApiError(403, 'out_of_scope', 'You do not have access to this site.')
  return db.units
    .filter((u) => u.site_id === f.site_id && (!f.status || u.status === f.status) && (!f.component || u.component === f.component)
      && (!f.group || `${u.abo}${u.rh}` === f.group)
      && (!f.band || (f.band === '0_2' ? daysLeft(u) <= 2 : f.band === '3_7' ? daysLeft(u) > 2 && daysLeft(u) <= 7 : daysLeft(u) > 7)))
    .sort((a, b) => a.expires_at.localeCompare(b.expires_at)) // FEFO (FR-INV-09)
})

const movements = new Map<string, UnitMovement[]>()
function historyOf(u: BloodUnit): UnitMovement[] {
  if (!movements.has(u.id)) {
    const r = mulberry32(parseInt(u.id.slice(0, 8), 16))
    const t0 = Date.parse(u.collected_at) + (1 + r() * 2) * DAY
    const list: UnitMovement[] = [{ id: 1, unit_id: u.id, from_status: null, to_status: 'available', from_site_id: null, to_site_id: u.site_id, actor: 'import', reason: 'Received from supplier', created_at: iso(t0) }]
    if (u.status !== 'available') list.push({ id: 2, unit_id: u.id, from_status: u.status === 'issued' ? 'reserved' : 'available', to_status: u.status, from_site_id: u.site_id, to_site_id: u.site_id, actor: u.status === 'expired' ? 'system' : db.staff[1].email, reason: u.status === 'expired' ? 'Expiry time passed' : 'Recorded at site', created_at: iso(Math.min(NOW, t0 + r() * 5 * DAY)) })
    movements.set(u.id, list)
  }
  return movements.get(u.id)!
}
export const getUnit = (id: string) => read(() => {
  const u = db.units.find((x) => x.id === id)
  if (!u) throw new ApiError(404, 'not_found', 'Unit not found.')
  return { unit: u, movements: historyOf(u) }
})

// Lifecycle (spec section 6). Server is the authority; mirrored here for the mock.
export const LIFECYCLE: Record<UnitStatus, UnitStatus[]> = {
  available: ['reserved', 'in_transit', 'quarantined', 'expired'],
  reserved: ['available', 'issued', 'quarantined', 'expired'],
  in_transit: ['available', 'quarantined', 'expired'],
  quarantined: ['available', 'discarded'],
  expired: ['discarded'],
  issued: [],
  discarded: [],
}
function transition(u: BloodUnit, to: UnitStatus, reason: string) {
  if (!LIFECYCLE[u.status].includes(to)) throw new ApiError(409, 'invalid_transition', `A ${u.status} unit cannot become ${to}.`)
  historyOf(u).push({ id: historyOf(u).length + 1, unit_id: u.id, from_status: u.status, to_status: to, from_site_id: u.site_id, to_site_id: u.site_id, actor: actor(), reason, created_at: new Date().toISOString() })
  u.status = to
  appendAudit(actor(), 'unit.transition', 'blood_unit', u.unit_code, Date.now())
}
export const transitionUnits = (ids: string[], to: UnitStatus, reason: string) => write(() => {
  const list = ids.map((id) => db.units.find((u) => u.id === id)!)
  list.forEach((u) => { if (!LIFECYCLE[u.status].includes(to)) throw new ApiError(409, 'invalid_transition', `${u.unit_code}: a ${u.status} unit cannot become ${to}.`) })
  list.forEach((u) => transition(u, to, reason))
  return list.length
})

export interface NewUnit { unit_code: string; abo: Abo; rh: Rh; component: Component; collected_at: string; expires_at: string; site_id: string }
function validateUnit(n: NewUnit): string | null {
  if (!n.unit_code || !n.collected_at || !n.expires_at) return 'missing_field'
  if (Date.parse(n.expires_at) <= Date.parse(n.collected_at)) return 'expiry_before_collection'
  if (db.units.some((u) => u.unit_code === n.unit_code)) return 'duplicate_code'
  return null
}
function addUnit(n: NewUnit) {
  const u: BloodUnit = { ...n, id: crypto.randomUUID(), status: 'available', reserved_for: null, collected_at: iso(Date.parse(n.collected_at)), expires_at: iso(Date.parse(n.expires_at)) }
  db.units.push(u)
  movements.set(u.id, [{ id: 1, unit_id: u.id, from_status: null, to_status: 'available', from_site_id: null, to_site_id: u.site_id, actor: actor(), reason: 'Received at site', created_at: new Date().toISOString() }])
  appendAudit(actor(), 'unit.receive', 'blood_unit', u.unit_code, Date.now())
}
export const receiveUnit = (n: NewUnit) => write(() => {
  const err = validateUnit(n)
  if (err) throw new ApiError(err === 'duplicate_code' ? 409 : 422, err, err)
  addUnit(n)
})
export const importUnits = (siteId: string, csv: string) => write(() => {
  const rows = csv.trim().split(/\r?\n/)
  const header = rows.shift()?.split(',').map((h) => h.trim()) ?? []
  const need = ['unit_code', 'abo', 'rh', 'component', 'collected_at', 'expires_at']
  if (!need.every((h) => header.includes(h))) throw new ApiError(422, 'bad_header', need.join(', '))
  const errors: { row: number; reason: string }[] = []
  let imported = 0
  rows.forEach((line, i) => {
    const cells = line.split(',').map((c) => c.trim())
    const rec = Object.fromEntries(header.map((h, j) => [h, cells[j] ?? ''])) as unknown as NewUnit
    rec.site_id = siteId
    let err = validateUnit(rec)
    if (!err && !['O', 'A', 'B', 'AB'].includes(rec.abo)) err = 'invalid_group'
    if (!err && !['pos', 'neg'].includes(rec.rh)) err = 'invalid_rh'
    if (!err && !['red_cells', 'platelets', 'plasma'].includes(rec.component)) err = 'invalid_component'
    if (!err && Number.isNaN(Date.parse(rec.expires_at))) err = 'invalid_date'
    if (err) errors.push({ row: i + 2, reason: err }); else { addUnit(rec); imported++ }
  })
  return { imported, errors }
})

// ---------- compatibility & forecasts ----------
export const compatibility = (abo: Abo, rh: Rh, component: Component) => read(() =>
  db.compatRules.filter((r) => r.component === component && r.recipient_abo === abo && r.recipient_rh === rh).sort((a, b) => a.rank - b.rank))

export const forecast = (siteId: string, component: Component, abo: Abo, rh: Rh) => read<ForecastSeries>(() => {
  const r = mulberry32(fnv(siteId + component + abo + rh).split('').reduce((s, c) => s * 31 + c.charCodeAt(0), 7))
  const base = (db.COMP_BASE[component] / 9) * db.MIX[`${abo}-${rh}`] * db.siteSize.get(siteId)!
  const week = [1.1, 1.1, 1, 1, 1, 0.7, 0.6]
  const sparse = base < 0.5
  const points = []
  const today = NOW - (NOW % DAY)
  for (let d = -28; d < 7; d++) {
    const t = today + d * DAY
    const mean = base * week[(new Date(t).getDay() + 6) % 7]
    const spread = Math.max(0.6, Math.sqrt(mean) * 1.3)
    const round1 = (x: number) => Math.round(Math.max(0, x) * 10) / 10
    points.push(d < 0
      ? { day: dayIso(t), actual: Math.max(0, Math.round(mean + (r() - 0.5) * spread * 2)), point: round1(mean), low: round1(mean - spread), high: round1(mean + spread) }
      : { day: dayIso(t), point: round1(mean), low: round1(mean - spread), high: round1(mean + spread) })
  }
  const past = points.filter((p) => p.actual !== undefined)
  const mae = past.reduce((s, p) => s + Math.abs(p.actual! - p.point), 0) / past.length
  const cov = past.filter((p) => p.actual! >= p.low && p.actual! <= p.high).length / past.length
  return {
    model: sparse ? 'poisson_sparse' : base > 3 ? 'gbm_quantile' : 'exp_smoothing', model_version: '2026.09.3',
    mae: Math.round(mae * 100) / 100, coverage: Math.round(cov * 1000) / 1000, baseline_mae: Math.round(mae * (1.18 + r() * 0.2) * 100) / 100, points,
  }
})

// ---------- redistribution ----------
export const listPlans = () => read(() => db.plans.map(({ recommendations, ...p }) => ({ ...p, count: recommendations.length })))
export const getPlan = (id: string) => read<TransferPlan>(() => {
  const p = db.plans.find((x) => x.id === id)
  if (!p) throw new ApiError(404, 'not_found', 'Plan not found.')
  return p
})
export const runPlan = () => write(() => ({ accepted: true, plan_id: db.plans[0].id }))
export const decide = (recId: string, approve: boolean, units?: number) => write(() => {
  const rec = db.plans.flatMap((p) => p.recommendations).find((r) => r.id === recId)!
  if (rec.status !== 'proposed') throw new ApiError(409, 'already_decided', 'This recommendation was already decided.')
  rec.status = approve ? 'approved' : 'rejected'
  rec.decided_by = actor(); rec.decided_at = new Date().toISOString()
  if (approve) {
    if (units) rec.units = units
    db.transfers.unshift({ id: crypto.randomUUID(), recommendation_id: rec.id, from_site_id: rec.from_site_id, to_site_id: rec.to_site_id, component: rec.component, abo: rec.abo, rh: rec.rh, units: rec.units, status: 'approved', dispatched_at: null, received_at: null, unit_codes: [] })
  }
  appendAudit(actor(), 'transfer.decision', 'recommendation', rec.id.slice(0, 8), Date.now())
})

export const listTransfers = () => read(() => db.transfers)
export const previewPick = (id: string) => read(() => {
  const t = db.transfers.find((x) => x.id === id)!
  const minLife = Number(db.settings.find((s) => s.key === `min_transfer_life_${t.component}_days`)?.value ?? 0)
  return db.units
    .filter((u) => u.site_id === t.from_site_id && u.status === 'available' && u.component === t.component && u.abo === t.abo && u.rh === t.rh && daysLeft(u) >= minLife)
    .sort((a, b) => a.expires_at.localeCompare(b.expires_at)).slice(0, t.units)
})
export const dispatchTransfer = (id: string, unitIds: string[]) => write(() => {
  const t = db.transfers.find((x) => x.id === id)!
  if (t.status !== 'approved') throw new ApiError(409, 'invalid_transition', 'Only approved transfers can be dispatched.')
  const list = unitIds.map((uid) => db.units.find((u) => u.id === uid)!)
  list.forEach((u) => transition(u, 'in_transit', `Transfer to ${t.to_site_id.slice(0, 8)}`))
  t.status = 'dispatched'; t.dispatched_at = new Date().toISOString(); t.unit_codes = list.map((u) => u.unit_code)
})
export const receiveTransfer = (id: string) => write(() => {
  const t = db.transfers.find((x) => x.id === id)!
  if (t.status !== 'dispatched') throw new ApiError(409, 'invalid_transition', 'Only dispatched transfers can be received.')
  for (const code of t.unit_codes) {
    const u = db.units.find((x) => x.unit_code === code)
    if (u && u.status === 'in_transit') { transition(u, 'available', 'Received at destination'); u.site_id = t.to_site_id } // location changes only on receipt (FR-RD-05)
  }
  t.status = 'received'; t.received_at = new Date().toISOString()
})

// ---------- requests ----------
export const listRequests = () => read(() => {
  const s = session!
  return db.requests.filter((r) => s.role === 'requester' ? r.requester_id === s.user_id : s.role === 'hospital_lead' ? s.site_ids.includes(r.site_id) : true)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
})
export const getRequest = (id: string) => read(() => {
  const r = db.requests.find((x) => x.id === id)
  if (!r) throw new ApiError(404, 'not_found', 'Request not found.')
  return r
})
export interface NewRequest { abo: Abo; rh: Rh; component: Component; units_needed: number; site_id: string; urgency: Urgency; needed_by: string }
export const createRequest = (n: NewRequest) => write(() => {
  const s = session!
  const open = db.requests.filter((r) => r.requester_id === s.user_id && !['fulfilled', 'partially_fulfilled', 'unfilled', 'cancelled'].includes(r.status)).length
  if (s.role === 'requester' && open >= 3) throw new ApiError(429, 'rate_limited', 'limit')
  const r: BloodRequest = {
    ...n, id: crypto.randomUUID(), ref: `RQ-${2700 + db.requests.length}`, requester_id: s.user_id, units_secured: 0,
    needed_by: iso(Date.parse(n.needed_by)), status: 'submitted', confirmed_at: null, created_at: new Date().toISOString(),
    progress: { stock_units: 0, donors_notified: 0, donors_accepted: 0 },
  }
  db.requests.unshift(r)
  return r
})
export const confirmRequest = (id: string) => write(() => {
  const r = db.requests.find((x) => x.id === id)!
  if (r.status !== 'submitted') throw new ApiError(409, 'invalid_transition', 'Only submitted requests can be confirmed.')
  r.confirmed_at = new Date().toISOString()
  appendAudit(actor(), 'request.confirm', 'blood_request', r.ref, Date.now())
  // Stock check first (FR-REQ-03); shortfall goes to matching (FR-REQ-04).
  const avail = db.units.filter((u) => u.status === 'available' && u.component === r.component && u.abo === r.abo && u.rh === r.rh).length
  if (avail >= r.units_needed) { r.status = 'covered_by_stock'; r.progress.stock_units = r.units_needed; r.units_secured = r.units_needed }
  else { r.status = 'matching'; r.progress.stock_units = avail; r.units_secured = avail; r.progress.donors_notified = r.component === 'red_cells' ? 9 : 0 }
  return r
})
export const cancelRequest = (id: string) => write(() => {
  const r = db.requests.find((x) => x.id === id)!
  if (!['submitted', 'confirmed', 'covered_by_stock', 'matching'].includes(r.status)) throw new ApiError(409, 'invalid_transition', 'This request is already closed.')
  r.status = 'cancelled'
})

// ---------- donors ----------
export interface DonorFilter { group?: string; eligible?: '' | 'yes' | 'no'; q?: string }
export const eligibleAgain = (d: { last_donation_on: string | null; deferral: { eligible_again_on: string } | null }) => {
  const cooldown = Number(db.settings.find((s) => s.key === 'donor_cooldown_days')!.value)
  const fromCooldown = d.last_donation_on ? Date.parse(d.last_donation_on) + cooldown * DAY : 0
  const fromDeferral = d.deferral ? Date.parse(d.deferral.eligible_again_on) : 0
  return Math.max(fromCooldown, fromDeferral)
}
export const listDonors = (f: DonorFilter) => read(() => db.donors.filter((d) => {
  const elig = eligibleAgain(d) <= NOW
  return (!f.group || `${d.abo}${d.rh}` === f.group) && (!f.eligible || (f.eligible === 'yes') === elig) && (!f.q || d.ref.toLowerCase().includes(f.q.toLowerCase()) || d.area_label.toLowerCase().includes(f.q.toLowerCase()))
}))
export const addDeferral = (id: string, category: string, eligible_again_on: string) => write(() => {
  const d = db.donors.find((x) => x.id === id)!
  d.deferral = { category, eligible_again_on }
  appendAudit(actor(), 'donor.deferral', 'donor', d.ref, Date.now())
})
export const verifyGroup = (id: string) => write(() => {
  const d = db.donors.find((x) => x.id === id)!
  d.group_verified = true
  appendAudit(actor(), 'donor.verify_group', 'donor', d.ref, Date.now())
})

let donorRegistered = false
export const getDonorProfile = () => read(() => {
  if (!donorRegistered) throw new ApiError(404, 'not_registered', 'Complete donor registration first.')
  return db.donorProfile
})
export type ProfilePatch = Partial<Donor> & { consent?: boolean }
export const updateDonorProfile = (patch: ProfilePatch) => write(() => {
  if (!donorRegistered && !patch.consent) throw new ApiError(422, 'consent_required', 'Consent is required.')
  donorRegistered = true
  return Object.assign(db.donorProfile, patch)
})
export const exportDonorData = () => read(() => {
  appendAudit(actor(), 'donor.export', 'donor', db.donorProfile.ref, Date.now())
  return { exported_at: new Date().toISOString(), profile: db.donorProfile, invitations: db.invitations }
})
export const deleteDonorData = () => write(() => {
  appendAudit(actor(), 'donor.delete', 'donor', db.donorProfile.ref, Date.now())
  setSession(null)
})
export const listInvitations = () => read(() => db.invitations)
export const respondInvitation = (id: string, accept: boolean) => write(() => {
  const inv = db.invitations.find((x) => x.id === id)!
  if (inv.status !== 'invited') throw new ApiError(409, 'invalid_transition', 'This invitation is closed.')
  inv.status = accept ? 'accepted' : 'declined'
  if (accept && !db.threads.some((t) => t.id === id)) db.threads.push({ id, request_ref: inv.request_ref, hospital_area: inv.hospital_area, donor_shares_phone: false, requester_shares_phone: false, counterpart_phone: null, messages: [] })
})
export const getThread = (id: string) => read<MatchThread>(() => {
  const t = db.threads.find((x) => x.id === id)
  if (!t) throw new ApiError(404, 'not_found', 'Conversation not found.')
  // Phone revealed only when both sides opt in (FR-MAT-04, SEC-08).
  return { ...t, counterpart_phone: t.donor_shares_phone && t.requester_shares_phone ? '+880 1000-000 001' : null }
})
export const sendMessage = (id: string, body: string) => write(() => {
  const t = db.threads.find((x) => x.id === id)!
  t.messages.push({ id: t.messages.length + 1, mine: true, body: body.slice(0, 1000), created_at: new Date().toISOString() })
})
export const sharePhone = (id: string) => write(() => {
  const t = db.threads.find((x) => x.id === id)!
  t.donor_shares_phone = true
  appendAudit(actor(), 'match.share_phone', 'donor_match', id.slice(0, 8), Date.now())
})

// ---------- alerts ----------
export const listAlerts = () => read<Alert[]>(() => {
  const s = session!
  return db.alerts.filter((a) => s.role !== 'hospital_lead' || (a.site_id && s.site_ids.includes(a.site_id))).sort((a, b) => b.created_at.localeCompare(a.created_at))
})
export const setAlertStatus = (id: string, status: 'acknowledged' | 'resolved') => write(() => {
  const a = db.alerts.find((x) => x.id === id)!
  a.status = status
  if (status === 'acknowledged') { a.acknowledged_by = actor(); a.acknowledged_at = new Date().toISOString() }
})

// ---------- reports ----------
export type ReportName = 'stock' | 'wastage' | 'transfers' | 'requests'
export const report = (name: ReportName) => read<Record<string, string | number>[]>(() => {
  if (name === 'stock' || name === 'wastage') {
    return db.sites.map((s) => {
      const mine = db.units.filter((u) => u.site_id === s.id)
      const count = (st: UnitStatus) => mine.filter((u) => u.status === st).length
      const row: Record<string, string | number> = name === 'stock'
        ? { site: s.code, available: count('available'), reserved: count('reserved'), in_transit: count('in_transit'), quarantined: count('quarantined') }
        : { site: s.code, expired: count('expired'), discarded: count('discarded'), issued: count('issued'), wastage_pct: Math.round((count('expired') / Math.max(1, mine.length)) * 1000) / 10 }
      return row
    })
  }
  if (name === 'transfers') return db.transfers.map((t) => ({ from: code(t.from_site_id), to: code(t.to_site_id), group: `${t.abo}${t.rh === 'neg' ? '-' : '+'}`, units: t.units, status: t.status }))
  return db.requests.map((r) => ({ ref: r.ref, site: code(r.site_id), group: `${r.abo}${r.rh === 'neg' ? '-' : '+'}`, needed: r.units_needed, secured: r.units_secured, urgency: r.urgency, status: r.status }))
})
const code = (id: string) => db.sites.find((s) => s.id === id)?.code ?? id

// ---------- admin ----------
export const listUsers = () => read(() => db.staff)
export const updateUser = (id: string, patch: { active?: boolean; role?: Role; site_ids?: string[] }) => write(() => {
  const u = db.staff.find((x) => x.id === id)!
  Object.assign(u, patch)
  appendAudit(actor(), 'user.update', 'user', u.email, Date.now())
})
export const listSettings = () => read(() => ({ settings: db.settings, history: [...db.settingHistory].reverse() }))
export const updateSetting = (key: string, value: Setting['value']) => write(() => {
  const s = db.settings.find((x) => x.key === key)!
  db.settingHistory.push({ key, old_value: s.value, new_value: value, version: s.version + 1, changed_by: actor(), changed_at: new Date().toISOString() })
  Object.assign(s, { value, version: s.version + 1, updated_by: actor(), updated_at: new Date().toISOString() })
  appendAudit(actor(), 'setting.change', 'setting', key, Date.now())
})
export const listCompatRules = (component: Component) => read(() => db.compatRules.filter((r) => r.component === component))

// ---------- audit ----------
export const listAudit = (q: string) => read(() => [...db.audit].reverse().filter((e) => !q || `${e.action} ${e.actor} ${e.entity_id}`.toLowerCase().includes(q.toLowerCase())).slice(0, 200))
export const verifyAudit = () => read<ChainCheck>(() => {
  let prev = '00000000'
  for (const e of db.audit) {
    if (fnv(prev + auditPayload(e)) !== e.hash) return { ok: false, checked: e.id, broken_at: e.id }
    prev = e.hash
  }
  appendAudit(actor(), 'audit.verify', 'audit_event', String(db.audit.length), Date.now())
  return { ok: true, checked: db.audit.length - 1, broken_at: null }
})


// ---------- low stock and appeals (mock) ----------
const GROUP_OF: Record<string, [Abo, Rh]> = { 'O+': ['O', 'pos'], 'O−': ['O', 'neg'], 'A+': ['A', 'pos'], 'A−': ['A', 'neg'], 'B+': ['B', 'pos'], 'B−': ['B', 'neg'], 'AB+': ['AB', 'pos'], 'AB−': ['AB', 'neg'] }
export const lowStock = () => read<LowStock[]>(() => db.alerts.filter((a) => a.type === 'stockout' && a.payload.component === 'red_cells' && a.site_id).map((a) => {
  const [abo, rh] = GROUP_OF[String(a.payload.group)] ?? ['O', 'pos']
  const open = db.requests.find((r) => r.kind === 'appeal' && r.site_id === a.site_id && r.abo === abo && r.rh === rh && ['matching', 'confirmed'].includes(r.status))
  return { site_id: a.site_id!, abo, rh, available: 1, demand: 1 + Number(a.payload.short), shortfall: Number(a.payload.short), days: 2, open_appeal_id: open?.id ?? null }
}))
export interface AppealBody { site_id: string; abo: Abo; rh: Rh; units: number; urgency: Urgency; hours?: number }
export const createAppeal = (b: AppealBody) => write(() => {
  if (db.requests.some((r) => r.kind === 'appeal' && r.site_id === b.site_id && r.abo === b.abo && r.rh === b.rh && r.status === 'matching'))
    throw new ApiError(409, 'appeal_open', 'An appeal for this group is already running at this site.')
  const r: BloodRequest = {
    id: crypto.randomUUID(), ref: `AP-${2900 + db.requests.length}`, kind: 'appeal', requester_id: session!.user_id, site_id: b.site_id, abo: b.abo, rh: b.rh,
    component: 'red_cells', units_needed: b.units, units_secured: 0, urgency: b.urgency, needed_by: iso(Date.now() + (b.hours ?? 72) * 3_600_000),
    status: 'matching', confirmed_at: new Date().toISOString(), created_at: new Date().toISOString(), shortfall: b.units, wave: 1,
    progress: { stock_units: 0, donors_notified: Math.min(40, b.units * 4 + 3), donors_accepted: 0 },
  }
  db.requests.unshift(r)
  appendAudit(actor(), 'appeal.create', 'blood_request', r.ref, Date.now())
  return r
})
const mockMatches = new Map<string, RequestMatch[]>()
export const listRequestMatches = (id: string) => read<RequestMatch[]>(() => {
  if (!mockMatches.has(id)) {
    const r = db.requests.find((x) => x.id === id)!
    mockMatches.set(id, db.donors.slice(0, r.progress.donors_notified).map((d, i) => ({
      id: `${id}-${i}`, donor_ref: d.ref, abo: d.abo, rh: d.rh, group_verified: d.group_verified, wave: 1 + Math.floor(i / 6),
      score: Math.round((0.9 - i * 0.02) * 1000) / 1000, status: i < r.progress.donors_accepted ? 'accepted' : 'invited', invited_at: r.created_at, responded_at: null,
    })))
  }
  return mockMatches.get(id)!
})
export const recordMatchOutcome = (matchId: string, outcome: 'donated' | 'no_show' | 'deferred_on_site') => write(() => {
  for (const [rid, list] of mockMatches) {
    const m = list.find((x) => x.id === matchId)
    if (!m) continue
    if (m.status !== 'accepted') throw new ApiError(409, 'invalid_transition', 'Only accepted invitations get an outcome.')
    m.status = outcome
    const r = db.requests.find((x) => x.id === rid)!
    if (outcome === 'donated') { r.units_secured += 1; if (r.units_secured >= r.units_needed) r.status = 'fulfilled' }
  }
})
