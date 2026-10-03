import { useParamState } from '../../lib/useParamState'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listCompatRules, listSettings, listSites, listUsers, updateSetting, updateUser } from '../../api/client'
import type { Component as Comp, Role, Setting, StaffUser } from '../../api/types'
import { Badge, Button, PageHeader, QueryView, Segmented, inputCls, tdCls, thCls, cx } from '../../components/ui'
import { COMPONENTS, GROUPS, groupLabel } from '../../lib/rules'
import { fmtDateTime } from '../../lib/format'
import { STAFF_ROLES } from '../../session'

type Tab = 'users' | 'sites' | 'settings' | 'rules'

export function Component() {
  const { t } = useTranslation()
  const [tab, setTab] = useParamState<Tab>('tab', 'users')
  return (
    <div className="grid gap-6">
      <PageHeader title={t('admin.title')} description={t('admin.description')} />
      <Segmented label={t('admin.section')} value={tab} onChange={setTab} options={(['users', 'sites', 'settings', 'rules'] as Tab[]).map((v) => ({ value: v, label: t(`admin.tab.${v}`) }))} />
      {tab === 'users' && <Users />}
      {tab === 'sites' && <Sites />}
      {tab === 'settings' && <Settings />}
      {tab === 'rules' && <Rules />}
    </div>
  )
}

function Toggle({ checked, onChange, label, busy }: { checked: boolean; onChange: (v: boolean) => void; label: string; busy?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={busy} onClick={() => onChange(!checked)}
      className={cx('relative inline-flex h-6 w-10 shrink-0 items-center rounded-full transition-colors duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50', checked ? 'bg-emerald-600' : 'bg-zinc-300')}>
      <span className={cx('size-5 rounded-full bg-white shadow transition-transform duration-200 ease-out-expo', checked ? 'translate-x-[18px]' : 'translate-x-0.5')} />
    </button>
  )
}

function Users() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['users'], queryFn: listUsers })
  const sites = useQuery({ queryKey: ['sites'], queryFn: listSites })
  const m = useMutation({ mutationFn: ({ id, patch }: { id: string; patch: Partial<StaffUser> }) => updateUser(id, patch), onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }) })
  return (
    <QueryView q={q}>
      {(users) => (
        <div tabIndex={0} className="overflow-x-auto rounded-2xl focus-visible:outline-2 focus-visible:outline-brand bg-white ring-1 ring-zinc-200">
          <table className="w-full min-w-[780px] text-sm">
            <caption className="sr-only">{t('admin.tab.users')}</caption>
            <thead className="border-b border-zinc-200"><tr>
              <th scope="col" className={`${thCls} pl-5`}>{t('auth.email')}</th><th scope="col" className={thCls}>{t('admin.role')}</th>
              <th scope="col" className={thCls}>{t('admin.scope')}</th><th scope="col" className={thCls}>{t('admin.totp')}</th><th scope="col" className={thCls}>{t('admin.active')}</th>
            </tr></thead>
            <tbody className="divide-y divide-zinc-100">
              {users.map((u) => (
                <tr key={u.id} className={cx(!u.active && 'text-zinc-500')}>
                  <td className={`${tdCls} pl-5 font-mono text-xs`}>{u.email}</td>
                  <td className={tdCls}>
                    <select aria-label={t('admin.roleFor', { email: u.email })} value={u.role} onChange={(e) => m.mutate({ id: u.id, patch: { role: e.target.value as Role } })} className={`${inputCls} h-8 w-48`}>
                      {STAFF_ROLES.map((r) => <option key={r} value={r}>{t(`roles.${r}`)}</option>)}
                    </select>
                  </td>
                  <td className={`${tdCls} text-xs`}>{u.site_ids.length ? u.site_ids.map((id) => sites.data?.find((s) => s.id === id)?.code).join(', ') : <span className="text-zinc-500">{t('admin.region')}</span>}</td>
                  <td className={tdCls}>{u.totp ? <Badge tone="good">{t('admin.on')}</Badge> : u.role === 'admin' ? <Badge tone="bad">{t('admin.required')}</Badge> : <Badge>{t('admin.off')}</Badge>}</td>
                  <td className={tdCls}><Toggle checked={u.active} label={t('admin.activeFor', { email: u.email })} busy={m.isPending && m.variables?.id === u.id} onChange={(v) => m.mutate({ id: u.id, patch: { active: v } })} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-zinc-200 px-5 py-3 text-xs text-zinc-500">{t('admin.disableNote')}</p>
        </div>
      )}
    </QueryView>
  )
}

function Sites() {
  const { t } = useTranslation()
  const q = useQuery({ queryKey: ['sites'], queryFn: listSites })
  return (
    <QueryView q={q}>
      {(sites) => (
        <div tabIndex={0} className="overflow-x-auto rounded-2xl focus-visible:outline-2 focus-visible:outline-brand bg-white ring-1 ring-zinc-200">
          <table className="w-full min-w-[680px] text-sm">
            <caption className="sr-only">{t('admin.tab.sites')}</caption>
            <thead className="border-b border-zinc-200"><tr>
              <th scope="col" className={`${thCls} pl-5`}>{t('admin.code')}</th><th scope="col" className={thCls}>{t('admin.name')}</th><th scope="col" className={thCls}>{t('admin.type')}</th>
              <th scope="col" className={thCls}>{t('admin.location')}</th><th scope="col" className={thCls}>{t('admin.timezone')}</th><th scope="col" className={thCls}>{t('admin.active')}</th>
            </tr></thead>
            <tbody className="divide-y divide-zinc-100">
              {sites.map((s) => (
                <tr key={s.id}>
                  <td className={`${tdCls} pl-5 font-mono text-xs`}>{s.code}</td><td className={tdCls}>{s.name}</td><td className={tdCls}>{t(`siteType.${s.type}`)}</td>
                  <td className={`${tdCls} font-mono text-xs tabular-nums text-zinc-600`}>{s.lat.toFixed(4)}, {s.lng.toFixed(4)}</td>
                  <td className={`${tdCls} text-zinc-600`}>{s.timezone}</td>
                  <td className={tdCls}>{s.active ? <Badge tone="good" dot>{t('admin.active')}</Badge> : <Badge>{t('admin.inactive')}</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </QueryView>
  )
}

function SettingRow({ s }: { s: Setting }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const isObj = typeof s.value === 'object' && s.value !== null
  const shown = isObj ? JSON.stringify(s.value) : String(s.value)
  const [draft, setDraft] = useState(shown)
  const parse = () => (isObj ? JSON.parse(draft) : typeof s.value === 'number' ? Number(draft) : typeof s.value === 'boolean' ? draft === 'true' : draft)
  const m = useMutation({ mutationFn: () => updateSetting(s.key, parse()), onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }) })
  const dirty = draft !== shown
  let invalid = typeof s.value === 'number' && (draft.trim() === '' || Number.isNaN(Number(draft)))
  if (isObj) { try { JSON.parse(draft) } catch { invalid = true } }
  return (
    <tr>
      <td className={`${tdCls} pl-5 font-mono text-xs`}><label htmlFor={`set-${s.key}`}>{s.key}</label></td>
      <td className={tdCls}>
        {typeof s.value === 'boolean'
          ? <select id={`set-${s.key}`} value={draft} onChange={(e) => setDraft(e.target.value)} className={`${inputCls} h-8 w-28`}><option value="true">{t('admin.on')}</option><option value="false">{t('admin.off')}</option></select>
          : <input id={`set-${s.key}`} value={draft} onChange={(e) => setDraft(e.target.value)} inputMode={typeof s.value === 'number' ? 'decimal' : undefined}
              aria-invalid={invalid || undefined} spellCheck={false} title={isObj ? t('admin.jsonHint') : undefined} className={`${inputCls} h-8 font-mono ${isObj ? 'w-full min-w-64 text-xs' : 'w-28'}`} />}
      </td>
      <td className={`${tdCls} font-mono text-xs text-zinc-500`}>v{s.version}</td>
      <td className={`${tdCls} text-xs text-zinc-500`}>{fmtDateTime(s.updated_at)}</td>
      <td className={`${tdCls} pr-5 text-right`}>{dirty && <Button size="sm" variant="primary" disabled={invalid} loading={m.isPending} onClick={() => m.mutate()}>{t('common.save')}</Button>}</td>
    </tr>
  )
}

function Settings() {
  const { t } = useTranslation()
  const q = useQuery({ queryKey: ['settings'], queryFn: listSettings })
  return (
    <QueryView q={q}>
      {({ settings, history }) => (
        <div className="grid gap-8 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <div tabIndex={0} className="overflow-x-auto rounded-2xl focus-visible:outline-2 focus-visible:outline-brand bg-white ring-1 ring-zinc-200">
            <table className="w-full min-w-[600px] text-sm">
              <caption className="sr-only">{t('admin.tab.settings')}</caption>
              <thead className="border-b border-zinc-200"><tr>
                <th scope="col" className={`${thCls} pl-5`}>{t('admin.key')}</th><th scope="col" className={thCls}>{t('admin.value')}</th>
                <th scope="col" className={thCls}>{t('admin.version')}</th><th scope="col" className={thCls}>{t('admin.updated')}</th><th scope="col"><span className="sr-only">{t('common.actions')}</span></th>
              </tr></thead>
              <tbody className="divide-y divide-zinc-100">{settings.map((s) => <SettingRow key={`${s.key}-${s.version}`} s={s} />)}</tbody>
            </table>
          </div>
          <section aria-labelledby="hist-h">
            <h2 id="hist-h" className="text-base font-semibold tracking-tight">{t('admin.history')}</h2>
            <p className="mt-1 text-sm text-zinc-600">{t('admin.historyBody')}</p>
            <ol className="mt-4 divide-y divide-zinc-200 border-y border-zinc-200">
              {history.map((h, i) => (
                <li key={i} className="py-3 text-sm">
                  <p className="font-mono text-xs text-zinc-900">{h.key} <span className="text-zinc-500">v{h.version}</span></p>
                  <p className="mt-1 break-all font-mono text-xs"><span className="text-zinc-500 line-through">{typeof h.old_value === 'object' ? JSON.stringify(h.old_value) : String(h.old_value)}</span> <span aria-hidden>&rarr;</span><span className="sr-only">{t('plan.to')}</span> <span className="text-zinc-950">{typeof h.new_value === 'object' ? JSON.stringify(h.new_value) : String(h.new_value)}</span></p>
                  <p className="mt-1 text-xs text-zinc-500">{h.changed_by} &middot; {fmtDateTime(h.changed_at)}</p>
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
    </QueryView>
  )
}

function Rules() {
  const { t } = useTranslation()
  const [component, setComponent] = useState<Comp>('red_cells')
  const q = useQuery({ queryKey: ['compat', component], queryFn: () => listCompatRules(component) })
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented size="sm" label={t('common.component')} value={component} onChange={setComponent} options={COMPONENTS.map((c) => ({ value: c, label: t(`component.${c}`) }))} />
        <p className="text-xs text-zinc-500">{t('admin.rulesNote')}</p>
      </div>
      <QueryView q={q}>
        {(rules) => (
          <div tabIndex={0} className="overflow-x-auto rounded-2xl focus-visible:outline-2 focus-visible:outline-brand bg-white ring-1 ring-zinc-200">
            <table className="w-full min-w-[620px] text-sm">
              <caption className="px-5 pt-4 text-left text-xs text-zinc-500">{t('admin.rulesCaption')}</caption>
              <thead><tr className="border-b border-zinc-200">
                <th scope="col" className={`${thCls} pl-5`}>{t('admin.recipient')}</th>
                {GROUPS.map(([a, r]) => <th key={a + r} scope="col" className="px-2 py-2.5 text-center text-xs font-semibold text-zinc-700">{groupLabel(a, r)}</th>)}
              </tr></thead>
              <tbody className="divide-y divide-zinc-100">
                {GROUPS.map(([ra, rr]) => (
                  <tr key={ra + rr}>
                    <th scope="row" className={`${tdCls} pl-5 text-left font-semibold`}>{groupLabel(ra, rr)}</th>
                    {GROUPS.map(([da, dr]) => {
                      const rule = rules.find((x) => x.recipient_abo === ra && x.recipient_rh === rr && x.donor_abo === da && x.donor_rh === dr)
                      return (
                        <td key={da + dr} className="px-2 py-2 text-center">
                          {rule ? <span className={cx('inline-grid size-7 place-items-center rounded-md font-mono text-xs tabular-nums', rule.rank === 1 ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-700')}>{rule.rank}</span>
                            : <span className="text-zinc-300" aria-label={t('admin.incompatible')}>&middot;</span>}
                        </td>
                      )
                    })}
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
