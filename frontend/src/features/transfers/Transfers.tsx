import { useParamState } from '../../lib/useParamState'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Truck, Package } from '@phosphor-icons/react'
import { dispatchTransfer, listSites, listTransfers, previewPick, receiveTransfer } from '../../api/client'
import type { Transfer } from '../../api/types'
import { Badge, Button, Dialog, EmptyState, GroupChip, PageHeader, QueryView, Segmented, Skeleton, type Tone } from '../../components/ui'
import { ExpiryCell } from '../../components/status'
import { groupLabel } from '../../lib/rules'
import { fmtRelative } from '../../lib/format'
import { useSession } from '../../session'

type Tab = 'approved' | 'dispatched' | 'received'
const TONE: Record<Transfer['status'], Tone> = { approved: 'info', dispatched: 'brand', received: 'good', cancelled: 'neutral' }

export function Component() {
  const { t } = useTranslation()
  const { session } = useSession()
  const [tab, setTab] = useParamState<Tab>('tab', 'approved')
  const [active, setActive] = useState<{ tr: Transfer; kind: 'dispatch' | 'receive' } | null>(null)
  const q = useQuery({ queryKey: ['transfers'], queryFn: listTransfers })
  const sites = useQuery({ queryKey: ['sites'], queryFn: listSites })
  const name = (id: string) => sites.data?.find((s) => s.id === id)?.name ?? '—'
  const mine = (tr: Transfer) => session?.role === 'bank_manager' || session?.site_ids.includes(tr.from_site_id) || session?.site_ids.includes(tr.to_site_id)
  const canReceive = (tr: Transfer) => session?.role === 'hospital_lead' && session.site_ids.includes(tr.to_site_id)
  const count = (s: Tab) => q.data?.filter((x) => x.status === s && mine(x)).length ?? 0

  return (
    <div className="grid gap-6">
      <PageHeader title={t('transfers.title')} description={t('transfers.description')} />
      <Segmented label={t('common.status')} value={tab} onChange={setTab} options={(['approved', 'dispatched', 'received'] as Tab[]).map((s) => ({
        value: s, label: <>{t(`transfers.tab.${s}`)} <span className="ml-1 font-mono text-xs text-zinc-500">{count(s)}</span></>,
      }))} />
      <QueryView q={q} rows={5} isEmpty={(d) => !d.some((x) => x.status === tab && mine(x))}
        empty={<EmptyState icon={<Truck size={20} />} title={t(`transfers.empty.${tab}`)} body={t('transfers.emptyBody')} />}>
        {(data) => (
          <ul className="divide-y divide-zinc-200 rounded-2xl bg-white ring-1 ring-zinc-200">
            {data.filter((x) => x.status === tab && mine(x)).map((tr, i) => (
              <li key={tr.id} className="reveal grid gap-3 p-4 md:grid-cols-[minmax(0,1.8fr)_auto_minmax(0,1fr)_auto] md:items-center md:px-5" style={{ '--i': i } as React.CSSProperties}>
                <p className="flex min-w-0 flex-wrap items-center gap-2 text-sm font-medium">
                  <span className="truncate">{name(tr.from_site_id)}</span><ArrowRight size={14} className="text-zinc-500" aria-hidden /><span className="sr-only">{t('plan.to')}</span><span className="truncate">{name(tr.to_site_id)}</span>
                </p>
                <div className="flex items-center gap-3"><GroupChip label={groupLabel(tr.abo, tr.rh)} /><span className="font-mono text-sm tabular-nums">{t('plan.units', { count: tr.units })}</span></div>
                <div className="text-sm text-zinc-600">
                  <Badge tone={TONE[tr.status]} dot>{t(`transfers.status.${tr.status}`)}</Badge>
                  {tr.dispatched_at && <span className="ml-2 text-xs text-zinc-500">{fmtRelative(tr.received_at ?? tr.dispatched_at)}</span>}
                </div>
                <div className="md:text-right">
                  {tr.status === 'approved' && <Button size="sm" variant="primary" onClick={() => setActive({ tr, kind: 'dispatch' })}><Truck size={16} aria-hidden />{t('transfers.dispatch')}</Button>}
                  {tr.status === 'dispatched' && (canReceive(tr)
                    ? <Button size="sm" variant="primary" onClick={() => setActive({ tr, kind: 'receive' })}><Package size={16} aria-hidden />{t('transfers.receive')}</Button>
                    : <span className="text-xs text-zinc-500">{t('transfers.awaitingReceipt')}</span>)}
                </div>
              </li>
            ))}
          </ul>
        )}
      </QueryView>
      {active?.kind === 'dispatch' && <DispatchDialog tr={active.tr} onClose={() => setActive(null)} />}
      {active?.kind === 'receive' && <ReceiveDialog tr={active.tr} onClose={() => setActive(null)} />}
    </div>
  )
}

function DispatchDialog({ tr, onClose }: { tr: Transfer; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const pick = useQuery({ queryKey: ['pick', tr.id], queryFn: () => previewPick(tr.id), gcTime: 0 })
  const m = useMutation({
    mutationFn: () => dispatchTransfer(tr.id, pick.data!.map((u) => u.id)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['transfers'] }); qc.invalidateQueries({ queryKey: ['units'] }); onClose() },
  })
  const n = pick.data?.length ?? 0
  return (
    <Dialog open onClose={onClose} wide title={t('transfers.dispatchTitle', { count: n })} description={t('transfers.dispatchBody')}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="primary" disabled={!n} loading={m.isPending} onClick={() => m.mutate()}>{t('transfers.dispatchConfirm', { count: n })}</Button>
      </>}>
      {pick.isPending ? <Skeleton rows={4} /> : (
        <>
          {n < tr.units && <p role="alert" className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-inset ring-amber-200">{t('transfers.shortPick', { have: n, want: tr.units })}</p>}
          <ol className="divide-y divide-zinc-100 rounded-lg ring-1 ring-zinc-200">
            {pick.data?.map((u, i) => (
              <li key={u.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <span className="flex items-center gap-3"><span className="w-5 font-mono text-xs text-zinc-500">{i + 1}</span><span className="font-mono">{u.unit_code}</span></span>
                <ExpiryCell at={u.expires_at} />
              </li>
            ))}
          </ol>
        </>
      )}
      {m.error && <p role="alert" className="text-sm text-red-700">{(m.error as Error).message}</p>}
    </Dialog>
  )
}

function ReceiveDialog({ tr, onClose }: { tr: Transfer; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const m = useMutation({
    mutationFn: () => receiveTransfer(tr.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['transfers'] }); qc.invalidateQueries({ queryKey: ['units'] }); onClose() },
  })
  return (
    <Dialog open onClose={onClose} title={t('transfers.receiveTitle', { count: tr.unit_codes.length })} description={t('transfers.receiveBody')}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="primary" loading={m.isPending} onClick={() => m.mutate()}>{t('transfers.receiveConfirm', { count: tr.unit_codes.length })}</Button>
      </>}>
      <ul className="grid grid-cols-2 gap-1 rounded-lg bg-zinc-50 p-3 font-mono text-xs text-zinc-700">{tr.unit_codes.map((c) => <li key={c}>{c}</li>)}</ul>
    </Dialog>
  )
}
