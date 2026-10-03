import { useParamState } from '../../lib/useParamState'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { DownloadSimple } from '@phosphor-icons/react'
import { report, type ReportName } from '../../api/client'
import { Button, PageHeader, QueryView, Segmented, tdCls, thCls } from '../../components/ui'
import { downloadFile, toCsv } from '../../lib/format'

const CHART: Partial<Record<ReportName, { x: string; bars: [string, string][] }>> = {
  stock: { x: 'site', bars: [['available', '#3f3f46'], ['reserved', '#0369a1'], ['quarantined', '#b45309']] },
  wastage: { x: 'site', bars: [['expired', '#b91c1c'], ['discarded', '#a1a1aa']] },
}

export function Component() {
  const { t } = useTranslation()
  const [name, setName] = useParamState<ReportName>('report', 'wastage')
  const q = useQuery({ queryKey: ['report', name], queryFn: () => report(name) })
  const chart = CHART[name]

  return (
    <div className="grid gap-6">
      <PageHeader title={t('reports.title')} description={t('reports.description')}
        actions={<Button variant="primary" disabled={!q.data?.length} onClick={() => downloadFile(`lifegrid-${name}-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(q.data!), 'text/csv')}>
          <DownloadSimple size={16} aria-hidden />{t('reports.export')}
        </Button>} />
      <Segmented label={t('reports.which')} value={name} onChange={setName} options={(['wastage', 'stock', 'transfers', 'requests'] as ReportName[]).map((n) => ({ value: n, label: t(`reports.name.${n}`) }))} />
      <QueryView q={q} rows={8}>
        {(rows) => (
          <div className="grid gap-6">
            {chart && (
              <figure className="reveal rounded-2xl bg-white p-5 ring-1 ring-zinc-200">
                <figcaption className="mb-3 flex flex-wrap gap-4 text-xs text-zinc-600">
                  {chart.bars.map(([k, c]) => <span key={k} className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: c }} aria-hidden />{t(`reports.col.${k}`)}</span>)}
                </figcaption>
                <div className="h-64" role="img" aria-label={t('reports.chartSr', { name: t(`reports.name.${name}`) })}>
                  <ResponsiveContainer>
                    <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                      <CartesianGrid stroke="#f4f4f5" vertical={false} />
                      <XAxis dataKey={chart.x} tick={{ fontSize: 10, fill: '#71717a' }} tickLine={false} axisLine={{ stroke: '#e4e4e7' }} interval={0} />
                      <YAxis tick={{ fontSize: 11, fill: '#71717a' }} tickLine={false} axisLine={false} />
                      <Tooltip cursor={{ fill: '#f4f4f5' }} contentStyle={{ borderRadius: 10, border: '1px solid #e4e4e7', fontSize: 12 }} formatter={(v, k) => [v, t(`reports.col.${String(k)}`)]} />
                      {chart.bars.map(([k, c]) => <Bar key={k} dataKey={k} stackId="a" fill={c} isAnimationActive={false} />)}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </figure>
            )}
            <div tabIndex={0} className="overflow-x-auto rounded-2xl focus-visible:outline-2 focus-visible:outline-brand bg-white ring-1 ring-zinc-200">
              <table className="w-full text-sm">
                <caption className="sr-only">{t(`reports.name.${name}`)}</caption>
                <thead className="border-b border-zinc-200"><tr>{Object.keys(rows[0] ?? {}).map((k) => <th key={k} scope="col" className={thCls}>{t(`reports.col.${k}`)}</th>)}</tr></thead>
                <tbody className="divide-y divide-zinc-100">
                  {rows.map((r, i) => (
                    <tr key={i} className="hover:bg-zinc-50">
                      {Object.entries(r).map(([k, v]) => <td key={k} className={`${tdCls} ${typeof v === 'number' ? 'font-mono tabular-nums' : ''}`}>{k === 'status' || k === 'urgency' ? t(`reports.val.${v}`) : v}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </QueryView>
    </div>
  )
}
