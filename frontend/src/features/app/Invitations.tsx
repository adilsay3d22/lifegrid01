import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChatCircleText, EnvelopeSimpleOpen, MapPin } from '@phosphor-icons/react'
import { listInvitations, respondInvitation } from '../../api/client'
import type { Invitation } from '../../api/types'
import { Badge, Button, EmptyState, QueryView, cx } from '../../components/ui'
import { UrgencyBadge } from '../../components/status'
import { groupLabel } from '../../lib/rules'
import { fmtRelative } from '../../lib/format'

/** FR-MAT-03: only group needed, hospital area and urgency. No requester name or phone. */
export function Component() {
  const { t } = useTranslation()
  const q = useQuery({ queryKey: ['invitations'], queryFn: listInvitations })
  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t('invitations.title')}</h1>
        <p className="mt-1 text-sm text-zinc-600">{t('invitations.body')}</p>
      </header>
      <QueryView q={q} rows={3} empty={<EmptyState icon={<EnvelopeSimpleOpen size={20} />} title={t('invitations.emptyTitle')} body={t('invitations.emptyBody')} />}>
        {(list) => <ul className="grid gap-4">{list.map((inv, i) => <Card key={inv.id} inv={inv} i={i} />)}</ul>}
      </QueryView>
    </div>
  )
}

function Card({ inv, i }: { inv: Invitation; i: number }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const m = useMutation({ mutationFn: (accept: boolean) => respondInvitation(inv.id, accept), onSuccess: () => qc.invalidateQueries({ queryKey: ['invitations'] }) })
  const open = inv.status === 'invited'
  return (
    <li className={cx('reveal rounded-3xl bg-white p-5 ring-1', inv.urgency === 'emergency' && open ? 'ring-red-300' : 'ring-zinc-200')} style={{ '--i': i } as React.CSSProperties}>
      <div className="flex items-start gap-4">
        <span className="grid size-16 shrink-0 place-items-center rounded-2xl bg-zinc-950 text-xl font-semibold text-white">{groupLabel(inv.abo, inv.rh)}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><UrgencyBadge u={inv.urgency} />{inv.kind === 'appeal' && <Badge tone="brand">{t('invitations.appeal')}</Badge>}{!open && <Badge tone={inv.status === 'accepted' ? 'good' : 'neutral'}>{t(`matchStatus.${inv.status}`)}</Badge>}</div>
          <p className="mt-2 flex items-center gap-1.5 text-sm text-zinc-800"><MapPin size={16} className="text-zinc-500" aria-hidden />{t('invitations.area', { area: inv.hospital_area })}</p>
          <p className="mt-0.5 text-sm text-zinc-500">{t('invitations.neededBy', { when: fmtRelative(inv.needed_by) })}</p>
        </div>
      </div>
      {open ? (
        <div className="mt-5 grid grid-cols-2 gap-3">
          <Button size="lg" loading={m.isPending && m.variables === false} onClick={() => m.mutate(false)}>{t('invitations.decline')}</Button>
          <Button size="lg" variant="primary" loading={m.isPending && m.variables === true} onClick={() => m.mutate(true)}>{t('invitations.accept')}</Button>
        </div>
      ) : inv.status === 'accepted' && (
        <Link to={`/app/matches/${inv.id}`} className="mt-5 flex h-12 items-center justify-center gap-2 rounded-lg bg-zinc-100 text-sm font-medium text-zinc-900 hover:bg-zinc-200 focus-visible:outline-2 focus-visible:outline-brand">
          <ChatCircleText size={18} aria-hidden />{t('invitations.openChat')}
        </Link>
      )}
    </li>
  )
}
