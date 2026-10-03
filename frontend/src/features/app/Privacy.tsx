import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation } from '@tanstack/react-query'
import { DownloadSimple, Trash } from '@phosphor-icons/react'
import { deleteDonorData, exportDonorData } from '../../api/client'
import { Button, Dialog, Field, inputCls } from '../../components/ui'
import { downloadFile } from '../../lib/format'
import { useSession } from '../../session'
import { CONSENT_VERSION } from '../../lib/rules'

/** FR-DON-06: download and delete my data. */
export function Component() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const { refresh } = useSession()
  const [confirming, setConfirming] = useState(false)
  const [typed, setTyped] = useState('')
  const word = t('privacy.confirmWord')
  const exp = useMutation({ mutationFn: exportDonorData, onSuccess: (d) => downloadFile('lifegrid-my-data.json', JSON.stringify(d, null, 2), 'application/json') })
  const del = useMutation({ mutationFn: deleteDonorData, onSuccess: () => { refresh(); nav('/app', { replace: true }) } })

  return (
    <div className="grid gap-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t('privacy.title')}</h1>
        <p className="mt-1 text-sm text-zinc-600">{t('privacy.body')}</p>
      </header>

      <section aria-labelledby="held-h" className="grid gap-3">
        <h2 id="held-h" className="text-base font-semibold tracking-tight">{t('privacy.heldTitle')}</h2>
        <ul className="divide-y divide-zinc-200 border-y border-zinc-200 text-sm">
          {(t('privacy.held', { returnObjects: true }) as string[]).map((h) => <li key={h} className="py-2.5 text-zinc-700">{h}</li>)}
        </ul>
        <p className="text-sm text-zinc-500">{t('privacy.notHeld')}</p>
      </section>

      <section aria-labelledby="consent-h" className="grid gap-2 rounded-2xl bg-white p-5 ring-1 ring-zinc-200">
        <h2 id="consent-h" className="text-sm font-semibold">{t('consent.title')} <span className="font-mono text-xs font-normal text-zinc-500">{CONSENT_VERSION}</span></h2>
        <ul className="grid gap-1.5 list-disc pl-5 text-sm leading-relaxed text-zinc-600">
          {(t('consent.points', { returnObjects: true }) as string[]).map((p) => <li key={p}>{p}</li>)}
        </ul>
      </section>

      <div className="grid gap-3">
        <Button size="lg" loading={exp.isPending} onClick={() => exp.mutate()}><DownloadSimple size={18} aria-hidden />{t('privacy.download')}</Button>
        <Button size="lg" variant="danger" onClick={() => setConfirming(true)}><Trash size={18} aria-hidden />{t('privacy.delete')}</Button>
      </div>

      <Dialog open={confirming} onClose={() => { setConfirming(false); setTyped('') }} title={t('privacy.deleteTitle')} description={t('privacy.deleteBody')}
        footer={<>
          <Button variant="ghost" onClick={() => { setConfirming(false); setTyped('') }}>{t('common.cancel')}</Button>
          <Button variant="danger" disabled={typed.trim().toUpperCase() !== word.toUpperCase()} loading={del.isPending} onClick={() => del.mutate()}>{t('privacy.deleteConfirm')}</Button>
        </>}>
        <Field label={t('privacy.typeToConfirm', { word })}>
          {(p) => <input {...p} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} className={`${inputCls} font-mono uppercase`} />}
        </Field>
      </Dialog>
    </div>
  )
}
