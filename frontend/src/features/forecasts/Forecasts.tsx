import { useParamState } from '../../lib/useParamState'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { forecast, listSites } from '../../api/client'
import type { Abo, Component as Comp, ForecastSeries, Rh } from '../../api/types'
import { PageHeader, QueryView, Segmented, inputCls, cx } from '../../components/ui'
import { COMPONENTS, GROUPS, groupLabel } from '../../lib/rules'
import { fmtNum, fmtPct } from '../../lib/format'
import { useSession } from '../../session'

export function Component() {
  const { t } = useTranslation()
  const { session } = useSession()
  const sites = useQuery({ queryKey: ['sites'], queryFn: listSites })
  const [siteId, setSiteId] = useParamState<string>('site', '')
  const [component, setComponent] = useParamState<Comp>('component', 'red_cells')
  const [group, setGroup] = useParamState<string>('group', 'Opos')
  // Leads default to their own site; region roles to the first hospital (banks have no demand to forecast).
  const site = siteId || (session?.role === 'hospital_lead' ? session.site_ids[0] : sites.data?.find((x) => x.type === 'hospital')?.id) || ''
  const abo = group.replace(/pos|neg/, '') as Abo
  const rh = (group.endsWith('neg') ? 'neg' : 'pos') as Rh
  const q = useQuery({ queryKey: ['forecast', site, component, group], queryFn: () => forecast(site, component, abo, rh), enabled: !!site })

  return (
    <div className="grid gap-6">
      <PageHeader title={t('forecast.title')} description={t('forecast.description')} />
      <div className="flex flex-wrap items-end gap-3">
        <label className="grid gap-1">
          <span className="text-xs font-medium text-zinc-500">{t('common.site')}</span>
          <select value={site} onChange={(e) => setSiteId(e.target.value)} className={`${inputCls} h-9 w-64`}>
            {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        <Segmented label={t('common.component')} value={component} onChange={setComponent} options={COMPONENTS.map((c) => ({ value: c, label: t(`component.${c}`) }))} />
        <Segmented size="sm" label={t('common.group')} value={group} onChange={setGroup} options={GROUPS.map(([a, r]) => ({ value: `${a}${r}`, label: <span className="font-semibold">{groupLabel(a, r)}</span> }))} />
      </div>
      <QueryView q={q} rows={8}>
        {(s) => (
          <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_300px]">
            <ForecastChart s={s} />
            <Accuracy s={s} />
          </div>
        )}
      </QueryView>
    </div>
  )
}

function ForecastChart({ s }: { s: ForecastSeries }) {
  const { t } = useTranslation()
  const today = s.points.find((p) => p.actual === undefined)?.day
  const data = s.points.map((p) => ({ ...p, band: [p.low, p.high], label: p.day.slice(5) }))
  return (
    <figure className="reveal rounded-2xl bg-white p-5 ring-1 ring-zinc-200">
      <figcaption className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-zinc-600">
        <span className="font-medium text-zinc-900 text-sm mr-auto">{t('forecast.chartTitle')}</span>
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-zinc-900" aria-hidden />{t('forecast.actual')}</span>
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 border-t-2 border-dashed border-brand" aria-hidden />{t('forecast.point')}</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-sm bg-brand/15" aria-hidden />{t('forecast.band')}</span>
      </figcaption>
      <div className="h-[340px]" role="img" aria-label={t('forecast.chartSr', { model: s.model })}>
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid stroke="#f4f4f5" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#71717a' }} tickLine={false} axisLine={{ stroke: '#e4e4e7' }} interval={4} />
            <YAxis tick={{ fontSize: 11, fill: '#71717a' }} tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip contentStyle={{ borderRadius: 10, border: '1px solid #e4e4e7', fontSize: 12 }}
              formatter={(v, name) => [Array.isArray(v) ? `${fmtNum(Number(v[0]), 1)} – ${fmtNum(Number(v[1]), 1)}` : fmtNum(Number(v), 1), t(`forecast.${String(name)}`)]} />
            <Area dataKey="band" name="band" stroke="none" fill="#8f1d2c" fillOpacity={0.12} isAnimationActive={false} />
            <Line dataKey="actual" name="actual" stroke="#18181b" strokeWidth={1.75} dot={false} isAnimationActive={false} connectNulls={false} />
            <Line dataKey="point" name="point" stroke="#8f1d2c" strokeWidth={1.75} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
            {today && <ReferenceLine x={today.slice(5)} stroke="#a1a1aa" strokeDasharray="2 3" label={{ value: t('forecast.today'), position: 'insideTopRight', fontSize: 11, fill: '#71717a' }} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}

function Accuracy({ s }: { s: ForecastSeries }) {
  const { t } = useTranslation()
  const better = s.mae < s.baseline_mae
  return (
    <aside className="reveal grid content-start gap-6" style={{ '--i': 2 } as React.CSSProperties} aria-labelledby="acc-h">
      <h2 id="acc-h" className="text-base font-semibold tracking-tight">{t('forecast.accuracyTitle')}</h2>
      <dl className="grid gap-5 divide-y divide-zinc-200 border-y border-zinc-200">
        <div className="pt-4">
          <dt className="text-xs font-medium uppercase tracking-wider text-zinc-500">{t('forecast.model')}</dt>
          <dd className="mt-1 font-mono text-sm text-zinc-900">{t(`forecast.models.${s.model}`)}</dd>
          <dd className="font-mono text-xs text-zinc-500">v{s.model_version}</dd>
        </div>
        <div className="pt-4">
          <dt className="text-xs font-medium uppercase tracking-wider text-zinc-500">{t('forecast.mae')}</dt>
          <dd className="mt-1 font-mono text-2xl tabular-nums text-zinc-950">{fmtNum(s.mae, 2)}</dd>
          <dd className={cx('text-sm', better ? 'text-emerald-700' : 'text-amber-800')}>{t('forecast.vsBaseline', { value: fmtNum(s.baseline_mae, 2) })}</dd>
        </div>
        <div className="py-4">
          <dt className="text-xs font-medium uppercase tracking-wider text-zinc-500">{t('forecast.coverage')}</dt>
          <dd className="mt-1 font-mono text-2xl tabular-nums text-zinc-950">{s.coverage == null ? '—' : fmtPct(s.coverage)}</dd>
          <dd className="text-sm text-zinc-500">{t('forecast.coverageTarget')}</dd>
        </div>
      </dl>
      <p className="text-xs leading-relaxed text-zinc-500">{t('forecast.note')}</p>
    </aside>
  )
}
