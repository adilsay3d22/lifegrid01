import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Megaphone, CheckCircle } from '@phosphor-icons/react'
import { ApiError, createAppeal, listSites, lowStock } from '../../api/client'
import type { LowStock, Urgency } from '../../api/types'
import { Badge, Button, Dialog, Field, GroupChip, QueryView, inputCls, Segmented } from '../../components/ui'
import { groupLabel } from '../../lib/rules'

/** Red-cell groups below forecast demand, with a one-click donor appeal. A person always starts the appeal. */
export function LowStockPanel() {
  const { t } = useTranslation()
  const q = useQuery({ queryKey: ['lowStock'], queryFn: lowStock })
  const sites = useQuery({ queryKey: ['sites'], queryFn: listSites })
  const [appeal, setAppeal] = useState<LowStock | null>(null)
  const name = (id: string) => sites.data?.find((s) => s.id === id)?.name ?? '—'

  return (
    <section aria-labelledby="low-h" className="reveal grid gap-3">
      <div>
        <h2 id="low-h" className="text-base font-semibold tracking-tight">{t('lowStock.title')}</h2>
        <p className="mt-1 text-sm text-zinc-600">{t('lowStock.body')}</p>
      </div>
      <QueryView q={q} rows={3} empty={<p className="rounded-xl border border-dashed border-zinc-300 px-4 py-5 text-sm text-zinc-600">{t('lowStock.empty')}</p>}>
        {(rows) => (
          <ul className="divide-y divide-zinc-200 rounded-2xl bg-white ring-1 ring-zinc-200">
            {rows.slice(0, 8).map((r) => (
              <li key={`${r.site_id}-${r.abo}-${r.rh}`} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <GroupChip label={groupLabel(r.abo, r.rh)} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-zinc-900">{name(r.site_id)}</span>
                  <span className="block text-xs text-zinc-500">{t('lowStock.line', { have: r.available, need: r.demand, days: r.days })}</span>
                </span>
                {r.open_appeal_id
                  ? <Badge tone="info" dot>{t('lowStock.appealRunning')}</Badge>
                  : <Button size="sm" variant="primary" onClick={() => setAppeal(r)}><Megaphone size={16} aria-hidden />{t('lowStock.appeal')}</Button>}
              </li>
            ))}
          </ul>
        )}
      </QueryView>
      {appeal && <AppealDialog row={appeal} siteName={name(appeal.site_id)} onClose={() => setAppeal(null)} />}
    </section>
  )
}

function AppealDialog({ row, siteName, onClose }: { row: LowStock; siteName: string; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [units, setUnits] = useState(Math.max(1, Math.min(20, row.shortfall)))
  const [urgency, setUrgency] = useState<Urgency>('urgent')
  const m = useMutation({
    mutationFn: () => createAppeal({ site_id: row.site_id, abo: row.abo, rh: row.rh, units, urgency }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['lowStock'] }); qc.invalidateQueries({ queryKey: ['requests'] }) },
  })
  const bad = !Number.isInteger(units) || units < 1 || units > 20
  return (
    <Dialog open onClose={onClose} title={t('lowStock.dialogTitle', { group: groupLabel(row.abo, row.rh), site: siteName })} description={t('lowStock.dialogBody')}
      footer={m.data ? <Button variant="primary" onClick={onClose}>{t('common.done')}</Button> : <>
        <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="primary" disabled={bad} loading={m.isPending} onClick={() => m.mutate()}><Megaphone size={16} aria-hidden />{t('lowStock.send')}</Button>
      </>}>
      {m.data ? (
        <p role="status" className="flex items-start gap-3 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-900 ring-1 ring-inset ring-emerald-200">
          <CheckCircle size={20} weight="fill" className="shrink-0" aria-hidden />
          {t('lowStock.sent', { count: m.data.progress.donors_notified, ref: m.data.ref })}
        </p>
      ) : (
        <div className="grid gap-4">
          <Field label={t('lowStock.units')} hint={t('lowStock.unitsHint', { shortfall: row.shortfall })} error={bad ? t('form.unitsRange') : undefined}>
            {(p) => <input {...p} type="number" inputMode="numeric" min={1} max={20} value={units} onChange={(e) => setUnits(Number(e.target.value))} className={`${inputCls} w-28 font-mono`} />}
          </Field>
          <div className="grid gap-2">
            <span className="text-sm font-medium text-zinc-800">{t('request.urgency')}</span>
            <Segmented label={t('request.urgency')} value={urgency} onChange={setUrgency} options={(['emergency', 'urgent', 'routine'] as Urgency[]).map((u) => ({ value: u, label: t(`urgency.${u}`) }))} />
          </div>
          {m.error && <p role="alert" className="text-sm text-red-700">{m.error instanceof ApiError ? t(`errors.${m.error.code}`, { defaultValue: m.error.message }) : t('errors.generic')}</p>}
        </div>
      )}
    </Dialog>
  )
}
