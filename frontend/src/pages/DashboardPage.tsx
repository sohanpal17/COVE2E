import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, CalendarClock, Database, FileSearch, HeartPulse, MapPin, Plus, ShieldCheck } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import { useI18n } from '../i18n'
import { fmtDate, inr, pct, titleCase } from '../utils/format'
import { Badge, Card, EmptyState, ErrorBox, Loading, PageHeader, ProgressBar, Spinner, StatePill, toneForState } from '../components/ui'
import AskCove2e from '../components/AskCove2e'
import type { IntegrationStatus } from '../types/api'

function claimHealthLine(status: string): string {
  switch (status) {
    case 'DOCUMENT_PENDING':
      return 'Insurer is waiting for a document — action required'
    case 'UNDER_REVIEW':
      return 'No action currently required.'
    case 'DRAFT':
      return 'Not yet submitted'
    case 'APPROVED':
      return 'Decision recorded; settlement in progress'
    case 'QUERY_RAISED':
      return 'Insurer raised a query — investigate the journey'
    case 'SUBMITTED':
      return 'Submitted to insurer; awaiting acknowledgement'
    case 'SETTLED':
      return 'Settled and paid'
    case 'REJECTED':
      return 'Rejected by insurer — review escalation options'
    default:
      return titleCase(status)
  }
}

function severityTone(sev: string): string {
  const s = sev.toUpperCase()
  if (s === 'HIGH' || s === 'CRITICAL') return 'red'
  if (s === 'MEDIUM') return 'amber'
  return 'blue'
}

function IntegrationsStrip({ data }: { data: IntegrationStatus }) {
  const items = [
    { label: 'Sarvam AI', ok: !!data.sarvam?.configured, text: data.sarvam?.configured ? 'connected' : 'deterministic fallback' },
    { label: 'Cognee', ok: !!data.cognee?.available, text: data.cognee?.available ? 'graph' : 'local fallback' },
    { label: 'n8n', ok: !!data.n8n?.reachable, text: data.n8n?.reachable ? 'reachable' : 'demo fallback' },
    { label: 'Database', ok: true, text: String(data.database?.dialect ?? 'unknown') },
  ]
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-ink-200 bg-white px-4 py-2.5 text-xs text-ink-500">
      <span className="label">Integrations</span>
      {items.map((it) => (
        <Badge key={it.label} tone={it.ok ? 'green' : 'amber'}>{it.label}: {it.text}</Badge>
      ))}
      {data.demo_mode && <Badge tone="amber">Demo mode</Badge>}
    </div>
  )
}

export default function DashboardPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard })
  const [toast, setToast] = useState<string | null>(null)

  const loadDemo = useMutation({
    mutationFn: api.loadDemo,
    onSuccess: (res) => {
      setToast(`${res.message} · Claim ${res.claim_number}`)
      qc.invalidateQueries()
      setTimeout(() => setToast(null), 6000)
    },
  })

  if (isLoading) return <Loading label={t('common.loading')} />
  if (error || !data) return <ErrorBox message={errorMessage(error)} />

  const greetingFirstLine = data.greeting.split('\n')[0]

  return (
    <div>
      <PageHeader
        title={t('nav.dashboard')}
        subtitle={greetingFirstLine}
        actions={
          <>
            <button className="btn-secondary" onClick={() => loadDemo.mutate()} disabled={loadDemo.isPending}>
              {loadDemo.isPending ? <Spinner /> : <Database className="h-4 w-4" />} {t('login.loadDemo')}
            </button>
            <button className="btn-primary" onClick={() => navigate('/incidents')}>
              <Plus className="h-4 w-4" /> Start a claim
            </button>
          </>
        }
      />

      {toast && <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{toast}</div>}
      {loadDemo.error && <div className="mb-4"><ErrorBox message={errorMessage(loadDemo.error)} /></div>}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title={t('dash.coverage')} action={<Link to="/policies" className="text-xs font-semibold text-brand-700 hover:underline">{t('common.viewAll')}</Link>}>
            {data.policies.length === 0 ? (
              <EmptyState title="No policies yet" hint="Upload a policy PDF to build your coverage profile and knowledge layer." action={<Link to="/policies" className="btn-primary">Upload policy</Link>} />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {data.policies.map((p) => (
                  <Link key={p.id} to={`/policies/${p.id}`} className="rounded-xl border border-ink-200 p-4 transition hover:border-brand-300 hover:shadow-card">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate text-xs text-ink-500">{p.insurer}</div>
                        <div className="truncate text-sm font-semibold text-ink-900">{p.plan_name}</div>
                      </div>
                      <Badge tone="blue">{p.policy_type}</Badge>
                    </div>
                    <div className="mt-3 text-lg font-bold text-ink-950">{inr(p.sum_insured)}</div>
                    <div className="text-xs text-ink-500">
                      Expires {fmtDate(p.end_date)}
                      {p.days_to_expiry != null && <span className={p.days_to_expiry < 30 ? ' text-amber-600' : ''}> · {p.days_to_expiry} days</span>}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5 text-[11px] text-ink-600">
                      <Badge tone="gray">Deductible {inr(p.deductible)}</Badge>
                      <Badge tone="gray">Waiting {p.waiting_period_days}d</Badge>
                      {p.claim_types.map((ct) => (
                        <Badge key={ct} tone="gray">{titleCase(ct)}</Badge>
                      ))}
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </Card>

          <Card title={t('dash.journeys')} action={<Link to="/journeys" className="text-xs font-semibold text-brand-700 hover:underline">{t('common.viewAll')}</Link>}>
            {data.journeys.length === 0 ? (
              <EmptyState title="No journeys yet" hint="Start a claim and COVE2E will track the journey end-to-end." />
            ) : (
              <ul className="divide-y divide-ink-100">
                {data.journeys.map((j) => (
                  <li key={j.id} className="py-3 first:pt-0 last:pb-0">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-ink-900">{j.title}</span>
                        <StatePill state={j.current_state} />
                        <Badge tone={toneForState(j.health)}>{j.health}</Badge>
                      </div>
                      <div className="flex items-center gap-2">
                        <button className="btn-secondary !px-3 !py-1 text-xs" onClick={() => navigate(`/journeys/${j.id}/investigation`)}>
                          <FileSearch className="h-3.5 w-3.5" /> Investigate
                        </button>
                        {j.claim_id && (
                          <button className="btn-ghost !px-3 !py-1 text-xs" onClick={() => navigate(`/claims/${j.claim_id}/tracking`)}>
                            <MapPin className="h-3.5 w-3.5" /> Track
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="mt-2 flex items-center gap-3">
                      <ProgressBar value={j.progress_percent} tone={j.health === 'BLOCKED' || j.health === 'ESCALATED' ? 'amber' : j.health === 'COMPLETE' ? 'green' : 'brand'} className="flex-1" />
                      <span className="w-24 text-right text-xs text-ink-500">{pct(j.progress_percent)} complete</span>
                    </div>
                    {j.outstanding_requirements.length > 0 && (
                      <div className="mt-1.5 text-xs text-amber-700">Outstanding: {j.outstanding_requirements.map(titleCase).join(', ')}</div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title={t('dash.ask')} subtitle="Context-aware: knows your policies, claims and journeys">
            <AskCove2e greeting={data.greeting} />
          </Card>
        </div>

        <div className="space-y-6">
          <Card title={t('dash.actionRequired')}>
            {data.action_required.length === 0 ? (
              <p className="flex items-center gap-2 text-sm text-ink-500"><ShieldCheck className="h-4 w-4 text-emerald-500" /> {t('dash.noAction')}</p>
            ) : (
              <ul className="space-y-3">
                {data.action_required.map((a, i) => (
                  <li key={i} className="rounded-lg border border-amber-200 bg-amber-50/60 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-2">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                        <div>
                          <div className="text-sm font-semibold text-ink-900">{a.title}</div>
                          <div className="text-xs text-ink-600">{a.detail}</div>
                        </div>
                      </div>
                      <Badge tone={severityTone(a.severity)}>{a.severity}</Badge>
                    </div>
                    <Link to={a.link} className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:underline">
                      {t('common.open')} <ArrowRight className="h-3 w-3" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title={t('dash.health')}>
            {data.claims.length === 0 ? (
              <p className="text-sm text-ink-500">No claims yet.</p>
            ) : (
              <ul className="space-y-3">
                {data.claims.map((c) => (
                  <li key={c.id}>
                    <div className="flex items-center justify-between gap-2">
                      <Link to={`/claims/${c.id}`} className="mono font-semibold text-ink-900 hover:text-brand-700">{c.claim_number}</Link>
                      <StatePill state={c.status} />
                    </div>
                    <p className="mt-0.5 flex items-start gap-1.5 text-xs text-ink-600">
                      <HeartPulse className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-400" /> {claimHealthLine(c.status)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title={t('dash.dates')}>
            {data.important_dates.length === 0 ? (
              <p className="text-sm text-ink-500">Nothing scheduled.</p>
            ) : (
              <ul className="space-y-3">
                {data.important_dates.map((d, i) => {
                  const overdue = d.days_from_now < 0
                  const rel = overdue ? `${Math.abs(d.days_from_now)} days overdue` : d.days_from_now === 0 ? 'today' : `in ${d.days_from_now} days`
                  const to = d.claim_id ? `/claims/${d.claim_id}` : d.policy_id ? `/policies/${d.policy_id}` : null
                  const body = (
                    <div className="flex items-start gap-2">
                      <CalendarClock className={`mt-0.5 h-4 w-4 shrink-0 ${overdue ? 'text-rose-500' : 'text-brand-500'}`} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-sm font-medium text-ink-900">{d.label}</span>
                          <Badge tone="gray">{titleCase(d.kind)}</Badge>
                        </div>
                        <div className="text-xs text-ink-500">
                          {fmtDate(d.date)} · <span className={overdue ? 'font-semibold text-rose-600' : ''}>{rel}</span>
                        </div>
                      </div>
                    </div>
                  )
                  return <li key={i}>{to ? <Link to={to} className="block rounded-lg hover:bg-ink-50">{body}</Link> : body}</li>
                })}
              </ul>
            )}
          </Card>

          {data.suggested_actions.length > 0 && (
            <Card title="Suggested next steps">
              <ul className="space-y-1.5">
                {data.suggested_actions.map((s) => (
                  <li key={s.key}>
                    <Link to={s.link} className="flex items-center justify-between rounded-lg px-2 py-1.5 text-sm text-ink-700 hover:bg-ink-50 hover:text-brand-700">
                      {s.label} <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>

      <div className="mt-6">
        <IntegrationsStrip data={data.integrations} />
      </div>
    </div>
  )
}
