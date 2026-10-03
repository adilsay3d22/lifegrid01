import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { DownloadSimple, FunnelSimple, Plus, UploadSimple, Drop } from '@phosphor-icons/react'
import { ApiError, LIFECYCLE, importUnits, listSites, listUnits, receiveUnit, transitionUnits, type UnitFilter } from '../../api/client'
import type { Abo, BloodUnit, Component as Comp, Rh, UnitStatus } from '../../api/types'
import { Badge, Button, Dialog, EmptyState, Field, GroupChip, PageHeader, QueryView, cx, inputCls, tdCls, thCls } from '../../components/ui'
import { ExpiryCell, UnitStatusBadge } from '../../components/status'
import { COMPONENTS, GROUPS, SHELF_DAYS, groupLabel } from '../../lib/rules'
import { downloadFile, fmtDate, fmtNum } from '../../lib/format'
import { useSession } from '../../session'

type Action = 'issue' | 'release' | 'quarantine' | 'clear' | 'discard'
const ACTIONS: Record<Action, { to: UnitStatus; from: UnitStatus[]; destructive: boolean }> = {
  issue: { to: 'issued', from: ['reserved'], destructive: false },
  release: { to: 'available', from: ['reserved'], destructive: false },
  quarantine: { to: 'quarantined', from: ['available', 'reserved', 'in_transit'], destructive: true },
  clear: { to: 'available', from: ['quarantined'], destructive: false },
  discard: { to: 'discarded', from: ['quarantined', 'expired'], destructive: true },
}
const STATUSES = Object.keys(LIFECYCLE) as UnitStatus[]
const PAGE = 60

export function Component() {
  const { id = '' } = useParams()
  const { t } = useTranslation()
  const nav = useNavigate()
  const { session } = useSession()
  const qc = useQueryClient()
  // Filters live in the URL so a filtered view can be shared or bookmarked.
  const [params, setParams] = useSearchParams()
  const f: Omit<UnitFilter, 'site_id'> = {
    status: (params.get('status') ?? 'available').replace('all', '') as UnitStatus | '', component: (params.get('component') ?? '') as Comp | '',
    group: params.get('group') ?? '', band: (params.get('band') ?? '') as UnitFilter['band'],
  }
  const setF = (next: typeof f) => {
    const p: Record<string, string> = {}
    if (next.status !== 'available') p.status = next.status || 'all'
    for (const k of ['component', 'group', 'band'] as const) if (next[k]) p[k] = next[k]!
    setParams(p, { replace: true })
  }
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [limit, setLimit] = useState(PAGE)
  const [action, setAction] = useState<Action | null>(null)
  const [dialog, setDialog] = useState<'receive' | 'import' | null>(null)

  const sites = useQuery({ queryKey: ['sites'], queryFn: listSites })
  const units = useQuery({ queryKey: ['units', id, f], queryFn: () => listUnits({ site_id: id, ...f }) })
  const site = sites.data?.find((s) => s.id === id)
  const mySites = sites.data?.filter((s) => session?.role === 'bank_manager' || session?.site_ids.includes(s.id)) ?? []

  const picked = useMemo(() => units.data?.filter((u) => selected.has(u.id)) ?? [], [units.data, selected])
  const validActions = (Object.keys(ACTIONS) as Action[]).filter((a) => picked.length > 0 && picked.every((u) => ACTIONS[a].from.includes(u.status)))
  const setFilter = (patch: Partial<typeof f>) => { setF({ ...f, ...patch }); setSelected(new Set()); setLimit(PAGE) }
  const refresh = () => { qc.invalidateQueries({ queryKey: ['units'] }); qc.invalidateQueries({ queryKey: ['stock'] }) }
  const toggle = (uid: string) => setSelected((s) => { const n = new Set(s); n.has(uid) ? n.delete(uid) : n.add(uid); return n })

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow={site ? `${site.code} · ${t(`siteType.${site.type}`)}` : ' '}
        title={site?.name ?? t('stock.title')}
        description={t('stock.description')}
        actions={<>
          {mySites.length > 1 && (
            <label className="flex items-center gap-2">
              <span className="sr-only">{t('common.site')}</span>
              <select value={id} onChange={(e) => nav(`/staff/sites/${e.target.value}/stock`)} className={`${inputCls} w-56`}>
                {mySites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </label>
          )}
          <Button onClick={() => setDialog('import')}><UploadSimple size={16} aria-hidden />{t('stock.import')}</Button>
          <Button variant="primary" onClick={() => setDialog('receive')}><Plus size={16} aria-hidden />{t('stock.receive')}</Button>
        </>}
      />

      <div className="flex flex-wrap items-end gap-3" role="group" aria-label={t('common.filters')}>
        <FunnelSimple size={18} className="mb-2.5 text-zinc-500" aria-hidden />
        <FilterSelect label={t('common.status')} value={f.status ?? ''} onChange={(v) => setFilter({ status: v as UnitStatus })}
          options={STATUSES.map((s) => [s, t(`unitStatus.${s}`)])} />
        <FilterSelect label={t('common.component')} value={f.component ?? ''} onChange={(v) => setFilter({ component: v as Comp })}
          options={COMPONENTS.map((c) => [c, t(`component.${c}`)])} />
        <FilterSelect label={t('common.group')} value={f.group ?? ''} onChange={(v) => setFilter({ group: v })}
          options={GROUPS.map(([a, r]) => [`${a}${r}`, groupLabel(a, r)])} />
        <FilterSelect label={t('stock.expiryBand')} value={f.band ?? ''} onChange={(v) => setFilter({ band: v as UnitFilter['band'] })}
          options={[['0_2', t('stock.band0_2')], ['3_7', t('stock.band3_7')], ['8', t('stock.band8')]]} />
        <p className="ml-auto pb-2.5 text-sm text-zinc-500" aria-live="polite">
          {units.data && t('stock.resultCount', { count: units.data.length })} <span className="text-zinc-500">&middot; {t('stock.fefo')}</span>
        </p>
      </div>

      <QueryView q={units} rows={10} empty={
        <EmptyState icon={<Drop size={20} />} title={t('stock.emptyTitle')} body={t('stock.emptyBody')}
          action={<Button size="sm" onClick={() => setFilter({ status: '', component: '', group: '', band: '' })}>{t('common.clearFilters')}</Button>} />
      }>
        {(data) => (
          <div tabIndex={0} className="overflow-x-auto rounded-2xl focus-visible:outline-2 focus-visible:outline-brand bg-white ring-1 ring-zinc-200">
            <table className="w-full min-w-[720px] text-sm">
              <caption className="sr-only">{t('stock.tableCaption')}</caption>
              <thead className="border-b border-zinc-200">
                <tr>
                  <th scope="col" className="w-10 pl-4">
                    <input type="checkbox" aria-label={t('stock.selectAll')} className="size-4 accent-brand"
                      checked={data.length > 0 && data.slice(0, limit).every((u) => selected.has(u.id))}
                      onChange={(e) => setSelected(e.target.checked ? new Set(data.slice(0, limit).map((u) => u.id)) : new Set())} />
                  </th>
                  <th scope="col" className={thCls}>{t('stock.unit')}</th>
                  <th scope="col" className={thCls}>{t('common.group')}</th>
                  <th scope="col" className={thCls}>{t('common.component')}</th>
                  <th scope="col" className={thCls}>{t('stock.expires')}</th>
                  <th scope="col" className={`${thCls} text-right`}>{t('stock.remaining')}</th>
                  <th scope="col" className={thCls}>{t('common.status')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {data.slice(0, limit).map((u, i) => (
                  <tr key={u.id} className={cx('reveal transition-colors', selected.has(u.id) ? 'bg-brand-soft/60' : 'hover:bg-zinc-50')} style={{ '--i': i } as React.CSSProperties}>
                    <td className="pl-4"><input type="checkbox" className="size-4 accent-brand" checked={selected.has(u.id)} onChange={() => toggle(u.id)} aria-label={t('stock.selectUnit', { code: u.unit_code })} /></td>
                    <td className={tdCls}><Link to={`/staff/units/${u.id}`} className="font-mono text-zinc-900 hover:text-brand hover:underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-brand rounded">{u.unit_code}</Link></td>
                    <td className={tdCls}><GroupChip label={groupLabel(u.abo, u.rh)} /></td>
                    <td className={`${tdCls} text-zinc-700`}>{t(`component.${u.component}`)}</td>
                    <td className={`${tdCls} text-zinc-700 tabular-nums`}>{fmtDate(u.expires_at)}</td>
                    <td className={`${tdCls} text-right`}><ExpiryCell at={u.expires_at} /></td>
                    <td className={tdCls}><UnitStatusBadge s={u.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.length > limit && (
              <div className="border-t border-zinc-200 p-3 text-center">
                <Button variant="ghost" size="sm" onClick={() => setLimit(limit + PAGE)}>{t('common.showMore', { count: Math.min(PAGE, data.length - limit) })}</Button>
              </div>
            )}
          </div>
        )}
      </QueryView>

      {picked.length > 0 && (
        <div className="reveal sticky bottom-4 z-20 mx-auto flex w-full max-w-3xl flex-wrap items-center gap-3 rounded-2xl bg-zinc-900 px-4 py-3 text-white shadow-[0_16px_32px_-12px_rgb(24_24_27/0.45)]">
          <p className="text-sm"><span className="font-mono tabular-nums">{picked.length}</span> {t('stock.selected')}</p>
          <div className="ml-auto flex flex-wrap gap-2">
            {validActions.length === 0 && <span className="text-sm text-zinc-400">{t('stock.noCommonAction')}</span>}
            {validActions.map((a) => (
              <button key={a} type="button" onClick={() => setAction(a)}
                className={cx('h-8 rounded-lg px-3 text-sm font-medium transition-colors active:scale-[0.98] focus-visible:outline-2 focus-visible:outline-white',
                  ACTIONS[a].destructive ? 'bg-red-500/15 text-red-200 hover:bg-red-500/25' : 'bg-white/10 hover:bg-white/20')}>
                {t(`stock.action.${a}`)}
              </button>
            ))}
            <button type="button" onClick={() => setSelected(new Set())} className="h-8 rounded-lg px-3 text-sm text-zinc-300 hover:text-white focus-visible:outline-2 focus-visible:outline-white">{t('common.cancel')}</button>
          </div>
        </div>
      )}

      {action && <TransitionDialog action={action} units={picked} onClose={() => setAction(null)} onDone={() => { setAction(null); setSelected(new Set()); refresh() }} />}
      <ReceiveDialog open={dialog === 'receive'} siteId={id} onClose={() => setDialog(null)} onDone={refresh} />
      <ImportDialog open={dialog === 'import'} siteId={id} onClose={() => setDialog(null)} onDone={refresh} />
    </div>
  )
}

function FilterSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  const { t } = useTranslation()
  return (
    <label className="grid gap-1">
      <span className="text-xs font-medium text-zinc-500">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={`${inputCls} h-9 w-40`}>
        <option value="">{t('common.all')}</option>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  )
}

/** Every stock-changing action confirms the unit count; destructive ones need a reason (spec section 15). */
function TransitionDialog({ action, units, onClose, onDone }: { action: Action; units: BloodUnit[]; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')
  const [touched, setTouched] = useState(false)
  const cfg = ACTIONS[action]
  const m = useMutation({ mutationFn: () => transitionUnits(units.map((u) => u.id), cfg.to, reason || t(`stock.action.${action}`)), onSuccess: onDone })
  const needsReason = cfg.destructive && reason.trim().length < 4
  return (
    <Dialog open onClose={onClose} title={t(`stock.confirm.${action}`, { count: units.length })} description={t('stock.confirmBody', { count: units.length })}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant={cfg.destructive ? 'danger' : 'primary'} loading={m.isPending}
          onClick={() => { setTouched(true); if (!needsReason) m.mutate() }}>
          {t(`stock.action.${action}`)} &middot; <span className="font-mono">{units.length}</span>
        </Button>
      </>}>
      <ul className="max-h-40 overflow-y-auto rounded-lg bg-zinc-50 p-3 font-mono text-xs text-zinc-700 grid grid-cols-2 gap-1">
        {units.map((u) => <li key={u.id}>{u.unit_code} <span className="text-zinc-500">{groupLabel(u.abo, u.rh)}</span></li>)}
      </ul>
      <Field label={cfg.destructive ? t('stock.reasonRequired') : t('stock.reasonOptional')} error={touched && needsReason ? t('form.reasonMin') : undefined}>
        {(p) => <textarea {...p} value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className={`${inputCls} h-auto py-2`} />}
      </Field>
      {m.error && <p role="alert" className="text-sm text-red-700">{m.error instanceof ApiError ? m.error.message : t('errors.generic')}</p>}
    </Dialog>
  )
}

const unitSchema = z.object({
  unit_code: z.string().trim().regex(/^[A-Z0-9-]{6,20}$/, 'form.unitCode'),
  group: z.string().min(2, 'form.required'),
  component: z.enum(['red_cells', 'platelets', 'plasma']),
  collected_at: z.string().min(1, 'form.required'),
  expires_at: z.string().min(1, 'form.required'),
}).refine((v) => Date.parse(v.expires_at) > Date.parse(v.collected_at), { path: ['expires_at'], message: 'form.expiryAfter' })
type UnitValues = z.infer<typeof unitSchema>

const localInput = (ms: number) => new Date(ms - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 16)

function ReceiveDialog({ open, siteId, onClose, onDone }: { open: boolean; siteId: string; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation()
  const now = Date.now()
  const { register, handleSubmit, setValue, getValues, reset, formState: { errors } } = useForm<UnitValues>({
    resolver: zodResolver(unitSchema),
    defaultValues: { unit_code: '', group: 'Opos', component: 'red_cells', collected_at: localInput(now - 86_400_000), expires_at: localInput(now + 41 * 86_400_000) },
  })
  const m = useMutation({
    mutationFn: (v: UnitValues) => {
      const [abo, rh] = [v.group.replace(/pos|neg/, '') as Abo, (v.group.endsWith('neg') ? 'neg' : 'pos') as Rh]
      return receiveUnit({ unit_code: v.unit_code, abo, rh, component: v.component, collected_at: v.collected_at, expires_at: v.expires_at, site_id: siteId })
    },
    onSuccess: () => { onDone(); reset(); onClose() },
  })
  // Shelf life default fills expiry from collection date; still editable.
  const syncExpiry = () => {
    const c = Date.parse(getValues('collected_at'))
    if (!Number.isNaN(c)) setValue('expires_at', localInput(c + SHELF_DAYS[getValues('component')] * 86_400_000))
  }
  const err = (k: keyof UnitValues) => errors[k] && t(errors[k]!.message!)
  return (
    <Dialog open={open} onClose={onClose} title={t('stock.receiveTitle')} description={t('stock.receiveBody')}>
      <form onSubmit={handleSubmit((v) => m.mutate(v))} noValidate className="grid gap-4 sm:grid-cols-2">
        <Field label={t('stock.unitCode')} hint={t('stock.unitCodeHint')} error={err('unit_code')} className="sm:col-span-2">
          {(p) => <input {...p} {...register('unit_code')} autoComplete="off" spellCheck={false} placeholder="LG26-0052114" className={`${inputCls} font-mono uppercase`} />}
        </Field>
        <Field label={t('common.group')} error={err('group')}>
          {(p) => <select {...p} {...register('group')} className={inputCls}>{GROUPS.map(([a, r]) => <option key={a + r} value={`${a}${r}`}>{groupLabel(a, r)}</option>)}</select>}
        </Field>
        <Field label={t('common.component')}>
          {(p) => <select {...p} {...register('component', { onChange: syncExpiry })} className={inputCls}>{COMPONENTS.map((c) => <option key={c} value={c}>{t(`component.${c}`)}</option>)}</select>}
        </Field>
        <Field label={t('stock.collectedAt')} error={err('collected_at')}>
          {(p) => <input {...p} type="datetime-local" {...register('collected_at', { onChange: syncExpiry })} className={inputCls} />}
        </Field>
        <Field label={t('stock.expiresAt')} error={err('expires_at')}>
          {(p) => <input {...p} type="datetime-local" {...register('expires_at')} className={inputCls} />}
        </Field>
        {m.error && <p role="alert" className="sm:col-span-2 text-sm text-red-700">{m.error instanceof ApiError ? t(`errors.${m.error.code}`) : t('errors.generic')}</p>}
        <div className="sm:col-span-2 flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" variant="primary" loading={m.isPending}>{t('stock.receiveOne')}</Button>
        </div>
      </form>
    </Dialog>
  )
}

const TEMPLATE = 'unit_code,abo,rh,component,collected_at,expires_at\nLG26-0090001,O,pos,red_cells,2026-09-28T08:00:00Z,2026-11-09T08:00:00Z\n'

function ImportDialog({ open, siteId, onClose, onDone }: { open: boolean; siteId: string; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  const m = useMutation({ mutationFn: () => importUnits(siteId, text), onSuccess: (r) => r.imported && onDone() })
  const close = () => { m.reset(); setText(''); onClose() }
  return (
    <Dialog open={open} onClose={close} wide title={t('stock.importTitle')} description={t('stock.importBody')}
      footer={m.data ? <Button variant="primary" onClick={close}>{t('common.done')}</Button> : <>
        <Button variant="ghost" onClick={close}>{t('common.cancel')}</Button>
        <Button variant="primary" disabled={!text.trim()} loading={m.isPending} onClick={() => m.mutate()}>{t('stock.importRun')}</Button>
      </>}>
      {!m.data ? (
        <div className="grid gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-lg bg-white px-4 text-sm font-medium ring-1 ring-inset ring-zinc-300 hover:bg-zinc-50 focus-within:ring-2 focus-within:ring-brand">
              <UploadSimple size={16} aria-hidden />{t('stock.chooseFile')}
              <input type="file" accept=".csv,text/csv" className="sr-only" onChange={async (e) => setText((await e.target.files?.[0]?.text()) ?? '')} />
            </label>
            <Button variant="ghost" size="sm" onClick={() => downloadFile('lifegrid-units-template.csv', TEMPLATE, 'text/csv')}><DownloadSimple size={16} aria-hidden />{t('stock.template')}</Button>
          </div>
          <Field label={t('stock.pasteCsv')}>
            {(p) => <textarea {...p} value={text} onChange={(e) => setText(e.target.value)} rows={7} spellCheck={false} placeholder={TEMPLATE} className={`${inputCls} h-auto py-2 font-mono text-xs`} />}
          </Field>
          {m.error && <p role="alert" className="text-sm text-red-700">{t('errors.bad_header', { cols: (m.error as Error).message })}</p>}
        </div>
      ) : (
        <div className="grid gap-4" aria-live="polite">
          <div className="flex gap-3">
            <Badge tone="good">{t('stock.imported', { count: m.data.imported })}</Badge>
            {m.data.errors.length > 0 && <Badge tone="bad">{t('stock.rejected', { count: m.data.errors.length })}</Badge>}
          </div>
          {m.data.errors.length > 0 && (
            <table className="w-full text-sm">
              <thead><tr className="border-b border-zinc-200"><th scope="col" className={thCls}>{t('stock.row')}</th><th scope="col" className={thCls}>{t('stock.reason')}</th></tr></thead>
              <tbody className="divide-y divide-zinc-100">
                {m.data.errors.map((e) => <tr key={e.row}><td className={`${tdCls} font-mono`}>{fmtNum(e.row)}</td><td className={tdCls}>{t(`errors.${e.reason}`)}</td></tr>)}
              </tbody>
            </table>
          )}
        </div>
      )}
    </Dialog>
  )
}
