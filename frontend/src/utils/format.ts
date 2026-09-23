export const inr = (v: number | null | undefined) =>
  v == null ? '—' : new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v)

export const fmtDate = (iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', year: 'numeric' }) =>
  iso ? new Date(iso).toLocaleDateString('en-IN', opts) : '—'

export const fmtDateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'

export const relDays = (iso: string | null | undefined) => {
  if (!iso) return ''
  const days = Math.round((Date.now() - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return 'today'
  if (days === 1) return '1 day ago'
  return `${days} days ago`
}

export const titleCase = (s: string | null | undefined) =>
  (s || '').replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())

export const stateLabel = (s: string | null | undefined) => (s || '').replace(/_/g, ' ')

export const pct = (n: number) => `${Math.round(n)}%`

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
