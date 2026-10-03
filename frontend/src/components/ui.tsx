import { useEffect, useId, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowClockwise, Tray, WarningOctagon, X } from '@phosphor-icons/react'
import type { UseQueryResult } from '@tanstack/react-query'
import { ApiError } from '../api/client'

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
const VARIANTS: Record<Variant, string> = {
  primary: 'bg-brand text-white hover:bg-brand-strong shadow-[inset_0_1px_0_rgb(255_255_255/0.12)]',
  secondary: 'bg-white text-zinc-800 ring-1 ring-inset ring-zinc-300 hover:bg-zinc-50',
  ghost: 'text-zinc-700 hover:bg-zinc-100',
  danger: 'bg-white text-red-800 ring-1 ring-inset ring-red-300 hover:bg-red-50',
}
export function Button({ variant = 'secondary', size = 'md', loading, className, children, disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md' | 'lg'; loading?: boolean }) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-lg font-medium whitespace-nowrap select-none',
        'transition-[background-color,box-shadow,transform] duration-200 ease-out-expo active:scale-[0.98]',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50 disabled:pointer-events-none',
        size === 'sm' ? 'h-8 px-3 text-sm' : size === 'lg' ? 'h-12 px-5 text-base' : 'h-10 px-4 text-sm',
        VARIANTS[variant], className,
      )}
    >
      {loading && <span className="size-3.5 rounded-full border-2 border-current border-r-transparent animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

export const inputCls = 'block w-full h-10 rounded-lg bg-white px-3 text-sm text-zinc-900 ring-1 ring-inset ring-zinc-300 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-brand aria-[invalid=true]:ring-red-500 disabled:bg-zinc-100'

/** Label above, helper and error below (one gap-2 block). Child receives the generated id. */
export function Field({ label, hint, error, children, className }: {
  label: ReactNode; hint?: ReactNode; error?: string; className?: string
  children: (props: { id: string; 'aria-describedby'?: string; 'aria-invalid'?: boolean }) => ReactNode
}) {
  const id = useId()
  const desc = error ? `${id}-err` : hint ? `${id}-hint` : undefined
  return (
    <div className={cx('grid gap-2 content-start', className)}>
      <label htmlFor={id} className="text-sm font-medium text-zinc-800">{label}</label>
      {children({ id, 'aria-describedby': desc, 'aria-invalid': error ? true : undefined })}
      {error ? <p id={`${id}-err`} className="text-sm text-red-700">{error}</p>
        : hint ? <p id={`${id}-hint`} className="text-sm text-zinc-500">{hint}</p> : null}
    </div>
  )
}

export type Tone = 'neutral' | 'brand' | 'good' | 'warn' | 'bad' | 'info'
const TONES: Record<Tone, string> = {
  neutral: 'bg-zinc-100 text-zinc-700 ring-zinc-200',
  brand: 'bg-brand-soft text-brand ring-brand/20',
  good: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  warn: 'bg-amber-50 text-amber-900 ring-amber-200',
  bad: 'bg-red-50 text-red-800 ring-red-200',
  info: 'bg-sky-50 text-sky-800 ring-sky-200',
}
export function Badge({ tone = 'neutral', children, dot }: { tone?: Tone; children: ReactNode; dot?: boolean }) {
  return (
    <span className={cx('inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap', TONES[tone])}>
      {dot && <span className="size-1.5 rounded-full bg-current" aria-hidden />}
      {children}
    </span>
  )
}

export function GroupChip({ label, verified }: { label: string; verified?: boolean }) {
  return (
    <span translate="no" className={cx('inline-flex h-7 min-w-10 items-center justify-center rounded-md px-1.5 text-sm font-semibold',
      verified === false ? 'bg-white text-zinc-700 ring-1 ring-inset ring-dashed ring-zinc-300' : 'bg-zinc-900 text-white')}>
      {label}
    </span>
  )
}

export function PageHeader({ title, description, actions, eyebrow }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between pb-6 border-b border-zinc-200">
      <div className="min-w-0">
        {eyebrow && <p className="mb-1 text-xs font-medium uppercase tracking-wider text-zinc-500">{eyebrow}</p>}
        <h1 className="text-2xl md:text-[1.75rem] font-semibold tracking-tight text-balance text-zinc-950">{title}</h1>
        {description && <p className="mt-1.5 max-w-[65ch] text-sm leading-relaxed text-zinc-600 text-pretty">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2 shrink-0">{actions}</div>}
    </header>
  )
}

export function Skeleton({ rows = 6, className }: { rows?: number; className?: string }) {
  const { t } = useTranslation()
  return (
    <div className={cx('grid gap-3 py-4', className)} role="status" aria-label={t('common.loading')}>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton h-9" style={{ opacity: 1 - i * 0.12 }} />)}
    </div>
  )
}

export function EmptyState({ title, body, action, icon }: { title: string; body?: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-zinc-300 px-6 py-10">
      <span className="grid size-10 place-items-center rounded-lg bg-zinc-100 text-zinc-500">{icon ?? <Tray size={20} />}</span>
      <div>
        <p className="font-medium text-zinc-900">{title}</p>
        {body && <p className="mt-1 max-w-[52ch] text-sm text-zinc-600">{body}</p>}
      </div>
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation()
  const msg = error instanceof ApiError ? t(`errors.${error.code}`, { defaultValue: error.message }) : t('errors.generic')
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-xl border border-red-200 bg-red-50/60 px-6 py-8">
      <span className="flex items-center gap-2 font-medium text-red-900"><WarningOctagon size={20} weight="fill" aria-hidden />{t('errors.title')}</span>
      <p className="text-sm text-red-800">{msg}</p>
      {onRetry && <Button size="sm" onClick={onRetry}><ArrowClockwise size={16} aria-hidden />{t('common.retry')}</Button>}
    </div>
  )
}

/** Renders loading, error and empty states for a query; children get the data. */
export function QueryView<T>({ q, empty, isEmpty, rows, children }: {
  q: UseQueryResult<T>; empty?: ReactNode; isEmpty?: (d: T) => boolean; rows?: number; children: (d: T) => ReactNode
}) {
  if (q.isPending) return <Skeleton rows={rows} />
  // Retrying a 4xx (scope, not found) cannot succeed, so only offer it for server or network failures.
  if (q.isError) return <ErrorState error={q.error} onRetry={q.error instanceof ApiError && q.error.status < 500 ? undefined : () => q.refetch()} />
  const d = q.data as T
  if (empty && (isEmpty ? isEmpty(d) : Array.isArray(d) && d.length === 0)) return <>{empty}</>
  return <>{children(d)}</>
}

export function Dialog({ open, onClose, title, description, children, footer, wide }: {
  open: boolean; onClose: () => void; title: ReactNode; description?: ReactNode; children?: ReactNode; footer?: ReactNode; wide?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const { t } = useTranslation()
  const titleId = useId()
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby={titleId}
      className={cx('m-auto w-[calc(100%-2rem)] rounded-2xl bg-white p-0 text-zinc-900 shadow-[0_24px_48px_-12px_rgb(24_24_27/0.25)] overscroll-contain', wide ? 'max-w-2xl' : 'max-w-lg')}
    >
      {open && (
        <div className="grid gap-5 p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 id={titleId} className="text-lg font-semibold tracking-tight">{title}</h2>
              {description && <p className="mt-1 text-sm text-zinc-600">{description}</p>}
            </div>
            <button type="button" onClick={onClose} aria-label={t('common.close')} className="-m-1 rounded-md p-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-brand">
              <X size={20} aria-hidden />
            </button>
          </div>
          {children}
          {footer && <div className="flex flex-wrap justify-end gap-2 pt-1">{footer}</div>}
        </div>
      )}
    </dialog>
  )
}

export function Segmented<T extends string>({ value, onChange, options, label, size = 'md' }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[]; label: string; size?: 'sm' | 'md'
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg bg-zinc-100 p-1 gap-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx('rounded-md font-medium transition-[background-color,color,box-shadow] duration-200 focus-visible:outline-2 focus-visible:outline-brand',
            size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-8 px-3 text-sm',
            value === o.value ? 'bg-white text-zinc-950 shadow-[0_1px_2px_rgb(24_24_27/0.08)] ring-1 ring-zinc-200' : 'text-zinc-600 hover:text-zinc-900')}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'bad' | 'warn' }) {
  return (
    <div className="min-w-0 px-0 py-4 md:px-6 first:pl-0">
      <dt className="text-xs font-medium uppercase tracking-wider text-zinc-500">{label}</dt>
      <dd className={cx('mt-1 font-mono text-3xl font-medium tabular-nums tracking-tight', tone === 'bad' ? 'text-red-700' : tone === 'warn' ? 'text-amber-700' : 'text-zinc-950')}>{value}</dd>
      {sub && <dd className="mt-0.5 text-sm text-zinc-500">{sub}</dd>}
    </div>
  )
}

export const thCls = 'px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 whitespace-nowrap'
export const tdCls = 'px-3 py-3 align-middle'
