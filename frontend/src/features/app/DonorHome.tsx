import { Link, Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, CalendarCheck, HourglassMedium } from '@phosphor-icons/react'
import { ApiError, eligibleAgain, getDonorProfile, listInvitations, updateDonorProfile } from '../../api/client'
import type { Availability, Donor } from '../../api/types'
import { GroupChip, QueryView, Segmented, inputCls, cx } from '../../components/ui'
import { groupLabel } from '../../lib/rules'
import { fmtDate } from '../../lib/format'

export function Component() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['donorProfile'], queryFn: getDonorProfile })
  const inv = useQuery({ queryKey: ['invitations'], queryFn: listInvitations })
  const m = useMutation({ mutationFn: (patch: Partial<Donor>) => updateDonorProfile(patch), onSuccess: (d) => qc.setQueryData(['donorProfile'], d) })
  const openInv = inv.data?.filter((i) => i.status === 'invited').length ?? 0
  if (q.error instanceof ApiError && q.error.code === 'not_registered') return <Navigate to="/app/register" replace />

  return (
    <QueryView q={q} rows={5}>
      {(d) => {
        const next = eligibleAgain(d)
        const ok = next <= Date.now()
        const days = Math.ceil((next - Date.now()) / 86_400_000)
        return (
          <div className="grid gap-8">
            <section aria-labelledby="elig-h" className={cx('reveal relative overflow-hidden rounded-3xl p-6', ok ? 'bg-zinc-950 text-white' : 'bg-white ring-1 ring-zinc-200')}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className={cx('text-xs font-medium uppercase tracking-wider', ok ? 'text-zinc-400' : 'text-zinc-500')}>{t('donorHome.status')}</p>
                  <h1 id="elig-h" className="mt-2 text-2xl font-semibold tracking-tight text-balance">{ok ? t('donorHome.eligible') : t('donorHome.notYet', { count: days })}</h1>
                  <p className={cx('mt-2 text-sm', ok ? 'text-zinc-300' : 'text-zinc-600')}>
                    {ok ? t('donorHome.eligibleBody') : t('donorHome.nextDate', { date: fmtDate(new Date(next).toISOString()) })}
                  </p>
                </div>
                <span className={cx('grid size-14 shrink-0 place-items-center rounded-2xl', ok ? 'bg-brand' : 'bg-zinc-100 text-zinc-600')}>
                  {ok ? <CalendarCheck size={28} weight="fill" aria-hidden /> : <HourglassMedium size={28} aria-hidden />}
                </span>
              </div>
              <dl className={cx('mt-6 grid grid-cols-2 gap-4 border-t pt-4 text-sm', ok ? 'border-white/10' : 'border-zinc-200')}>
                <div>
                  <dt className={ok ? 'text-zinc-400' : 'text-zinc-500'}>{t('common.group')}</dt>
                  <dd className="mt-1 flex items-center gap-2"><GroupChip label={groupLabel(d.abo, d.rh)} verified={ok ? undefined : d.group_verified} /><span className="text-xs">{d.group_verified ? t('donors.verified') : t('donors.selfReported')}</span></dd>
                </div>
                <div>
                  <dt className={ok ? 'text-zinc-400' : 'text-zinc-500'}>{t('donors.lastDonation')}</dt>
                  <dd className="mt-1 tabular-nums">{d.last_donation_on ? fmtDate(d.last_donation_on) : t('donors.never')}</dd>
                </div>
              </dl>
            </section>

            {openInv > 0 && (
              <Link to="/app/invitations" className="reveal flex items-center gap-3 rounded-2xl bg-brand-soft p-4 ring-1 ring-brand/20 focus-visible:outline-2 focus-visible:outline-brand" style={{ '--i': 1 } as React.CSSProperties}>
                <span className="live-dot size-2.5 rounded-full bg-brand" aria-hidden />
                <span className="flex-1 text-sm font-medium text-brand">{t('donorHome.invitations', { count: openInv })}</span>
                <ArrowRight size={18} className="text-brand" aria-hidden />
              </Link>
            )}

            <section aria-labelledby="avail-h" className="reveal grid gap-4" style={{ '--i': 2 } as React.CSSProperties}>
              <div>
                <h2 id="avail-h" className="text-base font-semibold tracking-tight">{t('donorHome.availability')}</h2>
                <p className="mt-1 text-sm text-zinc-600">{t('donorHome.availabilityBody')}</p>
              </div>
              <Segmented label={t('donorHome.availability')} value={d.availability} onChange={(v: Availability) => m.mutate({ availability: v })}
                options={(['available', 'unavailable', 'travelling'] as Availability[]).map((v) => ({ value: v, label: t(`availability.${v}`) }))} />
            </section>

            <section aria-labelledby="quiet-h" className="reveal grid gap-4" style={{ '--i': 3 } as React.CSSProperties}>
              <div>
                <h2 id="quiet-h" className="text-base font-semibold tracking-tight">{t('donorHome.quiet')}</h2>
                <p className="mt-1 text-sm text-zinc-600">{t('donorHome.quietBody')}</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <label className="grid gap-2 text-sm font-medium text-zinc-800">{t('donorHome.from')}
                  <input type="time" value={d.quiet_start ?? ''} onChange={(e) => m.mutate({ quiet_start: e.target.value || null })} className={inputCls} />
                </label>
                <label className="grid gap-2 text-sm font-medium text-zinc-800">{t('donorHome.to')}
                  <input type="time" value={d.quiet_end ?? ''} onChange={(e) => m.mutate({ quiet_end: e.target.value || null })} className={inputCls} />
                </label>
              </div>
              <label className="flex items-start gap-3 text-sm text-zinc-800">
                <input type="checkbox" checked={d.emergency_override} onChange={(e) => m.mutate({ emergency_override: e.target.checked })} className="mt-0.5 size-5 accent-brand" />
                <span>{t('donorHome.override')}</span>
              </label>
              <label className="flex items-center justify-between gap-3 text-sm font-medium text-zinc-800">
                {t('donorHome.maxInvites')}
                <select value={d.max_invites_30d} onChange={(e) => m.mutate({ max_invites_30d: Number(e.target.value) })} className={`${inputCls} w-20`}>
                  {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
              <p className="h-5 text-xs text-zinc-500" aria-live="polite">{m.isPending ? t('common.saving') : m.isSuccess ? t('common.saved') : ''}</p>
            </section>
          </div>
        )
      }}
    </QueryView>
  )
}
