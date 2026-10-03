import i18n from '../i18n'

// Times stored UTC, shown in the site zone (spec section 10). One zone for the demo region.
const TZ = 'Asia/Dhaka'
const fmt = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(i18n.language, { timeZone: TZ, ...o })
export const fmtDate = (s: string) => fmt({ day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(s))
export const fmtDateTime = (s: string) => fmt({ day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(s))
export const fmtTime = (s: string) => fmt({ hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(s))
export const fmtNum = (n: number, digits = 0) => new Intl.NumberFormat(i18n.language, { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(n)
export const fmtPct = (n: number) => new Intl.NumberFormat(i18n.language, { style: 'percent', maximumFractionDigits: 1 }).format(n)

const rtf = () => new Intl.RelativeTimeFormat(i18n.language, { numeric: 'auto' })
export function fmtRelative(s: string) {
  const diff = Date.parse(s) - Date.now()
  const abs = Math.abs(diff)
  if (abs < 3_600_000) return rtf().format(Math.round(diff / 60_000), 'minute')
  if (abs < 86_400_000) return rtf().format(Math.round(diff / 3_600_000), 'hour')
  return rtf().format(Math.round(diff / 86_400_000), 'day')
}
export const daysUntil = (s: string) => (Date.parse(s) - Date.now()) / 86_400_000

export function downloadFile(name: string, body: string, type: string) {
  const url = URL.createObjectURL(new Blob([body], { type }))
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  a.click()
  URL.revokeObjectURL(url)
}
export function toCsv(rows: Record<string, string | number>[]) {
  if (!rows.length) return ''
  const keys = Object.keys(rows[0])
  const esc = (v: unknown) => (/[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v))
  return [keys.join(','), ...rows.map((r) => keys.map((k) => esc(r[k])).join(','))].join('\n')
}
