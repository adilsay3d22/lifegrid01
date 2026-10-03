import { useDeferredValue, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery } from '@tanstack/react-query'
import { MagnifyingGlass, ShieldCheck, ShieldWarning } from '@phosphor-icons/react'
import { listAudit, verifyAudit } from '../../api/client'
import { Button, EmptyState, PageHeader, QueryView, inputCls, tdCls, thCls } from '../../components/ui'
import { fmtDateTime, fmtNum } from '../../lib/format'

export function Component() {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const q = useDeferredValue(search)
  const events = useQuery({ queryKey: ['audit', q], queryFn: () => listAudit(q) })
  const verify = useMutation({ mutationFn: verifyAudit })

  return (
    <div className="grid gap-6">
      <PageHeader title={t('audit.title')} description={t('audit.description')}
        actions={<Button variant="primary" loading={verify.isPending} onClick={() => verify.mutate()}><ShieldCheck size={16} aria-hidden />{t('audit.verify')}</Button>} />

      <div aria-live="polite">
        {verify.data && (verify.data.ok ? (
          <p className="reveal flex items-center gap-3 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-900 ring-1 ring-inset ring-emerald-200">
            <ShieldCheck size={20} weight="fill" aria-hidden />{t('audit.ok', { count: verify.data.checked })}
          </p>
        ) : (
          <p role="alert" className="reveal flex items-center gap-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-900 ring-1 ring-inset ring-red-200">
            <ShieldWarning size={20} weight="fill" aria-hidden />{t('audit.broken', { id: verify.data.broken_at })}
          </p>
        ))}
      </div>

      <label className="relative grid w-full max-w-sm gap-1">
        <span className="text-xs font-medium text-zinc-500">{t('audit.search')}</span>
        <MagnifyingGlass size={16} className="pointer-events-none absolute bottom-2.5 left-3 text-zinc-500" aria-hidden />
        <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('audit.searchPh')} autoComplete="off" className={`${inputCls} h-9 pl-9`} />
      </label>

      <QueryView q={events} rows={10} empty={<EmptyState title={t('audit.empty')} />}>
        {(rows) => (
          <div tabIndex={0} className="overflow-x-auto rounded-2xl focus-visible:outline-2 focus-visible:outline-brand bg-white ring-1 ring-zinc-200">
            <table className="w-full min-w-[820px] text-sm">
              <caption className="sr-only">{t('audit.title')}</caption>
              <thead className="border-b border-zinc-200"><tr>
                <th scope="col" className={`${thCls} pl-5 text-right`}>#</th><th scope="col" className={thCls}>{t('audit.when')}</th><th scope="col" className={thCls}>{t('audit.action')}</th>
                <th scope="col" className={thCls}>{t('audit.entity')}</th><th scope="col" className={thCls}>{t('audit.actor')}</th><th scope="col" className={`${thCls} pr-5`}>{t('audit.hash')}</th>
              </tr></thead>
              <tbody className="divide-y divide-zinc-100">
                {rows.map((e) => (
                  <tr key={e.id} className="hover:bg-zinc-50">
                    <td className={`${tdCls} pl-5 text-right font-mono text-xs tabular-nums text-zinc-500`}>{fmtNum(e.id)}</td>
                    <td className={`${tdCls} whitespace-nowrap text-xs tabular-nums text-zinc-600`}>{fmtDateTime(e.created_at)}</td>
                    <td className={`${tdCls} font-mono text-xs`}>{e.action}</td>
                    <td className={`${tdCls} text-xs`}><span className="text-zinc-500">{e.entity_type}</span> <span className="font-mono">{e.entity_id}</span></td>
                    <td className={`${tdCls} max-w-[16rem] truncate font-mono text-xs text-zinc-600`}>{e.actor}</td>
                    <td className={`${tdCls} pr-5 font-mono text-xs text-zinc-500`}>{e.hash}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </QueryView>
    </div>
  )
}
