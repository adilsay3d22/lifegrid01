import { useParamState } from '../../lib/useParamState'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ClipboardText, Plus } from '@phosphor-icons/react'
import { cancelRequest, confirmRequest, listRequests, listSites } from '../../api/client'
import type { BloodRequest } from '../../api/types'
import { Badge, Button, Dialog, EmptyState, GroupChip, PageHeader, QueryView, Segmented, cx } from '../../components/ui'
import { RequestStatusBadge, UrgencyBadge } from '../../components/status'
import { groupLabel } from '../../lib/rules'
import { fmtDateTime, fmtRelative } from '../../lib/format'
import { useSession } from '../../session'
import { RequestProgress } from './Progress'
import { RequestForm } from './RequestForm'
import { RequestMatches } from './Matches'
import { Link } from 'react-router-dom'

const OPEN = ['submitted', 'confirmed', 'covered_by_stock', 'matching']

export function Component() {
  const { t } = useTranslation()
  const { session } = useSession()
  const [view, setView] = useParamState<'open' | 'closed'>('view', 'open')
  const [selected, setSelected] = useState<BloodRequest | null>(null)
  const [creating, setCreating] = useState(false)
  const q = useQuery({ queryKey: ['requests'], queryFn: listRequests })
  const sites = useQuery({ queryKey: ['sites'], queryFn: listSites })
  const qc = useQueryClient()
  const site = (id: string) => sites.data?.find((s) => s.id === id)
  const toConfirm = q.data?.filter((r) => r.status === 'submitted') ?? []
  const list = q.data?.filter((r) => (view === 'open') === OPEN.includes(r.status) && r.status !== 'submitted') ?? []

  return (
    <div className="grid gap-8">
      <PageHeader title={t('requests.title')} description={t('requests.description')}
        actions={session?.role === 'hospital_lead' && <Button variant="primary" onClick={() => setCreating(true)}><Plus size={16} aria-hidden />{t('requests.new')}</Button>} />

      <QueryView q={q} rows={6} empty={<EmptyState icon={<ClipboardText size={20} />} title={t('requests.emptyTitle')} body={t('requests.emptyBody')} />}>
        {() => <>
          {toConfirm.length > 0 && (
            <section aria-labelledby="confirm-h" className="reveal">
              <h2 id="confirm-h" className="flex items-center gap-2 text-base font-semibold tracking-tight">
                <span className="live-dot size-2 rounded-full bg-amber-500" aria-hidden />{t('requests.toConfirm', { count: toConfirm.length })}
              </h2>
              <p className="mt-1 text-sm text-zinc-600">{t('requests.toConfirmBody')}</p>
              <ul className="mt-4 grid gap-3 md:grid-cols-2">
                {toConfirm.map((r) => (
                  <li key={r.id}>
                    <button type="button" onClick={() => setSelected(r)} className="group flex w-full items-center gap-4 rounded-2xl bg-white p-4 text-left ring-1 ring-amber-200 transition-shadow hover:shadow-[0_8px_24px_-12px_rgb(24_24_27/0.18)] focus-visible:outline-2 focus-visible:outline-brand">
                      <GroupChip label={groupLabel(r.abo, r.rh)} />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2"><span className="font-mono text-sm font-medium">{r.ref}</span><UrgencyBadge u={r.urgency} /></span>
                        <span className="mt-0.5 block truncate text-sm text-zinc-600">{t('requests.line', { count: r.units_needed, component: t(`component.${r.component}`), site: site(r.site_id)?.name })}</span>
                      </span>
                      <span className="text-right text-xs text-zinc-500">{t('requests.neededBy')}<br /><span className="font-medium text-zinc-800">{fmtRelative(r.needed_by)}</span></span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section aria-labelledby="list-h" className="grid gap-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 id="list-h" className="text-base font-semibold tracking-tight">{t('requests.all')}</h2>
              <Segmented size="sm" label={t('common.status')} value={view} onChange={setView} options={[{ value: 'open', label: t('requests.open') }, { value: 'closed', label: t('requests.closed') }]} />
            </div>
            {list.length === 0 ? <EmptyState title={t(`requests.empty_${view}`)} /> : (
              <ul className="divide-y divide-zinc-200 rounded-2xl bg-white ring-1 ring-zinc-200">
                {list.map((r, i) => (
                  <li key={r.id} className="reveal" style={{ '--i': i } as React.CSSProperties}>
                    <button type="button" onClick={() => setSelected(r)} className="grid w-full gap-3 p-4 text-left hover:bg-zinc-50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand md:grid-cols-[auto_minmax(0,1.4fr)_minmax(0,1fr)_auto] md:items-center md:px-5">
                      <GroupChip label={groupLabel(r.abo, r.rh)} />
                      <span className="min-w-0">
                        <span className="flex items-center gap-2"><span className="font-mono text-sm font-medium">{r.ref}</span><UrgencyBadge u={r.urgency} />{r.kind === 'appeal' && <Badge tone="brand">{t('requests.appeal')}</Badge>}</span>
                        <span className="mt-0.5 block truncate text-sm text-zinc-600">{site(r.site_id)?.name}</span>
                      </span>
                      <span className="flex items-center gap-2">
                        <span className="flex gap-0.5" aria-hidden>{Array.from({ length: r.units_needed }, (_, k) => <span key={k} className={cx('h-1.5 w-4 rounded-full', k < r.units_secured ? 'bg-brand' : 'bg-zinc-200')} />)}</span>
                        <span className="font-mono text-xs tabular-nums text-zinc-600">{t('requests.securedOf', { a: r.units_secured, b: r.units_needed })}</span>
                      </span>
                      <RequestStatusBadge s={r.status} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>}
      </QueryView>

      {selected && <RequestDialog r={q.data?.find((x) => x.id === selected.id) ?? selected} siteName={site(selected.site_id)?.name} onClose={() => setSelected(null)}
        canConfirm={session?.role === 'hospital_lead' && session.site_ids.includes(selected.site_id)} />}
      <Dialog open={creating} onClose={() => setCreating(false)} wide title={t('requests.new')} description={t('requests.newBody')}>
        {creating && <RequestForm siteIds={session?.site_ids} onCreated={() => { setCreating(false); qc.invalidateQueries({ queryKey: ['requests'] }) }} />}
      </Dialog>
    </div>
  )
}

function RequestDialog({ r, siteName, canConfirm, onClose }: { r: BloodRequest; siteName?: string; canConfirm: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const { session } = useSession()
  const role = session?.role
  const qc = useQueryClient()
  const done = () => qc.invalidateQueries({ queryKey: ['requests'] })
  const confirm = useMutation({ mutationFn: () => confirmRequest(r.id), onSuccess: done })
  const cancel = useMutation({ mutationFn: () => cancelRequest(r.id), onSuccess: () => { done(); onClose() } })
  const open = OPEN.includes(r.status)
  return (
    <Dialog open onClose={onClose} title={<span className="flex items-center gap-3"><span className="font-mono">{r.ref}</span><RequestStatusBadge s={r.status} /></span>}
      description={`${t('requests.line', { count: r.units_needed, component: t(`component.${r.component}`), site: siteName })} · ${t('requests.neededBy')} ${fmtDateTime(r.needed_by)}`}
      footer={<>
        {open && canConfirm && <Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate()}>{t('requests.cancel')}</Button>}
        {r.status === 'submitted' && canConfirm && <Button variant="primary" loading={confirm.isPending} onClick={() => confirm.mutate()}>{t('requests.confirm')}</Button>}
      </>}>
      <div className="flex items-center gap-3"><GroupChip label={groupLabel(r.abo, r.rh)} /><UrgencyBadge u={r.urgency} /></div>
      {r.status === 'submitted' && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-inset ring-amber-200">
          {canConfirm ? t('requests.confirmHint') : t('requests.otherSite')}
        </p>
      )}
      <RequestProgress r={r} />
      {r.escalated_at && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900 ring-1 ring-inset ring-red-200">{t('requests.escalated')}</p>}
      {r.transfer_plan_id && <Link to={`/staff/plans/${r.transfer_plan_id}`} className="text-sm font-medium text-brand underline underline-offset-4">{t('requests.reviewTransfers')}</Link>}
      <RequestMatches requestId={r.id} canRecord={canConfirm || role === 'donor_coordinator'} canMessage={r.requester_id === session?.user_id} />
      {confirm.data && <p role="status" className="text-sm text-emerald-800">{t(confirm.data.status === 'covered_by_stock' ? 'requests.coveredMsg' : 'requests.matchingMsg')}</p>}
    </Dialog>
  )
}
