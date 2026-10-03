import { useDeferredValue, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LockKey, MagnifyingGlass, SealCheck, UsersThree } from '@phosphor-icons/react'
import { addDeferral, eligibleAgain, listDonors, verifyGroup, type DonorFilter } from '../../api/client'
import type { Donor } from '../../api/types'
import { Badge, Button, Dialog, EmptyState, Field, GroupChip, PageHeader, QueryView, inputCls, tdCls, thCls } from '../../components/ui'
import { GROUPS, groupLabel } from '../../lib/rules'
import { LowStockPanel } from '../stock/LowStockPanel'
import { fmtDate } from '../../lib/format'

const CATEGORIES = ['low_haemoglobin', 'recent_travel', 'medication', 'recent_procedure', 'temporary_illness']
const PAGE = 50

export function Component() {
  const { t } = useTranslation()
  const [f, setF] = useState<DonorFilter>({ q: '', group: '', eligible: '' })
  const q = useDeferredValue(f.q)
  const [limit, setLimit] = useState(PAGE)
  const [deferring, setDeferring] = useState<Donor | null>(null)
  const donors = useQuery({ queryKey: ['donors', { ...f, q }], queryFn: () => listDonors({ ...f, q }) })
  const qc = useQueryClient()
  const verify = useMutation({ mutationFn: verifyGroup, onSuccess: () => qc.invalidateQueries({ queryKey: ['donors'] }) })

  return (
    <div className="grid gap-6">
      <PageHeader title={t('donors.title')} description={t('donors.description')}
        actions={<p className="flex items-center gap-2 rounded-lg bg-zinc-100 px-3 py-2 text-xs text-zinc-600"><LockKey size={14} aria-hidden />{t('donors.privacy')}</p>} />
      <LowStockPanel />
      <div className="flex flex-wrap items-end gap-3">
        <label className="relative grid gap-1">
          <span className="text-xs font-medium text-zinc-500">{t('donors.search')}</span>
          <MagnifyingGlass size={16} className="pointer-events-none absolute left-3 bottom-2.5 text-zinc-500" aria-hidden />
          <input type="search" value={f.q} onChange={(e) => { setF({ ...f, q: e.target.value }); setLimit(PAGE) }} placeholder={t('donors.searchPh')} autoComplete="off" className={`${inputCls} h-9 w-64 pl-9`} />
        </label>
        <label className="grid gap-1">
          <span className="text-xs font-medium text-zinc-500">{t('common.group')}</span>
          <select value={f.group} onChange={(e) => setF({ ...f, group: e.target.value })} className={`${inputCls} h-9 w-32`}>
            <option value="">{t('common.all')}</option>
            {GROUPS.map(([a, r]) => <option key={a + r} value={`${a}${r}`}>{groupLabel(a, r)}</option>)}
          </select>
        </label>
        <label className="grid gap-1">
          <span className="text-xs font-medium text-zinc-500">{t('donors.eligibility')}</span>
          <select value={f.eligible} onChange={(e) => setF({ ...f, eligible: e.target.value as DonorFilter['eligible'] })} className={`${inputCls} h-9 w-40`}>
            <option value="">{t('common.all')}</option><option value="yes">{t('donors.eligibleNow')}</option><option value="no">{t('donors.notYet')}</option>
          </select>
        </label>
        <p className="ml-auto pb-2 text-sm text-zinc-500" aria-live="polite">{donors.data && t('donors.count', { count: donors.data.length })}</p>
      </div>

      <QueryView q={donors} rows={10} empty={<EmptyState icon={<UsersThree size={20} />} title={t('donors.emptyTitle')} body={t('donors.emptyBody')} />}>
        {(data) => (
          <div tabIndex={0} className="overflow-x-auto rounded-2xl focus-visible:outline-2 focus-visible:outline-brand bg-white ring-1 ring-zinc-200">
            <table className="w-full min-w-[860px] text-sm">
              <caption className="sr-only">{t('donors.title')}</caption>
              <thead className="border-b border-zinc-200"><tr>
                <th scope="col" className={`${thCls} pl-5`}>{t('donors.ref')}</th>
                <th scope="col" className={thCls}>{t('common.group')}</th>
                <th scope="col" className={thCls}>{t('donors.area')}</th>
                <th scope="col" className={thCls}>{t('donors.lastDonation')}</th>
                <th scope="col" className={thCls}>{t('donors.eligibility')}</th>
                <th scope="col" className={thCls}>{t('donors.availability')}</th>
                <th scope="col" className={thCls}>{t('donors.reliability')}</th>
                <th scope="col" className={`${thCls} text-right pr-5`}><span className="sr-only">{t('common.actions')}</span></th>
              </tr></thead>
              <tbody className="divide-y divide-zinc-100">
                {data.slice(0, limit).map((d, i) => {
                  const next = eligibleAgain(d)
                  const ok = next <= Date.now()
                  return (
                    <tr key={d.id} className="reveal hover:bg-zinc-50" style={{ '--i': i } as React.CSSProperties}>
                      <td className={`${tdCls} pl-5 font-mono`}>{d.ref}</td>
                      <td className={tdCls}>
                        <span className="flex items-center gap-1.5">
                          <GroupChip label={groupLabel(d.abo, d.rh)} verified={d.group_verified} />
                          {d.group_verified ? <SealCheck size={16} weight="fill" className="text-emerald-700" aria-label={t('donors.verified')} /> : <span className="sr-only">{t('donors.selfReported')}</span>}
                        </span>
                      </td>
                      <td className={`${tdCls} text-zinc-700`}>{d.area_label}</td>
                      <td className={`${tdCls} tabular-nums text-zinc-700`}>{d.last_donation_on ? fmtDate(d.last_donation_on) : <span className="text-zinc-500">{t('donors.never')}</span>}</td>
                      <td className={tdCls}>
                        {d.deferral ? <Badge tone="warn">{t('donors.deferredUntil', { date: fmtDate(d.deferral.eligible_again_on) })}</Badge>
                          : ok ? <Badge tone="good" dot>{t('donors.eligibleNow')}</Badge>
                          : <span className="text-sm tabular-nums text-zinc-600">{t('donors.from', { date: fmtDate(new Date(next).toISOString()) })}</span>}
                      </td>
                      <td className={`${tdCls} text-zinc-700`}>{t(`availability.${d.availability}`)}</td>
                      <td className={tdCls}>
                        <span className="flex items-center gap-2">
                          <span className="h-1.5 w-14 overflow-hidden rounded-full bg-zinc-100" aria-hidden><span className="block h-full bg-zinc-700" style={{ width: `${d.reliability * 100}%` }} /></span>
                          <span className="font-mono text-xs tabular-nums text-zinc-600">{d.reliability.toFixed(2)}</span>
                        </span>
                      </td>
                      <td className={`${tdCls} pr-5`}>
                        <span className="flex justify-end gap-1">
                          {!d.group_verified && d.abo && <Button size="sm" variant="ghost" loading={verify.isPending && verify.variables === d.id} onClick={() => verify.mutate(d.id)}>{t('donors.verify')}</Button>}
                          <Button size="sm" variant="ghost" onClick={() => setDeferring(d)}>{t('donors.defer')}</Button>
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {data.length > limit && <div className="border-t border-zinc-200 p-3 text-center"><Button size="sm" variant="ghost" onClick={() => setLimit(limit + PAGE)}>{t('common.showMore', { count: Math.min(PAGE, data.length - limit) })}</Button></div>}
          </div>
        )}
      </QueryView>
      {deferring && <DeferralDialog d={deferring} onClose={() => setDeferring(null)} />}
    </div>
  )
}

function DeferralDialog({ d, onClose }: { d: Donor; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [category, setCategory] = useState(CATEGORIES[0])
  const [date, setDate] = useState('')
  const [touched, setTouched] = useState(false)
  const m = useMutation({ mutationFn: () => addDeferral(d.id, category, date), onSuccess: () => { qc.invalidateQueries({ queryKey: ['donors'] }); onClose() } })
  const bad = !date || Date.parse(date) <= Date.now()
  return (
    <Dialog open onClose={onClose} title={t('donors.deferTitle', { ref: d.ref })} description={t('donors.deferBody')}
      footer={<><Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button><Button variant="primary" loading={m.isPending} onClick={() => { setTouched(true); if (!bad) m.mutate() }}>{t('donors.saveDeferral')}</Button></>}>
      <Field label={t('donors.category')}>
        {(p) => <select {...p} value={category} onChange={(e) => setCategory(e.target.value)} className={inputCls}>{CATEGORIES.map((c) => <option key={c} value={c}>{t(`deferral.${c}`)}</option>)}</select>}
      </Field>
      <Field label={t('donors.eligibleAgain')} error={touched && bad ? t('form.futureDate') : undefined}>
        {(p) => <input {...p} type="date" value={date} onChange={(e) => setDate(e.target.value)} className={inputCls} />}
      </Field>
    </Dialog>
  )
}
