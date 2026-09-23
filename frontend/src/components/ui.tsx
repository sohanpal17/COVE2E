import React from 'react'
import { AlertTriangle, Check, CheckCircle2, Circle, Info, Loader2, XCircle } from 'lucide-react'
import { Link } from 'react-router-dom'

export function Card({ children, className = '', title, subtitle, action }: { children: React.ReactNode; className?: string; title?: React.ReactNode; subtitle?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 px-5 pt-4">
          <div>
            {title && <h3 className="text-sm font-semibold text-ink-900">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-500">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className="card-pad">{children}</div>
    </section>
  )
}

export function PageHeader({ title, subtitle, actions, crumbs }: { title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode; crumbs?: { label: string; to?: string }[] }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {crumbs && (
          <nav className="mb-1 flex items-center gap-1 text-xs text-ink-500">
            {crumbs.map((c, i) => (
              <React.Fragment key={i}>
                {i > 0 && <span>/</span>}
                {c.to ? <Link to={c.to} className="hover:text-brand-600">{c.label}</Link> : <span>{c.label}</span>}
              </React.Fragment>
            ))}
          </nav>
        )}
        <h1 className="text-2xl font-bold text-ink-950">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

const TONES: Record<string, string> = {
  green: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
  red: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
  blue: 'bg-brand-50 text-brand-700 ring-1 ring-brand-200',
  gray: 'bg-ink-100 text-ink-700 ring-1 ring-ink-200',
  purple: 'bg-violet-50 text-violet-700 ring-1 ring-violet-200',
}

export function Badge({ children, tone = 'gray', className = '' }: { children: React.ReactNode; tone?: keyof typeof TONES | string; className?: string }) {
  return <span className={`pill ${TONES[tone] ?? TONES.gray} ${className}`}>{children}</span>
}

export function toneForState(state?: string | null): string {
  switch (state) {
    case 'RESOLVED':
    case 'SETTLED':
    case 'VERIFIED':
    case 'SUCCEEDED':
    case 'HEALTHY':
    case 'COMPLETE':
    case 'VALID':
    case 'SAFE':
    case 'DONE':
    case 'OK':
      return 'green'
    case 'QUERY_RAISED':
    case 'DOCUMENT_PENDING':
    case 'BLOCKED':
    case 'NEEDS_REVIEW':
    case 'ATTENTION':
    case 'CONFIRM':
    case 'PENDING_USER':
    case 'WARNING':
    case 'ISSUE':
    case 'AWAITING_USER':
      return 'amber'
    case 'ESCALATED':
    case 'REJECTED':
    case 'FAILED':
    case 'DENY':
    case 'INVALID':
    case 'CONFLICT':
    case 'MISSING':
      return 'red'
    case 'UNDER_REVIEW':
    case 'SUBMITTED':
    case 'EXECUTING':
    case 'RUNNING':
    case 'READY':
    case 'CURRENT':
    case 'INFO':
      return 'blue'
    case 'APPROVED':
    case 'CLAIM_RESOLUTION':
      return 'purple'
    default:
      return 'gray'
  }
}

export function StatePill({ state }: { state?: string | null }) {
  return <Badge tone={toneForState(state)}>{(state || '—').replace(/_/g, ' ')}</Badge>
}

export function ProgressBar({ value, tone = 'brand', className = '' }: { value: number; tone?: 'brand' | 'green' | 'amber' | 'red'; className?: string }) {
  const color = { brand: 'bg-brand-600', green: 'bg-emerald-500', amber: 'bg-amber-500', red: 'bg-rose-500' }[tone]
  return (
    <div className={`h-2 w-full overflow-hidden rounded-full bg-ink-100 ${className}`}>
      <div className={`h-full rounded-full ${color} transition-all duration-700`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  )
}

export function Spinner({ className = 'h-4 w-4' }: { className?: string }) {
  return <Loader2 className={`animate-spin ${className}`} />
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-ink-500">
      <Spinner /> {label}
    </div>
  )
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
      <XCircle className="mt-0.5 h-4 w-4 shrink-0" /> <span>{message}</span>
    </div>
  )
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-ink-200 bg-white px-6 py-12 text-center">
      <p className="text-sm font-semibold text-ink-800">{title}</p>
      {hint && <p className="mt-1 max-w-md text-xs text-ink-500">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="mt-1 text-lg font-semibold text-ink-900">{value}</div>
      {sub && <div className="text-xs text-ink-500">{sub}</div>}
    </div>
  )
}

export function StatusIcon({ status, className = 'h-4 w-4' }: { status: string; className?: string }) {
  switch (status) {
    case 'DONE':
    case 'OK':
    case 'VALID':
    case 'VERIFIED':
      return <CheckCircle2 className={`${className} text-emerald-500`} />
    case 'WARNING':
    case 'ISSUE':
    case 'NEEDS_REVIEW':
    case 'PENDING_USER':
      return <AlertTriangle className={`${className} text-amber-500`} />
    case 'MISSING':
    case 'FAILED':
    case 'INVALID':
      return <XCircle className={`${className} text-rose-500`} />
    case 'RUNNING':
    case 'EXECUTING':
      return <Loader2 className={`${className} animate-spin text-brand-600`} />
    case 'INFO':
      return <Info className={`${className} text-brand-500`} />
    case 'READY':
    case 'CURRENT':
      return <Circle className={`${className} fill-brand-500 text-brand-500`} />
    default:
      return <Circle className={`${className} text-ink-300`} />
  }
}

export function CheckList({ items }: { items: { label: string; status: string; detail?: string }[] }) {
  return (
    <ul className="space-y-2">
      {items.map((it, i) => (
        <li key={i} className="flex items-start gap-2 text-sm">
          <StatusIcon status={it.status} className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <div className="text-ink-900">{it.label}</div>
            {it.detail && <div className="text-xs text-ink-500">{it.detail}</div>}
          </div>
        </li>
      ))}
    </ul>
  )
}

export function Timeline({ events }: { events: { id: string; description: string; actor: string; created_at: string; to_state?: string | null; event_type: string }[] }) {
  if (!events.length) return <p className="text-sm text-ink-500">No events yet.</p>
  return (
    <ol className="relative ml-2 border-l border-ink-200">
      {events.map((e) => (
        <li key={e.id} className="mb-4 ml-4">
          <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full border border-white bg-brand-500" />
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-500">
            <span>{new Date(e.created_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
            <Badge tone="gray">{e.actor}</Badge>
            {e.to_state && <StatePill state={e.to_state} />}
          </div>
          <p className="mt-0.5 text-sm text-ink-800">{e.description}</p>
        </li>
      ))}
    </ol>
  )
}

export function KeyValue({ items }: { items: { k: string; v: React.ReactNode }[] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map((it) => (
        <div key={it.k}>
          <dt className="label">{it.k}</dt>
          <dd className="mt-0.5 text-sm font-medium text-ink-900">{it.v}</dd>
        </div>
      ))}
    </dl>
  )
}

export function StepRow({ n, label, description, status }: { n: number; label: string; description?: string; status: string }) {
  return (
    <div className="flex items-start gap-3">
      <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${status === 'DONE' ? 'bg-emerald-500 text-white' : status === 'RUNNING' || status === 'READY' ? 'bg-brand-600 text-white' : status === 'FAILED' ? 'bg-rose-500 text-white' : status === 'PENDING_USER' ? 'bg-amber-400 text-white' : 'bg-ink-100 text-ink-600'}`}>
        {status === 'DONE' ? <Check className="h-4 w-4" /> : status === 'RUNNING' ? <Loader2 className="h-4 w-4 animate-spin" /> : n}
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-sm font-medium text-ink-900">
          {label}
          <StatePill state={status} />
        </div>
        {description && <div className="text-xs text-ink-500">{description}</div>}
      </div>
    </div>
  )
}

export function Disclaimer({ children }: { children: React.ReactNode }) {
  return <p className="mt-3 flex items-start gap-1.5 text-xs text-ink-500"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" /> <span>{children}</span></p>
}
