import { useTranslation } from 'react-i18next'

export function Logo({ compact }: { compact?: boolean }) {
  const { t } = useTranslation()
  return (
    <span className="flex items-center gap-2.5" translate="no">
      <svg viewBox="0 0 64 64" className="size-7 shrink-0" aria-hidden>
        <rect width="64" height="64" rx="14" fill="var(--color-brand)" />
        <path d="M32 12c-7 10-14 18-14 27a14 14 0 0 0 28 0c0-9-7-17-14-27z" fill="#fafafa" />
        <path d="M24 40h16M32 32v16" stroke="var(--color-brand)" strokeWidth="4" strokeLinecap="round" />
      </svg>
      <span className="leading-none">
        <span className="block text-[15px] font-semibold tracking-tight text-zinc-950">{t('app.name')}</span>
        {!compact && <span className="mt-0.5 block text-[11px] text-zinc-500">{t('app.tagline')}</span>}
      </span>
    </span>
  )
}
