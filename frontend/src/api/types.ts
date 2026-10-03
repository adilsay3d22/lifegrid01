// Shapes mirror spec section 11. Replace with the generated OpenAPI client types when the API exists.
export type Role = 'bank_manager' | 'hospital_lead' | 'donor_coordinator' | 'donor' | 'requester' | 'admin' | 'auditor'
export type Abo = 'O' | 'A' | 'B' | 'AB'
export type Rh = 'pos' | 'neg'
export type Component = 'red_cells' | 'platelets' | 'plasma'
export type UnitStatus = 'available' | 'reserved' | 'in_transit' | 'quarantined' | 'issued' | 'expired' | 'discarded'
export type Urgency = 'emergency' | 'urgent' | 'routine'
export type RequestStatus =
  | 'submitted' | 'confirmed' | 'covered_by_stock' | 'matching'
  | 'fulfilled' | 'partially_fulfilled' | 'unfilled' | 'cancelled'
export type MatchStatus = 'invited' | 'accepted' | 'declined' | 'expired' | 'donated' | 'no_show' | 'deferred_on_site' | 'withdrawn'
export type Availability = 'available' | 'unavailable' | 'travelling'
export type Severity = 'critical' | 'warning' | 'info'

export interface Site {
  id: string; code: string; name: string; type: 'hospital' | 'blood_bank'
  lat: number; lng: number; timezone: string; active: boolean
}

export interface BloodUnit {
  id: string; unit_code: string; abo: Abo; rh: Rh; component: Component
  collected_at: string; expires_at: string; site_id: string; status: UnitStatus; reserved_for: string | null
}

export interface UnitMovement {
  id: number; unit_id: string; from_status: UnitStatus | null; to_status: UnitStatus
  from_site_id: string | null; to_site_id: string | null; actor: string; reason: string; created_at: string
}

export interface StockCell { site_id: string; component: Component; abo: Abo; rh: Rh; band_0_2: number; band_3_7: number; band_8: number }

export interface ForecastPoint { day: string; actual?: number; point?: number; low?: number; high?: number }
export interface ForecastSeries { model: string; model_version: string; mae: number; coverage: number | null; baseline_mae: number; points: ForecastPoint[] }

export interface Recommendation {
  id: string; plan_id: string; from_site_id: string; to_site_id: string; component: Component; abo: Abo; rh: Rh
  units: number; reason: 'expiry_risk' | 'projected_shortage'; expected_benefit: { expired_avoided: number; shortage_avoided: number; km: number }
  status: 'proposed' | 'approved' | 'rejected' | 'superseded'; decided_by: string | null; decided_at: string | null
}

export interface TransferPlan {
  id: string; created_at: string; horizon_days: number; status: 'proposed' | 'reviewed' | 'expired'
  solver_status: string; solver_seconds: number; is_fallback: boolean
  projected: { without: { expired: number; short: number }; with: { expired: number; short: number } }
  recommendations: Recommendation[]
}

export interface Transfer {
  id: string; recommendation_id: string; from_site_id: string; to_site_id: string
  component: Component; abo: Abo; rh: Rh; units: number
  status: 'approved' | 'dispatched' | 'received' | 'cancelled'; dispatched_at: string | null; received_at: string | null
  unit_codes: string[]
}

export interface BloodRequest {
  id: string; ref: string; requester_id: string; site_id: string; abo: Abo; rh: Rh; component: Component
  units_needed: number; units_secured: number; urgency: Urgency; needed_by: string; status: RequestStatus
  confirmed_at: string | null; created_at: string
  progress: { stock_units: number; donors_notified: number; donors_accepted: number }
  kind?: 'patient' | 'appeal'; shortfall?: number; wave?: number; escalated_at?: string | null; transfer_plan_id?: string | null
  accepted_matches?: { id: string; status: MatchStatus }[]
}

export interface RequestMatch {
  id: string; donor_ref: string; abo: Abo | null; rh: Rh | null; group_verified: boolean; wave: number; score: number
  status: MatchStatus; invited_at: string; responded_at: string | null
}

export interface LowStock { site_id: string; abo: Abo; rh: Rh; available: number; demand: number; shortfall: number; days: number; open_appeal_id: string | null }

export interface Donor {
  id: string; ref: string; abo: Abo | null; rh: Rh | null; group_verified: boolean; area_label: string
  last_donation_on: string | null; availability: Availability; reliability: number
  deferral: { category: string; eligible_again_on: string } | null
  eligible_from?: string | null; area_lat?: number | null; area_lng?: number | null; birth_year?: number | null
  weight_ok: boolean | null; quiet_start: string | null; quiet_end: string | null; emergency_override: boolean; max_invites_30d: number
  consent_version: string; consent_at: string
}

export interface Invitation {
  id: string; request_ref: string; abo: Abo; rh: Rh; hospital_area: string; urgency: Urgency; needed_by: string; status: MatchStatus
  kind?: 'patient' | 'appeal'
}

export interface Message { id: number; mine: boolean; body: string; created_at: string }
export interface MatchThread {
  id: string; request_ref: string; hospital_area: string; donor_shares_phone: boolean; requester_shares_phone: boolean
  counterpart_phone: string | null; messages: Message[]; role?: 'donor' | 'requester'
}

export interface Alert {
  id: string; type: 'expiry' | 'stockout' | 'temperature' | 'unfilled_request'; severity: Severity
  site_id: string | null; payload: Record<string, string | number>; status: 'open' | 'acknowledged' | 'resolved'
  acknowledged_by: string | null; acknowledged_at: string | null; created_at: string
}

export interface StaffUser { id: string; email: string; role: Role; site_ids: string[]; active: boolean; totp: boolean }

export interface Setting { key: string; value: number | boolean | string; version: number; updated_by: string; updated_at: string }
export interface SettingChange { key: string; old_value: unknown; new_value: unknown; version: number; changed_by: string; changed_at: string }

export interface CompatRule { component: Component; recipient_abo: Abo; recipient_rh: Rh; donor_abo: Abo; donor_rh: Rh; rank: number }

export interface AuditEvent { id: number; actor: string; action: string; entity_type: string; entity_id: string; created_at: string; hash: string }
export interface ChainCheck { ok: boolean; checked: number; broken_at: number | null }

export interface Session { user_id: string; role: Role; email: string | null; site_ids: string[] }
