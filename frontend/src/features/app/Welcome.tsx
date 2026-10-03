import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, ArrowRight, DeviceMobile, Drop, FirstAid } from '@phosphor-icons/react'
import { ApiError, LIVE, requestOtp, verifyOtp } from '../../api/client'
import { Button, Field, inputCls, cx } from '../../components/ui'
import { Logo } from '../../components/Logo'
import { homeFor, useSession } from '../../session'
import { useInstallPrompt } from '../../lib/install'

type Step = 'role' | 'phone' | 'code'

/** FR-AUTH-02: phone one-time code. The account is created on first verify. */
export function Component() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const { session, refresh } = useSession()
  const [initial] = useState(session)
  const [step, setStep] = useState<Step>('role')
  const [role, setRole] = useState<'donor' | 'requester'>('donor')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [devCode, setDevCode] = useState<string | null>(null)
  const install = useInstallPrompt()

  // Only redirect a session that existed on arrival; a fresh sign-in navigates itself (register vs home).
  if (initial && (initial.role === 'donor' || initial.role === 'requester')) return <Navigate to={homeFor(initial)} replace />

  const run = async (fn: () => Promise<void>) => {
    setErr(null); setBusy(true)
    try { await fn() } catch (e) { setErr(e instanceof ApiError ? t(`errors.${e.code}`) : t('errors.generic')) } finally { setBusy(false) }
  }

  return (
    <main className="mx-auto flex min-h-[100dvh] max-w-md flex-col px-4 pb-8 pt-6">
      <Logo />
      <div className="mt-auto pt-12">
        {step !== 'role' && (
          <button type="button" onClick={() => { setStep(step === 'code' ? 'phone' : 'role'); setErr(null) }} className="-ml-2 mb-6 flex h-9 items-center gap-1.5 rounded-md px-2 text-sm text-zinc-600 hover:bg-zinc-100 focus-visible:outline-2 focus-visible:outline-brand">
            <ArrowLeft size={16} aria-hidden />{t('common.back')}
          </button>
        )}

        {step === 'role' && (
          <div className="reveal">
            <h1 className="text-3xl font-semibold tracking-tight text-balance text-zinc-950">{t('welcome.title')}</h1>
            <p className="mt-3 text-base leading-relaxed text-zinc-600">{t('welcome.body')}</p>
            <div className="mt-8 grid gap-3">
              {([['donor', Drop], ['requester', FirstAid]] as const).map(([r, I], i) => (
                <button key={r} type="button" onClick={() => { setRole(r); setStep('phone') }} style={{ '--i': i + 1 } as React.CSSProperties}
                  className="reveal group flex items-center gap-4 rounded-2xl bg-white p-5 text-left ring-1 ring-zinc-200 transition-[box-shadow,transform] duration-300 ease-out-expo hover:shadow-[0_12px_28px_-14px_rgb(24_24_27/0.25)] active:scale-[0.99] focus-visible:outline-2 focus-visible:outline-brand">
                  <span className={cx('grid size-12 shrink-0 place-items-center rounded-xl', r === 'donor' ? 'bg-brand text-white' : 'bg-zinc-900 text-white')}><I size={24} weight="fill" aria-hidden /></span>
                  <span className="flex-1">
                    <span className="block font-medium text-zinc-950">{t(`welcome.${r}Title`)}</span>
                    <span className="mt-0.5 block text-sm text-zinc-600">{t(`welcome.${r}Body`)}</span>
                  </span>
                  <ArrowRight size={18} className="text-zinc-500 transition-transform group-hover:translate-x-0.5" aria-hidden />
                </button>
              ))}
            </div>
          </div>
        )}

        {step === 'phone' && (
          <form className="reveal grid gap-5" onSubmit={(e) => { e.preventDefault(); run(async () => { setDevCode((await requestOtp(phone)).dev_code); setStep('code') }) }}>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-zinc-950">{t('welcome.phoneTitle')}</h1>
              <p className="mt-2 text-sm text-zinc-600">{t('welcome.phoneBody')}</p>
            </div>
            <Field label={t('welcome.phone')} hint={t('welcome.phoneHint')} error={err ?? undefined}>
              {(p) => <input {...p} name="phone" type="tel" inputMode="tel" autoComplete="tel" autoFocus value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+880 17xx-xxxxxx" className={`${inputCls} h-12 text-base`} />}
            </Field>
            <Button type="submit" variant="primary" size="lg" loading={busy} disabled={phone.length < 9}>{t('welcome.sendCode')}</Button>
          </form>
        )}

        {step === 'code' && (
          <form className="reveal grid gap-5" onSubmit={(e) => { e.preventDefault(); run(async () => { await verifyOtp(phone, code, role); refresh(); nav(role === 'donor' ? '/app/donor' : '/app/requests') }) }}>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-zinc-950">{t('welcome.codeTitle')}</h1>
              <p className="mt-2 text-sm text-zinc-600">{t('welcome.codeBody', { phone })}</p>
            </div>
            <Field label={t('welcome.code')} hint={t(LIVE ? 'welcome.codeHintLive' : 'welcome.codeHint')} error={err ?? undefined}>
              {(p) => <input {...p} name="code" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" autoFocus placeholder="000000" className={`${inputCls} h-14 text-center font-mono text-2xl tracking-[0.5em]`} />}
            </Field>
            {devCode && (
              <p className="flex items-center justify-between gap-3 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-inset ring-amber-200">
                <span>{t('welcome.devCode')}</span>
                <button type="button" onClick={() => setCode(devCode)} className="font-mono text-base font-semibold tracking-widest underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-brand rounded">{devCode}</button>
              </p>
            )}
            <Button type="submit" variant="primary" size="lg" loading={busy} disabled={code.length !== 6}>{t('welcome.verify')}</Button>
          </form>
        )}
      </div>
      <div className="mt-10 grid justify-items-center gap-3 text-center">
        {install && step === 'role' && (
          <Button variant="secondary" onClick={install}><DeviceMobile size={18} aria-hidden />{t('welcome.install')}</Button>
        )}
        <Link to="/staff/login" className="text-sm font-medium text-zinc-600 underline underline-offset-4 hover:text-zinc-900">{t('welcome.staffLink')}</Link>
        <p className="text-xs text-zinc-500">{t('common.syntheticNotice')}</p>
      </div>
    </main>
  )
}
