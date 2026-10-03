import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ArrowRight } from '@phosphor-icons/react'
import { ApiError, LIVE, login, verifyTotp } from '../../api/client'
import { db } from '../../api/mock'
import { Button, Field, inputCls } from '../../components/ui'
import { Logo } from '../../components/Logo'
import { homeFor, useSession } from '../../session'

const schema = z.object({
  email: z.string().trim().email('form.email'),
  password: z.string().min(12, 'form.passwordMin'),
})
type Values = z.infer<typeof schema>

export function Component() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const { refresh, session } = useSession()
  const [step, setStep] = useState<'password' | 'totp'>('password')
  const [code, setCode] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const { register, handleSubmit, setValue, formState: { errors } } = useForm<Values>({ resolver: zodResolver(schema) })

  const done = () => { refresh(); nav(homeFor(JSON.parse(sessionStorage.getItem('lg.session')!))) }
  const fail = (e: unknown) => setErr(e instanceof ApiError ? t(`errors.${e.code}`) : t('errors.generic'))

  const onPassword = handleSubmit(async (v) => {
    setErr(null); setBusy(true)
    try { (await login(v.email, v.password)).totp_required ? setStep('totp') : done() } catch (e) { fail(e) } finally { setBusy(false) }
  })
  const onTotp = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null); setBusy(true)
    try { await verifyTotp(code); done() } catch (e) { fail(e) } finally { setBusy(false) }
  }

  if (session && !busy) return <Navigate to={homeFor(session)} replace />

  return (
    <div className="grid min-h-[100dvh] lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <main className="flex flex-col px-4 py-8 sm:px-12 lg:px-16">
        <Logo />
        <div className="my-auto w-full max-w-sm py-12">
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">{t('auth.staffEyebrow')}</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-950">{step === 'password' ? t('auth.staffTitle') : t('auth.totpTitle')}</h1>
          <p className="mt-2 text-sm leading-relaxed text-zinc-600">{step === 'password' ? t('auth.staffBody') : t('auth.totpBody')}</p>

          {step === 'password' ? (
            <form onSubmit={onPassword} noValidate className="mt-8 grid gap-5">
              <Field label={t('auth.email')} error={errors.email && t(errors.email.message!)}>
                {(p) => <input {...p} {...register('email')} type="email" autoComplete="username" spellCheck={false} placeholder={t('auth.emailPh')} className={inputCls} />}
              </Field>
              <Field label={t('auth.password')} error={errors.password && t(errors.password.message!)}>
                {(p) => <input {...p} {...register('password')} type="password" autoComplete="current-password" className={inputCls} />}
              </Field>
              {err && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 ring-1 ring-inset ring-red-200">{err}</p>}
              <Button type="submit" variant="primary" size="lg" loading={busy}>{t('auth.signIn')}<ArrowRight size={18} aria-hidden /></Button>
            </form>
          ) : (
            <form onSubmit={onTotp} className="mt-8 grid gap-5">
              <Field label={t('auth.totpCode')} hint={t('auth.totpHint')} error={err ?? undefined}>
                {(p) => <input {...p} name="totp" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" autoFocus placeholder="000000" className={`${inputCls} font-mono text-lg tracking-[0.4em] h-12`} />}
              </Field>
              <Button type="submit" variant="primary" size="lg" loading={busy} disabled={code.length !== 6}>{t('auth.verify')}</Button>
              <Button variant="ghost" onClick={() => { setStep('password'); setErr(null) }}>{t('common.back')}</Button>
            </form>
          )}

          <details className="mt-10 rounded-xl border border-zinc-200 bg-white p-4 text-sm">
            <summary className="cursor-pointer font-medium text-zinc-800">{t('auth.demoAccounts')}</summary>
            <p className="mt-2 text-zinc-600">{t(LIVE ? 'auth.demoHintLive' : 'auth.demoHint')}</p>
            <ul className="mt-3 divide-y divide-zinc-100">
              {db.staff.filter((u) => u.active).map((u) => (
                <li key={u.id}>
                  <button
                    type="button"
                    onClick={() => { setValue('email', u.email); setValue('password', 'synthetic-demo-pass'); setStep('password') }}
                    className="flex w-full items-center justify-between gap-3 py-2 text-left hover:text-brand focus-visible:outline-2 focus-visible:outline-brand rounded"
                  >
                    <span className="truncate font-mono text-xs">{u.email}</span>
                    <span className="shrink-0 text-xs text-zinc-500">{t(`roles.${u.role}`)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </details>
        </div>
        <div className="grid gap-2">
          <Link to="/app" className="w-fit text-sm font-medium text-brand underline underline-offset-4">{t('auth.appLink')}</Link>
          <p className="text-xs text-zinc-500">{t('common.syntheticNotice')}</p>
        </div>
      </main>
      <NetworkPanel />
    </div>
  )
}

/** Decorative: sites as nodes, transfer lanes drawing themselves. */
function NetworkPanel() {
  const { t } = useTranslation()
  const nodes = db.sites.map((s) => ({ x: ((s.lng - 90.24) / 0.29) * 520 + 40, y: (1 - (s.lat - 23.6) / 0.31) * 520 + 40, bank: s.type === 'blood_bank' }))
  const lanes = [[0, 5], [0, 6], [0, 9], [1, 3], [1, 12], [2, 8], [4, 7], [0, 13], [1, 11], [5, 10]]
  return (
    <aside className="relative hidden overflow-hidden bg-zinc-950 lg:flex lg:flex-col lg:justify-end" aria-hidden>
      <svg viewBox="0 0 600 600" className="absolute inset-0 m-auto h-full w-full max-w-[720px] opacity-90">
        <defs>
          <radialGradient id="glow"><stop offset="0" stopColor="#8f1d2c" stopOpacity="0.35" /><stop offset="1" stopColor="#8f1d2c" stopOpacity="0" /></radialGradient>
        </defs>
        <circle cx="300" cy="300" r="280" fill="url(#glow)" />
        {lanes.map(([a, b], i) => (
          <line key={i} x1={nodes[a].x} y1={nodes[a].y} x2={nodes[b].x} y2={nodes[b].y} stroke="#e4e4e7" strokeOpacity="0.25" strokeWidth="1.2"
            strokeDasharray="400" strokeDashoffset="400" style={{ animation: `draw 2.4s ${i * 0.18}s var(--ease-out-expo) forwards` }} />
        ))}
        {nodes.map((n, i) => (
          <g key={i}>
            <circle cx={n.x} cy={n.y} r={n.bank ? 9 : 5} fill={n.bank ? '#b23a48' : '#fafafa'} fillOpacity={n.bank ? 1 : 0.85} />
            {n.bank && <circle cx={n.x} cy={n.y} r="18" fill="none" stroke="#b23a48" strokeOpacity="0.5" className="live-dot" style={{ transformOrigin: `${n.x}px ${n.y}px` }} />}
          </g>
        ))}
      </svg>
      <style>{'@keyframes draw { to { stroke-dashoffset: 0 } }'}</style>
      <div className="relative m-12 max-w-md border-l border-white/15 pl-6">
        <p className="text-lg font-medium leading-snug tracking-tight text-zinc-100 text-balance">{t('auth.panelQuote')}</p>
        <p className="mt-3 text-sm text-zinc-400">{t('auth.panelSub', { sites: db.sites.length })}</p>
      </div>
    </aside>
  )
}
