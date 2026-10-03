import { useParamState } from '../../lib/useParamState'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import { ArrowRight, ArrowsClockwise, CheckCircle } from '@phosphor-icons/react'
import { listAlerts, listSites, runPlan, stockSummary } from '../../api/client'
import type { Alert, Component as Comp, Site, StockCell } from '../../api/types'
import { Button, PageHeader, QueryView, Segmented, Stat, Skeleton, EmptyState, cx } from '../../components/ui'
import { SeverityBadge } from '../../components/status'
import { COMPONENTS, GROUPS, groupLabel } from '../../lib/rules'
import { fmtDate, fmtNum, fmtRelative } from '../../lib/format'
import { alertText } from '../alerts/alertText'
import { LowStockPanel } from './LowStockPanel'

const RISK_COLOR = { critical: '#b91c1c', warning: '#b45309', ok: '#047857' }

export function Component() {
  const { t } = useTranslation()
  const [component, setComponent] = useParamState<Comp>('component', 'red_cells')
  const sites = useQuery({ queryKey: ['sites'], queryFn: listSites })
  const stock = useQuery({ queryKey: ['stock', component], queryFn: () => stockSummary(component) })
  const alerts = useQuery({ queryKey: ['alerts'], queryFn: listAlerts })
  const plan = useMutation({ mutationFn: runPlan })

  const open = alerts.data?.filter((a) => a.status === 'open') ?? []
  const risk = (siteId: string): keyof typeof RISK_COLOR => {
    const a = open.filter((x) => x.site_id === siteId)
    return a.some((x) => x.severity === 'critical') ? 'critical' : a.length ? 'warning' : 'ok'
  }
  const cells = stock.data ?? []
  const sum = (f: (c: StockCell) => number) => cells.reduce((s, c) => s + f(c), 0)

  return (
    <div className="grid gap-8">
      <PageHeader
        eyebrow={fmtDate(new Date().toISOString())}
        title={t('overview.title')}
        description={t('overview.description')}
        actions={<>
          <Button onClick={() => plan.mutate()} loading={plan.isPending}>
            {plan.isSuccess ? <CheckCircle size={16} weight="fill" className="text-emerald-700" aria-hidden /> : <ArrowsClockwise size={16} aria-hidden />}
            {plan.isSuccess ? t('overview.planQueued') : t('overview.runPlan')}
          </Button>
          <Link to="/staff/plans" className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-4 text-sm font-medium text-white hover:bg-brand-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand">
            {t('overview.reviewPlan')}<ArrowRight size={16} aria-hidden />
          </Link>
        </>}
      />

      <LowStockPanel />

      <section aria-labelledby="kpi-h" className="reveal">
        <h2 id="kpi-h" className="sr-only">{t('overview.kpis')}</h2>
        <dl className="grid grid-cols-2 md:grid-cols-4 md:divide-x divide-zinc-200 border-b border-zinc-200">
          <Stat label={t('overview.available', { component: t(`component.${component}`) })} value={stock.isPending ? '—' : fmtNum(sum((c) => c.band_0_2 + c.band_3_7 + c.band_8))} sub={t('overview.acrossSites', { count: sites.data?.length ?? 0 })} />
          <Stat label={t('overview.expiring')} value={stock.isPending ? '—' : fmtNum(sum((c) => c.band_0_2))} sub={t('overview.expiringSub')} tone="bad" />
          <Stat label={t('overview.stockoutRisk')} value={alerts.isPending ? '—' : open.filter((a) => a.type === 'stockout').length} sub={t('overview.stockoutSub')} tone="warn" />
          <Stat label={t('overview.openAlerts')} value={alerts.isPending ? '—' : open.length} sub={t('overview.criticalCount', { count: open.filter((a) => a.severity === 'critical').length })} />
        </dl>
      </section>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
        <section aria-labelledby="map-h" className="reveal" style={{ '--i': 1 } as React.CSSProperties}>
          <div className="mb-3 flex items-baseline justify-between gap-4">
            <h2 id="map-h" className="text-base font-semibold tracking-tight">{t('overview.mapTitle')}</h2>
            <ul className="flex gap-4 text-xs text-zinc-600">
              {(['critical', 'warning', 'ok'] as const).map((k) => (
                <li key={k} className="flex items-center gap-1.5"><span className="size-2.5 rounded-full" style={{ background: RISK_COLOR[k] }} aria-hidden />{t(`overview.risk.${k}`)}</li>
              ))}
            </ul>
          </div>
          <div className="h-[420px] overflow-hidden rounded-2xl ring-1 ring-zinc-200 bg-zinc-100">
            {sites.data ? <SiteMap sites={sites.data} risk={risk} cells={cells} /> : <Skeleton rows={1} className="h-full [&>div]:h-full p-0" />}
          </div>
        </section>

        <section aria-labelledby="alerts-h" className="reveal" style={{ '--i': 2 } as React.CSSProperties}>
          <div className="mb-3 flex items-baseline justify-between">
            <h2 id="alerts-h" className="text-base font-semibold tracking-tight">{t('overview.alertsTitle')}</h2>
            <Link to="/staff/alerts" className="text-sm font-medium text-brand hover:underline underline-offset-4">{t('common.viewAll')}</Link>
          </div>
          <QueryView q={alerts} rows={5} isEmpty={(d) => !d.some((a) => a.status === 'open')} empty={<EmptyState title={t('alerts.emptyTitle')} body={t('alerts.emptyBody')} />}>
            {() => (
              <ul className="divide-y divide-zinc-200 border-y border-zinc-200">
                {open.slice(0, 6).map((a, i) => <AlertRow key={a.id} a={a} site={sites.data?.find((s) => s.id === a.site_id)} i={i} />)}
              </ul>
            )}
          </QueryView>
        </section>
      </div>

      <section aria-labelledby="matrix-h" className="reveal" style={{ '--i': 3 } as React.CSSProperties}>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 id="matrix-h" className="text-base font-semibold tracking-tight">{t('overview.matrixTitle')}</h2>
            <p className="mt-1 text-sm text-zinc-600">{t('overview.matrixBody')}</p>
          </div>
          <Segmented label={t('common.component')} value={component} onChange={setComponent} options={COMPONENTS.map((c) => ({ value: c, label: t(`component.${c}`) }))} />
        </div>
        <QueryView q={stock} rows={8}>
          {(data) => <StockMatrix sites={sites.data ?? []} cells={data} component={component} />}
        </QueryView>
        <BandLegend />
      </section>
    </div>
  )
}

function AlertRow({ a, site, i }: { a: Alert; site?: Site; i: number }) {
  const { t } = useTranslation()
  return (
    <li className="reveal flex items-start gap-3 py-3" style={{ '--i': i } as React.CSSProperties}>
      <SeverityBadge s={a.severity} />
      <div className="min-w-0 flex-1">
        <p className="text-sm text-zinc-900">{alertText(t, a)}</p>
        <p className="mt-0.5 text-xs text-zinc-500">{site?.name ?? t('alerts.network')} &middot; {fmtRelative(a.created_at)}</p>
      </div>
    </li>
  )
}

function SiteMap({ sites, risk, cells }: { sites: Site[]; risk: (id: string) => keyof typeof RISK_COLOR; cells: StockCell[] }) {
  const { t } = useTranslation()
  return (
    <MapContainer center={[23.77, 90.39]} zoom={11} scrollWheelZoom={false} className="h-full w-full" attributionControl>
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' />
      {sites.map((s) => {
        const r = risk(s.id)
        const total = cells.filter((c) => c.site_id === s.id).reduce((n, c) => n + c.band_0_2 + c.band_3_7 + c.band_8, 0)
        const soon = cells.filter((c) => c.site_id === s.id).reduce((n, c) => n + c.band_0_2, 0)
        return (
          <CircleMarker key={s.id} center={[s.lat, s.lng]} radius={s.type === 'blood_bank' ? 12 : 8}
            pathOptions={{ color: '#fff', weight: 2, fillColor: RISK_COLOR[r], fillOpacity: 0.95 }}>
            <Popup>
              <p className="!m-0 font-semibold">{s.name}</p>
              <p className="!m-0 mt-1 font-mono text-xs text-zinc-500">{s.code} &middot; {t(`siteType.${s.type}`)}</p>
              <p className="!m-0 mt-2 text-sm">{t('overview.popupStock', { total, soon })}</p>
              <Link to={`/staff/sites/${s.id}/stock`} className="mt-2 inline-block text-sm font-medium !text-brand">{t('overview.openStock')}</Link>
            </Popup>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}

function StockMatrix({ sites, cells, component }: { sites: Site[]; cells: StockCell[]; component: Comp }) {
  const { t } = useTranslation()
  const groups = component === 'plasma' ? GROUPS.filter(([, rh]) => rh === 'pos') : GROUPS
  const at = (siteId: string, abo: string, rh: string) => cells.filter((c) => c.site_id === siteId && c.abo === abo && (component === 'plasma' || c.rh === rh))
  const max = Math.max(1, ...sites.flatMap((s) => groups.map(([a, r]) => at(s.id, a, r).reduce((n, c) => n + c.band_0_2 + c.band_3_7 + c.band_8, 0))))
  return (
    <div tabIndex={0} className="overflow-x-auto rounded-2xl focus-visible:outline-2 focus-visible:outline-brand ring-1 ring-zinc-200 bg-white">
      <table className="w-full min-w-[760px] text-sm">
        <caption className="sr-only">{t('overview.matrixTitle')}</caption>
        <thead>
          <tr className="border-b border-zinc-200">
            <th scope="col" className="w-[30%] px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">{t('common.site')}</th>
            {groups.map(([a, r]) => <th key={a + r} scope="col" className="px-2 py-3 text-right text-xs font-semibold text-zinc-700">{component === 'plasma' ? a : groupLabel(a, r)}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100">
          {sites.map((s) => (
            <tr key={s.id} className="hover:bg-zinc-50/70">
              <th scope="row" className="px-4 py-2.5 text-left font-normal">
                <Link to={`/staff/sites/${s.id}/stock`} className="font-medium text-zinc-900 hover:text-brand focus-visible:outline-2 focus-visible:outline-brand rounded">{s.name}</Link>
                <span className="ml-2 font-mono text-xs text-zinc-500">{s.code}</span>
              </th>
              {groups.map(([a, r]) => {
                const cs = at(s.id, a, r)
                const b = [cs.reduce((n, c) => n + c.band_0_2, 0), cs.reduce((n, c) => n + c.band_3_7, 0), cs.reduce((n, c) => n + c.band_8, 0)]
                const total = b[0] + b[1] + b[2]
                return (
                  <td key={a + r} className="px-2 py-2.5 text-right">
                    <span className={cx('font-mono tabular-nums', total === 0 ? 'text-red-700 font-medium' : 'text-zinc-900')}>{total}</span>
                    <span className={cx('ml-auto mt-1 flex h-1 overflow-hidden rounded-full', total === 0 && 'invisible')} style={{ width: `${Math.max(8, (total / max) * 100)}%` }} aria-hidden>
                      <span className="bg-red-600" style={{ flex: b[0] }} /><span className="bg-amber-500" style={{ flex: b[1] }} /><span className="bg-zinc-400" style={{ flex: b[2] }} />
                    </span>
                    <span className="sr-only">{t('overview.bandsSr', { a: b[0], b: b[1], c: b[2] })}</span>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BandLegend() {
  const { t } = useTranslation()
  return (
    <ul className="mt-3 flex flex-wrap gap-4 text-xs text-zinc-600">
      {[['bg-red-600', 'band0_2'], ['bg-amber-500', 'band3_7'], ['bg-zinc-400', 'band8']].map(([c, k]) => (
        <li key={k} className="flex items-center gap-1.5"><span className={`h-1.5 w-4 rounded-full ${c}`} aria-hidden />{t(`stock.${k}`)}</li>
      ))}
    </ul>
  )
}
