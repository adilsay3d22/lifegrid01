import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cancelRequest, getRequest, listSites } from '../../api/client'
import { Button, Dialog, GroupChip, QueryView } from '../../components/ui'
import { RequestStatusBadge, UrgencyBadge } from '../../components/status'
import { groupLabel } from '../../lib/rules'
import { fmtDateTime } from '../../lib/format'
import { RequestProgress } from '../requests/Progress'

export function Component() {
  const { id = '' } = useParams()
  const { t } = useTranslation()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const q = useQuery({ queryKey: ['request', id], queryFn: () => getRequest(id), refetchInterval: 15_000 })
  const sites = useQuery({ queryKey: ['sites'], queryFn: listSites })
  const cancel = useMutation({ mutationFn: () => cancelRequest(id), onSuccess: () => { qc.invalidateQueries({ queryKey: ['requests'] }); nav('/app/requests') } })

  return (
    <QueryView q={q} rows={5}>
      {(r) => (
        <div className="grid gap-6">
          <header className="flex items-start gap-4">
            <GroupChip label={groupLabel(r.abo, r.rh)} />
            <div className="min-w-0 flex-1">
              <p className="font-mono text-xs text-zinc-500">{r.ref}</p>
              <h1 className="text-xl font-semibold tracking-tight">{t(`requestStatus.${r.status}`)}</h1>
              <p className="mt-1 text-sm text-zinc-600">{t(`requestStatus.explain.${r.status}`)}</p>
            </div>
          </header>
          <div className="flex flex-wrap gap-2"><RequestStatusBadge s={r.status} /><UrgencyBadge u={r.urgency} /></div>
          <div className="rounded-2xl bg-white p-5 ring-1 ring-zinc-200"><RequestProgress r={r} /></div>
          {!!r.accepted_matches?.length && (
            <section aria-labelledby="donors-h" className="grid gap-2">
              <h2 id="donors-h" className="text-base font-semibold tracking-tight">{t('requestStatus.donorsTitle')}</h2>
              <ul className="grid gap-2">
                {r.accepted_matches.map((m, i) => (
                  <li key={m.id}>
                    <Link to={`/app/matches/${m.id}`} className="flex h-12 items-center justify-between rounded-xl bg-white px-4 text-sm font-medium ring-1 ring-zinc-200 hover:bg-zinc-50 focus-visible:outline-2 focus-visible:outline-brand">
                      <span>{t('requestStatus.donorN', { n: i + 1 })} · {t(`matchStatus.${m.status}`)}</span><span aria-hidden>&rarr;</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <dl className="grid gap-3 text-sm">
            <div className="flex justify-between gap-4"><dt className="text-zinc-500">{t('request.hospital')}</dt><dd className="text-right text-zinc-900">{sites.data?.find((s) => s.id === r.site_id)?.name}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-zinc-500">{t('common.component')}</dt><dd>{t(`component.${r.component}`)}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-zinc-500">{t('request.neededBy')}</dt><dd className="tabular-nums">{fmtDateTime(r.needed_by)}</dd></div>
          </dl>
          {['submitted', 'confirmed', 'covered_by_stock', 'matching'].includes(r.status) && (
            <Button variant="danger" onClick={() => setConfirming(true)}>{t('requests.cancel')}</Button>
          )}
          <Dialog open={confirming} onClose={() => setConfirming(false)} title={t('myRequests.cancelTitle')} description={t('myRequests.cancelBody')}
            footer={<><Button variant="ghost" onClick={() => setConfirming(false)}>{t('common.back')}</Button><Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate()}>{t('requests.cancel')}</Button></>} />
        </div>
      )}
    </QueryView>
  )
}
