// Synthetic, seeded demo data (spec SEC-17). No real people, phones or medical detail.
// ponytail: in-memory store, resets on reload; replaced by the FastAPI backend in phases 1-7.
import type {
  Alert, AuditEvent, BloodRequest, BloodUnit, Component, Donor, Invitation, MatchThread,
  Rh, Abo, Setting, SettingChange, Site, StaffUser, Transfer, TransferPlan, UnitStatus,
} from './types'
import { ABOS, COMPONENTS, GROUPS, SHELF_DAYS, seedCompatRules } from '../lib/rules'

function mulberry32(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
const rand = mulberry32(42)
const pick = <T,>(xs: readonly T[]) => xs[Math.floor(rand() * xs.length)]
const int = (lo: number, hi: number) => lo + Math.floor(rand() * (hi - lo + 1))
function poisson(mean: number) {
  const l = Math.exp(-mean); let k = 0; let p = 1
  do { k++; p *= rand() } while (p > l)
  return k - 1
}
const hex = (n: number) => Array.from({ length: n }, () => Math.floor(rand() * 16).toString(16)).join('')
const uuid = () => `${hex(8)}-${hex(4)}-4${hex(3)}-${hex(4)}-${hex(12)}`

const DAY = 86_400_000
export const NOW = Math.floor(Date.now() / 3_600_000) * 3_600_000
export const iso = (ms: number) => new Date(ms).toISOString()
export const dayIso = (ms: number) => iso(ms).slice(0, 10)

const SITE_ROWS: [string, string, Site['type'], number, number, number][] = [
  ['BB-CEN', 'Central Regional Blood Bank', 'blood_bank', 23.733, 90.395, 3],
  ['BB-NTH', 'Northern Blood Bank', 'blood_bank', 23.874, 90.398, 2.4],
  ['H-MIR', 'Mirpur Medical Centre', 'hospital', 23.8069, 90.3687, 1.6],
  ['H-UTT', 'Uttara Lakeview Hospital', 'hospital', 23.8759, 90.3795, 1.1],
  ['H-GUL', 'Gulshan Riverside Hospital', 'hospital', 23.7925, 90.4078, 1.4],
  ['H-DHN', 'Dhanmondi Teaching Hospital', 'hospital', 23.7461, 90.3742, 2.1],
  ['H-MOT', 'Motijheel City Hospital', 'hospital', 23.733, 90.4172, 1],
  ['H-BAD', 'Badda Community Hospital', 'hospital', 23.7806, 90.4265, 0.6],
  ['H-MOH', 'Mohammadpur Clinic', 'hospital', 23.7662, 90.3589, 0.5],
  ['H-JAT', 'Jatrabari Trauma Centre', 'hospital', 23.7104, 90.4348, 1.3],
  ['H-KER', 'Keraniganj District Hospital', 'hospital', 23.6985, 90.346, 0.6],
  ['H-SAV', 'Savar Regional Hospital', 'hospital', 23.8583, 90.2667, 0.8],
  ['H-TON', 'Tongi Medical College Hospital', 'hospital', 23.8916, 90.4023, 0.9],
  ['H-NAR', 'Narayanganj General', 'hospital', 23.6238, 90.499, 0.7],
]
const sites: Site[] = SITE_ROWS.map(([code, name, type, lat, lng]) => ({ id: uuid(), code, name, type, lat, lng, timezone: 'Asia/Dhaka', active: true }))
const siteSize = new Map(sites.map((s, i) => [s.id, SITE_ROWS[i][5]]))

const MIX: Record<string, number> = { 'O-pos': 0.35, 'A-pos': 0.28, 'B-pos': 0.2, 'AB-pos': 0.07, 'O-neg': 0.04, 'A-neg': 0.03, 'B-neg': 0.02, 'AB-neg': 0.01 }
const COMP_BASE: Record<Component, number> = { red_cells: 70, platelets: 12, plasma: 30 }

const units: BloodUnit[] = []
let unitSeq = 41_200
for (const site of sites) {
  for (const component of COMPONENTS) {
    for (const [abo, rh] of GROUPS) {
      const n = poisson(COMP_BASE[component] * MIX[`${abo}-${rh}`] * siteSize.get(site.id)!)
      for (let k = 0; k < n; k++) {
        const shelf = SHELF_DAYS[component]
        const age = rand() * shelf * 1.02
        const collected = NOW - age * DAY
        const expires = collected + shelf * DAY
        const r = rand()
        let status: UnitStatus = expires < NOW ? 'expired' : r < 0.06 ? 'reserved' : r < 0.09 ? 'in_transit' : r < 0.11 ? 'quarantined' : 'available'
        if (status === 'available' && rand() < 0.04) status = 'issued'
        units.push({
          id: uuid(), unit_code: `LG26-${String(unitSeq++).padStart(7, '0')}`, abo, rh, component,
          collected_at: iso(collected), expires_at: iso(expires), site_id: site.id, status, reserved_for: null,
        })
      }
    }
  }
}

const AREAS = ['Mirpur 10', 'Uttara Sector 7', 'Gulshan 2', 'Dhanmondi 27', 'Motijheel', 'Badda', 'Mohammadpur', 'Jatrabari', 'Savar', 'Tongi', 'Banani', 'Bashundhara', 'Rampura', 'Lalbagh']
const DEFERRALS = ['low_haemoglobin', 'recent_travel', 'medication', 'recent_procedure', 'temporary_illness']

const donors: Donor[] = Array.from({ length: 240 }, (_, i) => {
  const [abo, rh] = rand() < 0.08 ? [null, null] : (pick(GROUPS) as [Abo, Rh])
  const last = rand() < 0.7 ? NOW - int(14, 400) * DAY : null
  const deferred = rand() < 0.07
  return {
    id: uuid(), ref: `D-${(0x4a00 + i * 37).toString(16).toUpperCase()}`, abo, rh, group_verified: rand() < 0.55,
    area_label: pick(AREAS), last_donation_on: last ? dayIso(last) : null,
    availability: rand() < 0.78 ? 'available' : rand() < 0.5 ? 'unavailable' : 'travelling',
    reliability: Math.round((0.25 + rand() * 0.7) * 1000) / 1000,
    deferral: deferred ? { category: pick(DEFERRALS), eligible_again_on: dayIso(NOW + int(5, 90) * DAY) } : null,
    weight_ok: true, quiet_start: rand() < 0.6 ? '22:00' : null, quiet_end: rand() < 0.6 ? '07:00' : null,
    emergency_override: rand() < 0.4, max_invites_30d: 2, consent_version: 'v1.2', consent_at: iso(NOW - int(20, 300) * DAY),
  }
})

const hospitals = sites.filter((s) => s.type === 'hospital')
const banks = sites.filter((s) => s.type === 'blood_bank')

const staff: StaffUser[] = [
  { id: uuid(), email: 'nabila.karim@lifegrid.test', role: 'bank_manager', site_ids: banks.map((b) => b.id), active: true, totp: true },
  { id: uuid(), email: 'tanvir.rahman@lifegrid.test', role: 'hospital_lead', site_ids: [hospitals[3].id], active: true, totp: false },
  { id: uuid(), email: 'farhana.siddiqui@lifegrid.test', role: 'hospital_lead', site_ids: [hospitals[0].id, hospitals[4].id], active: true, totp: false },
  { id: uuid(), email: 'imran.chowdhury@lifegrid.test', role: 'donor_coordinator', site_ids: [], active: true, totp: false },
  { id: uuid(), email: 'sadia.haque@lifegrid.test', role: 'admin', site_ids: [], active: true, totp: true },
  { id: uuid(), email: 'mahmud.alam@lifegrid.test', role: 'auditor', site_ids: [], active: true, totp: false },
  { id: uuid(), email: 'rumana.akter@lifegrid.test', role: 'hospital_lead', site_ids: [hospitals[7].id], active: false, totp: false },
]
const appUsers = { donor: { id: uuid(), donorIndex: 3 }, requester: { id: uuid() } }

// Transfer plan from last night's 02:00 run.
const planId = uuid()
const plan: TransferPlan = {
  id: planId, created_at: iso(NOW - (NOW % DAY) - 4 * 3_600_000), horizon_days: 3, status: 'proposed',
  solver_status: 'OPTIMAL', solver_seconds: 11.37, is_fallback: false,
  projected: { without: { expired: 0, short: 0 }, with: { expired: 0, short: 0 } },
  recommendations: [],
}
const km = (a: Site, b: Site) => {
  const dLat = (b.lat - a.lat) * 111, dLng = (b.lng - a.lng) * 111 * Math.cos((a.lat * Math.PI) / 180)
  return Math.round(Math.hypot(dLat, dLng) * 10) / 10
}
for (let i = 0; i < 9; i++) {
  const from = i < 3 ? banks[i % 2] : pick(hospitals)
  let to = pick(hospitals)
  while (to.id === from.id) to = pick(hospitals)
  const [abo, rh] = pick(GROUPS.slice(0, 6))
  const n = int(2, 9)
  const reason = rand() < 0.55 ? 'expiry_risk' : 'projected_shortage'
  plan.recommendations.push({
    id: uuid(), plan_id: planId, from_site_id: from.id, to_site_id: to.id, component: i === 7 ? 'platelets' : 'red_cells', abo, rh, units: n,
    reason, expected_benefit: { expired_avoided: reason === 'expiry_risk' ? n - int(0, 1) : int(0, 1), shortage_avoided: reason === 'projected_shortage' ? n : int(0, 2), km: km(from, to) },
    status: 'proposed', decided_by: null, decided_at: null,
  })
}
const exp = plan.recommendations.reduce((s, r) => s + r.expected_benefit.expired_avoided, 0)
const sho = plan.recommendations.reduce((s, r) => s + r.expected_benefit.shortage_avoided, 0)
plan.projected = { without: { expired: exp + 7, short: sho + 4 }, with: { expired: 7, short: 4 } }

const transfers: Transfer[] = Array.from({ length: 5 }, (_, i) => {
  const from = i < 2 ? banks[i] : pick(hospitals)
  let to = pick(hospitals)
  while (to.id === from.id) to = pick(hospitals)
  const [abo, rh] = pick(GROUPS.slice(0, 6))
  const n = int(2, 6)
  const status = (['approved', 'approved', 'dispatched', 'dispatched', 'received'] as const)[i]
  return {
    id: uuid(), recommendation_id: uuid(), from_site_id: from.id, to_site_id: to.id, component: 'red_cells', abo, rh, units: n, status,
    dispatched_at: status === 'approved' ? null : iso(NOW - int(2, 20) * 3_600_000),
    received_at: status === 'received' ? iso(NOW - 3_600_000) : null,
    unit_codes: status === 'approved' ? [] : Array.from({ length: n }, () => `LG26-${String(int(41_200, unitSeq)).padStart(7, '0')}`),
  }
})

const REQ_STATES: BloodRequest['status'][] = ['submitted', 'submitted', 'confirmed', 'covered_by_stock', 'matching', 'matching', 'fulfilled', 'partially_fulfilled', 'unfilled', 'cancelled', 'fulfilled']
const requests: BloodRequest[] = REQ_STATES.map((status, i) => {
  const [abo, rh] = pick(GROUPS)
  const need = int(1, 4)
  const secured = status === 'fulfilled' ? need : status === 'partially_fulfilled' ? need - 1 : status === 'matching' ? int(0, need - 1) : status === 'covered_by_stock' ? need : 0
  const created = NOW - int(1, 60) * 3_600_000
  const done = ['fulfilled', 'partially_fulfilled', 'unfilled', 'cancelled'].includes(status)
  return {
    id: uuid(), ref: `RQ-${2604 + i * 13}`, requester_id: i === 4 ? appUsers.requester.id : uuid(), site_id: [hospitals[0], hospitals[3], hospitals[4], hospitals[5]][i % 4].id,
    abo, rh, component: i === 3 ? 'platelets' : 'red_cells', units_needed: need, units_secured: secured,
    urgency: pick(['emergency', 'urgent', 'urgent', 'routine'] as const),
    needed_by: iso(done ? NOW - int(1, 20) * 3_600_000 : NOW + int(4, 48) * 3_600_000), status,
    confirmed_at: status === 'submitted' || status === 'cancelled' ? null : iso(created + 1_800_000), created_at: iso(created),
    progress: {
      stock_units: status === 'covered_by_stock' ? need : status === 'matching' ? 0 : secured,
      donors_notified: ['matching', 'fulfilled', 'partially_fulfilled', 'unfilled'].includes(status) ? int(6, 22) : 0,
      donors_accepted: status === 'matching' ? secured + int(0, 1) : ['fulfilled', 'partially_fulfilled'].includes(status) ? secured : 0,
    },
  }
})

const invitations: Invitation[] = [
  { id: uuid(), request_ref: 'RQ-2656', abo: 'O', rh: 'pos', hospital_area: 'Dhanmondi', urgency: 'urgent', needed_by: iso(NOW + 9 * 3_600_000), status: 'invited' },
  { id: uuid(), request_ref: 'RQ-2669', abo: 'O', rh: 'pos', hospital_area: 'Mirpur', urgency: 'emergency', needed_by: iso(NOW + 3 * 3_600_000), status: 'invited' },
  { id: uuid(), request_ref: 'RQ-2617', abo: 'A', rh: 'pos', hospital_area: 'Gulshan', urgency: 'routine', needed_by: iso(NOW - 30 * 3_600_000), status: 'accepted' },
]
const threads: MatchThread[] = [{
  id: invitations[2].id, request_ref: 'RQ-2617', hospital_area: 'Gulshan', donor_shares_phone: false, requester_shares_phone: true,
  counterpart_phone: null,
  messages: [
    { id: 1, mine: false, body: 'Thank you for accepting. The transfusion desk is on the ground floor, east wing.', created_at: iso(NOW - 26 * 3_600_000) },
    { id: 2, mine: true, body: 'I can be there by 10:30 tomorrow morning.', created_at: iso(NOW - 25 * 3_600_000) },
    { id: 3, mine: false, body: 'That works. Please bring a photo ID for the donation desk.', created_at: iso(NOW - 25 * 3_600_000 + 600_000) },
  ],
}]

const alerts: Alert[] = []
const addAlert = (a: Omit<Alert, 'id' | 'status' | 'acknowledged_by' | 'acknowledged_at'>) =>
  alerts.push({ id: uuid(), status: 'open', acknowledged_by: null, acknowledged_at: null, ...a })
for (const s of sites) {
  const soon = units.filter((u) => u.site_id === s.id && u.status === 'available' && u.component === 'red_cells' && Date.parse(u.expires_at) - NOW < 3 * DAY).length
  if (soon >= 3) addAlert({ type: 'expiry', severity: soon > 6 ? 'critical' : 'warning', site_id: s.id, payload: { units: soon, component: 'red_cells', days: 3 }, created_at: iso(NOW - int(1, 8) * 3_600_000) })
}
addAlert({ type: 'stockout', severity: 'critical', site_id: hospitals[8].id, payload: { group: 'O−', component: 'red_cells', days: 2, short: 3 }, created_at: iso(NOW - 2 * 3_600_000) })
addAlert({ type: 'stockout', severity: 'warning', site_id: hospitals[2].id, payload: { group: 'B+', component: 'platelets', days: 2, short: 2 }, created_at: iso(NOW - 5 * 3_600_000) })
addAlert({ type: 'temperature', severity: 'critical', site_id: hospitals[5].id, payload: { max_c: 9.4, component: 'red_cells', units: 6 }, created_at: iso(NOW - 40 * 60_000) })
addAlert({ type: 'unfilled_request', severity: 'warning', site_id: requests[8].site_id, payload: { ref: requests[8].ref }, created_at: iso(NOW - 11 * 3_600_000) })

const settings: Setting[] = [
  ['reservation_timeout_hours', 24], ['plan_run_time', '02:00'], ['solver_time_limit_s', 30], ['match_coverage_margin', 0.5],
  ['donor_cooldown_days', 120], ['max_invites_per_30d', 2], ['platelets_allow_out_of_group', true], ['platelets_prefer_rh_match', true],
  ['min_transfer_life_red_cells_days', 5], ['min_transfer_life_platelets_days', 1], ['min_transfer_life_plasma_days', 30],
  ['expiry_alert_red_cells_days', 3], ['expiry_alert_platelets_days', 1], ['expiry_alert_plasma_days', 14],
  ['requester_open_limit', 3], ['requester_daily_limit', 5],
].map(([key, value]) => ({ key: key as string, value: value as Setting['value'], version: 1, updated_by: 'system', updated_at: iso(NOW - 30 * DAY) }))
const settingHistory: SettingChange[] = [
  { key: 'solver_time_limit_s', old_value: 20, new_value: 30, version: 1, changed_by: 'sadia.haque@lifegrid.test', changed_at: iso(NOW - 30 * DAY) },
]

// Audit chain: hash = fnv(prev_hash + payload). Real system uses SHA-256 server-side (FR-AUD-02).
export function fnv(s: string) {
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) }
  return (h >>> 0).toString(16).padStart(8, '0')
}
export const auditPayload = (e: Omit<AuditEvent, 'hash'>) => `${e.id}|${e.actor}|${e.action}|${e.entity_type}|${e.entity_id}|${e.created_at}`
const audit: AuditEvent[] = []
export function appendAudit(actor: string, action: string, entity_type: string, entity_id: string, at = NOW) {
  const prev = audit.at(-1)?.hash ?? '00000000'
  const e = { id: audit.length + 1, actor, action, entity_type, entity_id, created_at: iso(at) }
  audit.push({ ...e, hash: fnv(prev + auditPayload(e)) })
}
const ACTIONS: [string, string][] = [['auth.sign_in', 'user'], ['unit.transition', 'blood_unit'], ['transfer.decision', 'recommendation'], ['request.confirm', 'blood_request'], ['setting.change', 'setting'], ['donor.export', 'donor'], ['auth.sign_in_failed', 'user'], ['unit.transition', 'blood_unit']]
for (let i = 0; i < 64; i++) {
  const [action, type] = pick(ACTIONS)
  appendAudit(pick(staff).email, action, type, type === 'blood_unit' ? pick(units).unit_code : uuid().slice(0, 8), NOW - (64 - i) * 47 * 60_000)
}

export const db = {
  sites, units, donors, staff, appUsers, plans: [plan], transfers, requests, invitations, threads, alerts,
  settings, settingHistory, compatRules: seedCompatRules(), audit, siteSize, MIX, COMP_BASE,
  donorProfile: { ...donors[appUsers.donor.donorIndex], abo: 'O', rh: 'pos', last_donation_on: dayIso(NOW - 132 * DAY), deferral: null, availability: 'available' } as Donor,
}
export { DAY, rand, int, mulberry32, ABOS }
