import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { RequestForm } from '../requests/RequestForm'

export function Component() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const qc = useQueryClient()
  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t('appNav.newRequest')}</h1>
        <p className="mt-1 text-sm text-zinc-600">{t('newRequest.body')}</p>
      </header>
      <RequestForm compact onCreated={(r) => { qc.invalidateQueries({ queryKey: ['requests'] }); nav(`/app/requests/${r.id}`) }} />
    </div>
  )
}
