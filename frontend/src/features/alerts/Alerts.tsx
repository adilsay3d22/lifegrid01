import { useParamState } from '../../lib/useParamState'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BellSlash, Thermometer, HourglassMedium, TrendDown, UserCircleMinus, type Icon } from '@phosphor-icons/react'
import { listAlerts, listSites, setAlertStatus } from '../../api/client'
import type { Alert } from '../../api/types'
import { Button, EmptyState, PageHeader, QueryView, Segmented, cx } from '../../components/ui'
import { SeverityBadge } from '../../components/status'
import { fmtDateTime, fmtRelative } from '../../lib/format'
import { useSession } from '../../session'
import { alertText } from './alertText'

const ICON: Record<Alert['type'], Icon> = { expiry: HourglassMedium, stockout: TrendDown, temperature: Thermometer, unfilled_request: UserCircleMinus }
type View = Alert['status']

export function Component() {
  const { t } = useTranslation()
  const { session } = useSession()
  const [view, setView] = useParamState<View>('view', 'open')
  const q = useQuery({ queryKey: ['alerts'], queryFn: listAlerts })
  const sites = useQuery({ queryKey: ['sites'], queryFn: listSites })
  const qc = useQueryClient()
  const m = useMutation({ mutationFn: ({ id, s }: { id: string; s: 'acknowledged' | 'resolved' }) => setAlertStatus(id, s), onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }) })
  const visible = (a: Alert) => session?.role !== 'donor_coordinator' || a.type === 'unfilled_request'
  const readOnly = session?.role === 'auditor'
  const count = (v: View) => q.data?.filter((a) => a.status === v && visible(a)).length ?? 0

  return (
    <div className="grid gap-6">
      <PageHeader title={t('alerts.title')} description={t('alerts.description')} />
      <Segmented label={t('common.status')} value={view} onChange={setView}
        options={(['open', 'acknowledged', 'resolved'] as View[]).map((v) => ({ value: v, label: <>{t(`alerts.status.${v}`)} <span className="ml-1 font-mono text-xs text-zinc-500">{count(v)}</span></> }))} />
      <QueryView q={q} rows={6} isEmpty={(d) => !d.some((a) => a.status === view && visible(a))}
        empty={<EmptyState icon={<BellSlash size={20} />} title={t(view === 'open' ? 'alerts.emptyTitle' : 'alerts.emptyOther')} body={view === 'open' ? t('alerts.emptyBody') : undefined} />}>
        {(data) => (
          <ul className="divide-y divide-zinc-200 rounded-2xl bg-white ring-1 ring-zinc-200">
            {data.filter((a) => a.status === view && visible(a)).map((a, i) => {
              const I = ICON[a.type]
              const busy = m.isPending && m.variables?.id === a.id
              return (
                <li key={a.id} className="reveal grid gap-3 p-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-center md:px-5" style={{ '--i': i } as React.CSSProperties}>
                  <span className={cx('grid size-10 place-items-center rounded-xl', a.severity === 'critical' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-800')}><I size={20} aria-hidden /></span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2"><SeverityBadge s={a.severity} /><span className="text-xs text-zinc-500">{t(`alerts.type.${a.type}`)}</span></div>
                    <p className="mt-1 text-sm text-zinc-900">{alertText(t, a)}</p>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      {sites.data?.find((s) => s.id === a.site_id)?.name ?? t('alerts.network')} &middot; <time dateTime={a.created_at} title={fmtDateTime(a.created_at)}>{fmtRelative(a.created_at)}</time>
                      {a.acknowledged_by && <> &middot; {t('alerts.ackBy', { who: a.acknowledged_by, when: fmtDateTime(a.acknowledged_at!) })}</>}
                    </p>
                  </div>
                  {!readOnly && a.status !== 'resolved' && (
                    <div className="flex gap-2">
                      {a.status === 'open' && <Button size="sm" loading={busy && m.variables?.s === 'acknowledged'} onClick={() => m.mutate({ id: a.id, s: 'acknowledged' })}>{t('alerts.ack')}</Button>}
                      <Button size="sm" variant="ghost" loading={busy && m.variables?.s === 'resolved'} onClick={() => m.mutate({ id: a.id, s: 'resolved' })}>{t('alerts.resolve')}</Button>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </QueryView>
    </div>
  )
}
