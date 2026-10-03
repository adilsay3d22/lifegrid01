import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Logo } from '../components/Logo'

export function Component() {
  const { t } = useTranslation()
  return (
    <main className="mx-auto grid min-h-[100dvh] max-w-xl content-center gap-6 px-4">
      <Logo />
      <div>
        <p className="font-mono text-sm text-zinc-500">404</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">{t('notFound.title')}</h1>
        <p className="mt-2 text-zinc-600">{t('notFound.body')}</p>
      </div>
      <Link to="/staff/login" className="text-sm font-medium text-brand underline underline-offset-4">{t('notFound.home')}</Link>
    </main>
  )
}
