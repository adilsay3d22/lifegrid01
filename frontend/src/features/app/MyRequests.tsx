import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { ClipboardText, Plus, CaretRight } from '@phosphor-icons/react'
import { listRequests } from '../../api/client'
import { EmptyState, GroupChip, QueryView } from '../../components/ui'
import { RequestStatusBadge } from '../../components/status'
import { groupLabel } from '../../lib/rules'
import { fmtRelative } from '../../lib/format'

export function Component() {
  const { t } = useTranslation()
  const q = useQuery({ queryKey: ['requests'], queryFn: listRequests })
  const newLink = (
    <Link to="/app/requests/new" className="inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-brand px-5 font-medium text-white hover:bg-brand-strong active:scale-[0.98] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand">
      <Plus size={18} aria-hidden />{t('appNav.newRequest')}
    </Link>
  )
  return (
    <div className="grid gap-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t('myRequests.title')}</h1>
          <p className="mt-1 text-sm text-zinc-600">{t('myRequests.body')}</p>
        </div>
      </header>
      <QueryView q={q} rows={3} empty={<EmptyState icon={<ClipboardText size={20} />} title={t('myRequests.emptyTitle')} body={t('myRequests.emptyBody')} action={newLink} />}>
        {(list) => (
          <>
            <ul className="divide-y divide-zinc-200 rounded-2xl bg-white ring-1 ring-zinc-200">
              {list.map((r) => (
                <li key={r.id}>
                  <Link to={`/app/requests/${r.id}`} className="flex items-center gap-4 p-4 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand">
                    <GroupChip label={groupLabel(r.abo, r.rh)} />
                    <span className="min-w-0 flex-1">
                      <span className="block font-mono text-sm font-medium">{r.ref}</span>
                      <span className="block text-xs text-zinc-500">{t('requests.securedOf', { a: r.units_secured, b: r.units_needed })} &middot; {fmtRelative(r.created_at)}</span>
                    </span>
                    <RequestStatusBadge s={r.status} />
                    <CaretRight size={16} className="text-zinc-500" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
            {newLink}
          </>
        )}
      </QueryView>
    </div>
  )
}
