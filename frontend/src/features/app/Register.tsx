import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation } from '@tanstack/react-query'
import { MapContainer, TileLayer, CircleMarker, useMapEvents } from 'react-leaflet'
import { ApiError, updateDonorProfile } from '../../api/client'
import type { Abo, Rh } from '../../api/types'
import { Button, Field, inputCls, cx } from '../../components/ui'
import { CONSENT_VERSION, GROUPS, groupLabel } from '../../lib/rules'


// Rounded to 0.01 deg (about 1 km) before it leaves the device (FR-DON-01, SEC-07).
const round = (n: number) => Math.round(n * 100) / 100

function PinPicker({ pin, setPin }: { pin: [number, number] | null; setPin: (p: [number, number]) => void }) {
  useMapEvents({ click: (e) => setPin([round(e.latlng.lat), round(e.latlng.lng)]) })
  return pin ? <CircleMarker center={pin} radius={22} pathOptions={{ color: '#8f1d2c', fillColor: '#8f1d2c', fillOpacity: 0.2, weight: 2 }} /> : null
}

export function Component() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const [group, setGroup] = useState<string>('')
  const [pin, setPin] = useState<[number, number] | null>(null)
  const [birthYear, setBirthYear] = useState('')
  const [weightOk, setWeightOk] = useState(false)
  const [consent, setConsent] = useState(false)
  const [tried, setTried] = useState(false)
  const year = new Date().getFullYear()
  const age = year - Number(birthYear)
  const errors = {
    group: !group && t('form.required'),
    pin: !pin && t('register.pinRequired'),
    birthYear: (!/^\d{4}$/.test(birthYear) || age < 18 || age > 60) && t('register.ageRule'),
    consent: !consent && t('register.consentRequired'),
  }
  const valid = !Object.values(errors).some(Boolean)
  const m = useMutation({
    mutationFn: () => updateDonorProfile({
      abo: group === 'unknown' ? null : (group.replace(/pos|neg/, '') as Abo), rh: group === 'unknown' ? null : ((group.endsWith('neg') ? 'neg' : 'pos') as Rh),
      area_lat: pin?.[0], area_lng: pin?.[1], birth_year: Number(birthYear), weight_ok: weightOk, consent: true, consent_version: CONSENT_VERSION,
    }),
    onSuccess: () => nav('/app/donor'),
  })
  const show = (k: keyof typeof errors) => (tried && errors[k]) || undefined

  return (
    <form noValidate onSubmit={(e) => { e.preventDefault(); setTried(true); if (valid) m.mutate() }} className="grid gap-8">
      <header>
        <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">{t('register.eyebrow')}</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-950">{t('register.title')}</h1>
        <p className="mt-2 text-sm leading-relaxed text-zinc-600">{t('register.body')}</p>
      </header>

      <fieldset className="grid gap-2">
        <legend className="mb-2 text-sm font-medium text-zinc-800">{t('register.group')}</legend>
        <div className="grid grid-cols-4 gap-2">
          {[...GROUPS.map(([a, r]) => [`${a}${r}`, groupLabel(a, r)]), ['unknown', t('register.unknown')]].map(([v, l]) => (
            <label key={v} className={cx('flex h-12 cursor-pointer items-center justify-center rounded-lg text-sm font-medium ring-1 ring-inset has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand active:scale-[0.98]',
              v === 'unknown' ? 'col-span-4' : 'text-base font-semibold', group === v ? 'bg-zinc-900 text-white ring-zinc-900' : 'bg-white text-zinc-800 ring-zinc-300')}>
              <input type="radio" name="group" value={v} checked={group === v} onChange={() => setGroup(v)} className="sr-only" />{l}
            </label>
          ))}
        </div>
        <p className="text-sm text-zinc-500">{t('register.groupHint')}</p>
        {show('group') && <p className="text-sm text-red-700">{errors.group}</p>}
      </fieldset>

      <fieldset className="grid gap-2">
        <legend className="mb-2 text-sm font-medium text-zinc-800">{t('register.area')}</legend>
        <div className={cx('h-56 overflow-hidden rounded-xl ring-1', show('pin') ? 'ring-red-500' : 'ring-zinc-200')}>
          <MapContainer center={[23.78, 90.39]} zoom={11} className="h-full w-full" attributionControl>
            <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' />
            <PinPicker pin={pin} setPin={setPin} />
          </MapContainer>
        </div>
        <p className="text-sm text-zinc-500" aria-live="polite">{pin ? t('register.pinSet', { lat: pin[0].toFixed(2), lng: pin[1].toFixed(2) }) : t('register.areaHint')}</p>
        {show('pin') && <p className="text-sm text-red-700">{errors.pin}</p>}
      </fieldset>

      <div className="grid gap-5">
        <Field label={t('register.birthYear')} hint={t('register.birthYearHint')} error={show('birthYear')}>
          {(p) => <input {...p} value={birthYear} onChange={(e) => setBirthYear(e.target.value.replace(/\D/g, '').slice(0, 4))} inputMode="numeric" autoComplete="bday-year" placeholder="1994" className={`${inputCls} h-12 w-32 font-mono text-base`} />}
        </Field>
        <label className="flex items-start gap-3 text-sm text-zinc-800">
          <input type="checkbox" checked={weightOk} onChange={(e) => setWeightOk(e.target.checked)} className="mt-0.5 size-5 accent-brand" />
          <span>{t('register.weight')}</span>
        </label>
      </div>

      <section aria-labelledby="consent-h" className="grid gap-3 rounded-2xl bg-white p-5 ring-1 ring-zinc-200">
        <h2 id="consent-h" className="text-sm font-semibold text-zinc-900">{t('consent.title')} <span className="font-mono text-xs font-normal text-zinc-500">{CONSENT_VERSION}</span></h2>
        <ul className="grid gap-1.5 text-sm leading-relaxed text-zinc-600 list-disc pl-5">
          {(t('consent.points', { returnObjects: true }) as string[]).map((p) => <li key={p}>{p}</li>)}
        </ul>
        <label className="mt-1 flex items-start gap-3 text-sm font-medium text-zinc-900">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} aria-invalid={!!show('consent') || undefined} className="mt-0.5 size-5 accent-brand" />
          <span>{t('consent.agree')}</span>
        </label>
        {show('consent') && <p className="text-sm text-red-700">{errors.consent}</p>}
      </section>

      {m.error && <p role="alert" className="text-sm text-red-700">{m.error instanceof ApiError ? t(`errors.${m.error.code}`, { defaultValue: m.error.message }) : t('errors.generic')}</p>}
      <Button type="submit" variant="primary" size="lg" loading={m.isPending}>{t('register.submit')}</Button>
    </form>
  )
}
