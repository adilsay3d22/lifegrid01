import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Check, X } from '@phosphor-icons/react'
import { decide, getPlan, listSites } from '../../api/client'
import type { Recommendation, Site } from '../../api/types'
import { Badge, Button, Dialog, GroupChip, PageHeader, QueryView, inputCls, cx } from '../../components/ui'
import { groupLabel } from '../../lib/rules'
import { fmtDateTime, fmtNum } from '../../lib/format'

export function Component() {
  const { id = '' } = useParams()
  const { t } = useTranslation()
  const q = useQuery({ queryKey: ['plan', id], queryFn: () => getPlan(id) })
  const sites = useQuery({ queryKey: ['sites'], queryFn: listSites })
  const site = (sid: string) => sites.data?.find((s) => s.id === sid)

  return (
    <QueryView q={q} rows={8}>
      {(p) => {
        const pending = p.recommendations.filter((r) => r.status === 'proposed').length
        return (
          <div className="grid gap-8">
            <PageHeader
              eyebrow={t('plan.eyebrow', { date: fmtDateTime(p.created_at) })}
              title={t('plan.title')}
              description={t('plan.description', { days: p.horizon_days })}
              actions={<div className="flex flex-wrap items-center gap-2">
                <Badge tone={p.is_fallback ? 'warn' : 'good'} dot>{p.is_fallback ? t('plan.fallback') : t('plan.solver', { status: p.solver_status })}</Badge>
                <Badge><span className="font-mono">{fmtNum(p.solver_seconds, 1)} s</span></Badge>
              </div>}
            />

            <section aria-labelledby="eff-h" className="reveal grid gap-6 md:grid-cols-[minmax(0,0.9fr)_minmax(0,2fr)] md:items-center">
              <div>
                <h2 id="eff-h" className="text-base font-semibold tracking-tight">{t('plan.effectTitle')}</h2>
                <p className="mt-1 text-sm text-zinc-600">{t('plan.effectBody')}</p>
              </div>
              <dl className="grid gap-6 sm:grid-cols-2">
                <Effect label={t('plan.expired')} without={p.projected.without.expired} withPlan={p.projected.with.expired} />
                <Effect label={t('plan.short')} without={p.projected.without.short} withPlan={p.projected.with.short} />
              </dl>
            </section>

            <section aria-labelledby="rec-h" className="grid gap-4">
              <div className="flex items-baseline justify-between">
                <h2 id="rec-h" className="text-base font-semibold tracking-tight">{t('plan.recsTitle')}</h2>
                <p className="text-sm text-zinc-500">{t('plan.pending', { count: pending })}</p>
              </div>
              <ul className="divide-y divide-zinc-200 rounded-2xl bg-white ring-1 ring-zinc-200">
                {p.recommendations.map((r, i) => <RecRow key={r.id} r={r} from={site(r.from_site_id)} to={site(r.to_site_id)} i={i} planId={p.id} />)}
              </ul>
            </section>
          </div>
        )
      }}
    </QueryView>
  )
}

function Effect({ label, without, withPlan }: { label: string; without: number; withPlan: number }) {
  const { t } = useTranslation()
  const max = Math.max(without, 1)
  return (
    <div className="grid gap-2">
      <dt className="text-xs font-medium uppercase tracking-wider text-zinc-500">{label}</dt>
      <dd className="grid gap-1.5">
        <div className="grid grid-cols-[5rem_1fr_2.5rem] items-center gap-3 text-sm">
          <span className="text-zinc-500">{t('plan.without')}</span>
          <span className="h-2 rounded-full bg-zinc-300" style={{ width: `${(without / max) * 100}%` }} aria-hidden />
          <span className="text-right font-mono tabular-nums text-zinc-700">{without}</span>
        </div>
        <div className="grid grid-cols-[5rem_1fr_2.5rem] items-center gap-3 text-sm">
          <span className="font-medium text-zinc-900">{t('plan.with')}</span>
          <span className="h-2 rounded-full bg-brand" style={{ width: `${(withPlan / max) * 100}%`, minWidth: 4 }} aria-hidden />
          <span className="text-right font-mono font-medium tabular-nums text-zinc-950">{withPlan}</span>
        </div>
      </dd>
    </div>
  )
}

function RecRow({ r, from, to, i, planId }: { r: Recommendation; from?: Site; to?: Site; i: number; planId: string }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [units, setUnits] = useState(r.units)
  const [confirm, setConfirm] = useState<'approve' | 'reject' | null>(null)
  const m = useMutation({
    mutationFn: (approve: boolean) => decide(r.id, approve, units),
    onSuccess: () => { setConfirm(null); qc.invalidateQueries({ queryKey: ['plan', planId] }); qc.invalidateQueries({ queryKey: ['transfers'] }) },
  })
  const decided = r.status !== 'proposed'
  const invalid = !Number.isInteger(units) || units < 1 || units > r.units
  return (
    <li className={cx('reveal grid gap-4 p-4 md:grid-cols-[minmax(0,1.6fr)_auto_minmax(0,1.3fr)_auto] md:items-center md:px-5', decided && 'bg-zinc-50/70')} style={{ '--i': i } as React.CSSProperties}>
      <div className="min-w-0">
        <p className="grid text-sm font-medium text-zinc-900">
          <span className="truncate">{from?.name}</span>
          <span className="flex min-w-0 items-center gap-1.5">
            <ArrowRight size={14} className="shrink-0 text-brand" aria-hidden /><span className="sr-only">{t('plan.to')}</span>
            <span className="truncate">{to?.name}</span>
          </span>
        </p>
        <p className="mt-1 text-xs text-zinc-500">{t(`component.${r.component}`)} &middot; <span className="font-mono">{fmtNum(r.expected_benefit.km, 1)} km</span></p>
      </div>
      <div className="flex items-center gap-3">
        <GroupChip label={groupLabel(r.abo, r.rh)} />
        {decided ? <span className="font-mono text-sm tabular-nums">{t('plan.units', { count: r.units })}</span> : (
          <label className="flex items-center gap-2 text-sm">
            <span className="sr-only">{t('plan.unitsLabel', { max: r.units })}</span>
            <input type="number" inputMode="numeric" min={1} max={r.units} value={units} onChange={(e) => setUnits(Number(e.target.value))} aria-invalid={invalid || undefined}
              className={`${inputCls} h-9 w-16 font-mono tabular-nums`} />
            <span className="whitespace-nowrap text-zinc-500">{t('plan.unitsSuffix', { max: r.units })}</span>
          </label>
        )}
      </div>
      <div className="min-w-0">
        <Badge tone={r.reason === 'expiry_risk' ? 'warn' : 'info'}>{t(r.reason.startsWith('request:') ? 'plan.reason.request' : `plan.reason.${r.reason}`)}</Badge>
        <p className="mt-1.5 text-xs text-zinc-600">{t('plan.benefit', { expired: r.expected_benefit.expired_avoided, short: r.expected_benefit.shortage_avoided })}</p>
      </div>
      <div className="flex gap-2 md:justify-end">
        {decided ? (
          <Badge tone={r.status === 'approved' ? 'good' : 'neutral'} dot>{t(`plan.status.${r.status}`)}</Badge>
        ) : <>
          <Button size="sm" variant="ghost" onClick={() => setConfirm('reject')}><X size={16} aria-hidden />{t('plan.reject')}</Button>
          <Button size="sm" variant="primary" disabled={invalid} onClick={() => setConfirm('approve')}><Check size={16} aria-hidden />{t('plan.approve')}</Button>
        </>}
      </div>
      <Dialog open={!!confirm} onClose={() => setConfirm(null)}
        title={confirm === 'approve' ? t('plan.confirmApprove', { count: units }) : t('plan.confirmReject')}
        description={`${from?.name} → ${to?.name} · ${groupLabel(r.abo, r.rh)} ${t(`component.${r.component}`)}`}
        footer={<>
          <Button variant="ghost" onClick={() => setConfirm(null)}>{t('common.cancel')}</Button>
          <Button variant={confirm === 'approve' ? 'primary' : 'danger'} loading={m.isPending} onClick={() => m.mutate(confirm === 'approve')}>
            {confirm === 'approve' ? t('plan.approve') : t('plan.reject')}
          </Button>
        </>}>
        {confirm === 'approve' && units < r.units && <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-inset ring-amber-200">{t('plan.editedBody', { from: r.units, to: units })}</p>}
      </Dialog>
    </li>
  )
}
