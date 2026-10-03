import { useTranslation } from 'react-i18next'
import type { RequestStatus, Severity, UnitStatus, Urgency } from '../api/types'
import { Badge, type Tone } from './ui'
import { daysUntil } from '../lib/format'

const UNIT: Record<UnitStatus, Tone> = { available: 'good', reserved: 'info', in_transit: 'brand', quarantined: 'warn', issued: 'neutral', expired: 'bad', discarded: 'neutral' }
const REQ: Record<RequestStatus, Tone> = {
  submitted: 'warn', confirmed: 'info', covered_by_stock: 'good', matching: 'brand',
  fulfilled: 'good', partially_fulfilled: 'warn', unfilled: 'bad', cancelled: 'neutral',
}
const SEV: Record<Severity, Tone> = { critical: 'bad', warning: 'warn', info: 'info' }
const URG: Record<Urgency, Tone> = { emergency: 'bad', urgent: 'warn', routine: 'neutral' }

export function UnitStatusBadge({ s }: { s: UnitStatus }) { const { t } = useTranslation(); return <Badge tone={UNIT[s]} dot>{t(`unitStatus.${s}`)}</Badge> }
export function RequestStatusBadge({ s }: { s: RequestStatus }) { const { t } = useTranslation(); return <Badge tone={REQ[s]} dot>{t(`requestStatus.${s}`)}</Badge> }
export function SeverityBadge({ s }: { s: Severity }) { const { t } = useTranslation(); return <Badge tone={SEV[s]} dot>{t(`severity.${s}`)}</Badge> }
export function UrgencyBadge({ u }: { u: Urgency }) { const { t } = useTranslation(); return <Badge tone={URG[u]}>{t(`urgency.${u}`)}</Badge> }

/** Days-to-expiry with colour + text, never colour alone. */
export function ExpiryCell({ at }: { at: string }) {
  const { t } = useTranslation()
  const d = daysUntil(at)
  const tone = d < 0 ? 'text-red-700' : d <= 2 ? 'text-red-700 font-medium' : d <= 7 ? 'text-amber-800' : 'text-zinc-700'
  return <span className={`font-mono tabular-nums text-sm ${tone}`}>{d < 0 ? t('stock.expiredAgo') : d < 1 ? t('stock.hoursLeft', { count: Math.max(1, Math.floor(d * 24)) }) : t('stock.daysLeft', { count: Math.floor(d) })}</span>
}
