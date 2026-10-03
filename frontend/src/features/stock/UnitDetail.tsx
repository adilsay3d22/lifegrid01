import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from '@phosphor-icons/react'
import { getUnit, listSites } from '../../api/client'
import { GroupChip, PageHeader, QueryView } from '../../components/ui'
import { ExpiryCell, UnitStatusBadge } from '../../components/status'
import { groupLabel } from '../../lib/rules'
import { fmtDateTime } from '../../lib/format'

export function Component() {
  const { id = '' } = useParams()
  const { t } = useTranslation()
  const q = useQuery({ queryKey: ['unit', id], queryFn: () => getUnit(id) })
  const sites = useQuery({ queryKey: ['sites'], queryFn: listSites })
  const siteName = (sid: string | null) => sites.data?.find((s) => s.id === sid)?.name ?? '—'

  return (
    <QueryView q={q} rows={8}>
      {({ unit: u, movements }) => (
        <div className="grid gap-8">
          <Link to={`/staff/sites/${u.site_id}/stock`} className="inline-flex w-fit items-center gap-1.5 text-sm text-zinc-600 hover:text-zinc-900"><ArrowLeft size={16} aria-hidden />{siteName(u.site_id)}</Link>
          <PageHeader eyebrow={t('unit.eyebrow')} title={<span className="font-mono">{u.unit_code}</span>} actions={<UnitStatusBadge s={u.status} />} />
          <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-5 content-start">
              <Item label={t('common.group')}><GroupChip label={groupLabel(u.abo, u.rh)} /></Item>
              <Item label={t('common.component')}>{t(`component.${u.component}`)}</Item>
              <Item label={t('stock.collectedAt')}>{fmtDateTime(u.collected_at)}</Item>
              <Item label={t('stock.expiresAt')}>{fmtDateTime(u.expires_at)}</Item>
              <Item label={t('stock.remaining')}><ExpiryCell at={u.expires_at} /></Item>
              <Item label={t('common.site')}>{siteName(u.site_id)}</Item>
            </dl>
            <section aria-labelledby="mv-h">
              <h2 id="mv-h" className="text-base font-semibold tracking-tight">{t('unit.movements')}</h2>
              <ol className="mt-4 border-l border-zinc-200 ml-1.5">
                {[...movements].reverse().map((m, i) => (
                  <li key={m.id} className="reveal relative pl-6 pb-6 last:pb-0" style={{ '--i': i } as React.CSSProperties}>
                    <span className={`absolute -left-[5px] top-1.5 size-2.5 rounded-full ring-4 ring-canvas ${i === 0 ? 'bg-brand' : 'bg-zinc-300'}`} aria-hidden />
                    <div className="flex flex-wrap items-center gap-2">
                      {m.from_status && <><UnitStatusBadge s={m.from_status} /><span className="text-zinc-500" aria-hidden>&rarr;</span></>}
                      <UnitStatusBadge s={m.to_status} />
                    </div>
                    <p className="mt-1.5 text-sm text-zinc-800">{m.reason}</p>
                    <p className="mt-0.5 text-xs text-zinc-500"><time dateTime={m.created_at}>{fmtDateTime(m.created_at)}</time> &middot; <span className="font-mono">{m.actor}</span></p>
                  </li>
                ))}
              </ol>
            </section>
          </div>
        </div>
      )}
    </QueryView>
  )
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><dt className="text-xs font-medium uppercase tracking-wider text-zinc-500">{label}</dt><dd className="mt-1.5 text-sm text-zinc-900">{children}</dd></div>
}
