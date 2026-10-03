import { useTranslation } from 'react-i18next'
import { Check } from '@phosphor-icons/react'
import type { BloodRequest } from '../../api/types'
import { cx } from '../../components/ui'

const ORDER = ['submitted', 'confirmed', 'sourcing', 'closed'] as const
const stepOf = (s: BloodRequest['status']) =>
  s === 'submitted' ? 0 : s === 'confirmed' ? 1 : s === 'covered_by_stock' || s === 'matching' ? 2 : 3

/** Units secured + what the network did so far (FR-REQ-05). */
export function RequestProgress({ r }: { r: BloodRequest }) {
  const { t } = useTranslation()
  const step = r.status === 'cancelled' ? -1 : stepOf(r.status)
  return (
    <div className="grid gap-5">
      <div>
        <div className="flex items-baseline justify-between text-sm">
          <span className="font-medium text-zinc-900">{t('request.secured')}</span>
          <span className="font-mono tabular-nums"><span className="text-zinc-950 font-medium">{r.units_secured}</span><span className="text-zinc-500"> / {r.units_needed}</span></span>
        </div>
        <div className="mt-2 grid gap-1" style={{ gridTemplateColumns: `repeat(${r.units_needed}, 1fr)` }} role="progressbar" aria-valuemin={0} aria-valuemax={r.units_needed} aria-valuenow={r.units_secured} aria-label={t('request.secured')}>
          {Array.from({ length: r.units_needed }, (_, i) => (
            <span key={i} className={cx('h-2 rounded-full transition-colors duration-500', i < r.units_secured ? 'bg-brand' : 'bg-zinc-200')} />
          ))}
        </div>
      </div>
      <dl className="grid grid-cols-3 divide-x divide-zinc-200 border-y border-zinc-200 text-center">
        {(['stock_units', 'donors_notified', 'donors_accepted'] as const).map((k) => (
          <div key={k} className="py-3">
            <dd className="font-mono text-xl tabular-nums text-zinc-950">{r.progress[k]}</dd>
            <dt className="mt-0.5 text-xs text-zinc-500">{t(`request.progress.${k}`)}</dt>
          </div>
        ))}
      </dl>
      {step >= 0 && (
        <ol className="grid grid-cols-4 gap-2" aria-label={t('request.stepsLabel')}>
          {ORDER.map((s, i) => (
            <li key={s} className="grid gap-1.5" aria-current={i === step ? 'step' : undefined}>
              <span className={cx('h-1 rounded-full', i <= step ? 'bg-zinc-900' : 'bg-zinc-200')} aria-hidden />
              <span className={cx('flex items-center gap-1 text-xs', i <= step ? 'text-zinc-900 font-medium' : 'text-zinc-500')}>
                {i < step && <Check size={12} weight="bold" aria-hidden />}{t(`request.steps.${s}`)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
