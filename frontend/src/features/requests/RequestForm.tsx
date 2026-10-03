import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery } from '@tanstack/react-query'
import { z } from 'zod'
import { ApiError, createRequest, listSites } from '../../api/client'
import type { Abo, BloodRequest, Rh } from '../../api/types'
import { Button, Field, inputCls, cx } from '../../components/ui'
import { COMPONENTS, GROUPS, groupLabel } from '../../lib/rules'

const schema = z.object({
  group: z.string().min(2, 'form.required'),
  component: z.enum(['red_cells', 'platelets', 'plasma']),
  units_needed: z.coerce.number<number>().int('form.unitsRange').min(1, 'form.unitsRange').max(20, 'form.unitsRange'),
  site_id: z.string().min(1, 'form.hospitalRequired'),
  urgency: z.enum(['emergency', 'urgent', 'routine']),
  needed_by: z.string().min(1, 'form.neededByRequired').refine((v) => Date.parse(v) > Date.now(), 'form.neededByFuture'),
})
type Values = z.infer<typeof schema>

/** FR-REQ-01. Hospital and needed-by are required; the server returns 422 without them. */
export function RequestForm({ onCreated, siteIds, compact }: { onCreated: (r: BloodRequest) => void; siteIds?: string[]; compact?: boolean }) {
  const { t } = useTranslation()
  const sites = useQuery({ queryKey: ['sites'], queryFn: listSites })
  const hospitals = sites.data?.filter((s) => s.type === 'hospital' && (!siteIds?.length || siteIds.includes(s.id))) ?? []
  const { register, handleSubmit, watch, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { group: '', component: 'red_cells', units_needed: 1, site_id: siteIds?.length === 1 ? siteIds[0] : '', urgency: 'urgent', needed_by: '' },
  })
  const m = useMutation({
    mutationFn: (v: Values) => createRequest({
      abo: v.group.replace(/pos|neg/, '') as Abo, rh: (v.group.endsWith('neg') ? 'neg' : 'pos') as Rh,
      component: v.component, units_needed: v.units_needed, site_id: v.site_id, urgency: v.urgency, needed_by: v.needed_by,
    }),
    onSuccess: onCreated,
  })
  const err = (k: keyof Values) => errors[k] && t(errors[k]!.message!)
  const group = watch('group')
  const urgency = watch('urgency')

  return (
    <form onSubmit={handleSubmit((v) => m.mutate(v))} noValidate className={cx('grid gap-5', !compact && 'sm:grid-cols-2')}>
      <fieldset className={cx('grid gap-2', !compact && 'sm:col-span-2')} aria-describedby={errors.group ? 'grp-err' : undefined}>
        <legend className="mb-2 text-sm font-medium text-zinc-800">{t('request.patientGroup')}</legend>
        <div className="grid grid-cols-4 gap-2">
          {GROUPS.map(([a, r]) => {
            const v = `${a}${r}`
            return (
              <label key={v} className={cx('flex h-12 cursor-pointer items-center justify-center rounded-lg text-base font-semibold ring-1 ring-inset transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand active:scale-[0.98]',
                group === v ? 'bg-zinc-900 text-white ring-zinc-900' : 'bg-white text-zinc-800 ring-zinc-300 hover:bg-zinc-50')}>
                <input type="radio" value={v} {...register('group')} className="sr-only" />{groupLabel(a, r)}
              </label>
            )
          })}
        </div>
        {errors.group && <p id="grp-err" className="text-sm text-red-700">{t(errors.group.message!)}</p>}
      </fieldset>
      <Field label={t('common.component')}>
        {(p) => <select {...p} {...register('component')} className={inputCls}>{COMPONENTS.map((c) => <option key={c} value={c}>{t(`component.${c}`)}</option>)}</select>}
      </Field>
      <Field label={t('request.units')} hint={t('request.unitsHint')} error={err('units_needed')}>
        {(p) => <input {...p} type="number" inputMode="numeric" min={1} max={20} {...register('units_needed')} className={`${inputCls} font-mono`} />}
      </Field>
      <Field label={t('request.hospital')} error={err('site_id')} className={cx(!compact && 'sm:col-span-2')}>
        {(p) => <select {...p} {...register('site_id')} className={inputCls}><option value="">{t('request.chooseHospital')}</option>{hospitals.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>}
      </Field>
      <fieldset className="grid gap-2">
        <legend className="mb-2 text-sm font-medium text-zinc-800">{t('request.urgency')}</legend>
        <div className="grid grid-cols-3 gap-2">
          {(['emergency', 'urgent', 'routine'] as const).map((u) => (
            <label key={u} className={cx('flex h-10 cursor-pointer items-center justify-center rounded-lg text-sm font-medium ring-1 ring-inset has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand',
              urgency === u ? (u === 'emergency' ? 'bg-red-700 text-white ring-red-700' : 'bg-zinc-900 text-white ring-zinc-900') : 'bg-white text-zinc-700 ring-zinc-300 hover:bg-zinc-50')}>
              <input type="radio" value={u} {...register('urgency')} className="sr-only" />{t(`urgency.${u}`)}
            </label>
          ))}
        </div>
      </fieldset>
      <Field label={t('request.neededBy')} error={err('needed_by')}>
        {(p) => <input {...p} type="datetime-local" {...register('needed_by')} className={inputCls} />}
      </Field>
      {m.error && <p role="alert" className={cx('text-sm text-red-700', !compact && 'sm:col-span-2')}>{m.error instanceof ApiError ? t(`errors.${m.error.code}`) : t('errors.generic')}</p>}
      <p className={cx('text-xs leading-relaxed text-zinc-500', !compact && 'sm:col-span-2')}>{t('request.confirmNote')}</p>
      <Button type="submit" variant="primary" size="lg" loading={m.isPending} className={cx(!compact && 'sm:col-span-2 sm:justify-self-end')}>{t('request.submit')}</Button>
    </form>
  )
}
