import React from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Activity, FileText, FolderOpen, Gauge, Plus, Search } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import type { ClaimSummary } from '../types/api'
import { useI18n } from '../i18n'
import { Badge, Card, EmptyState, ErrorBox, Loading, PageHeader, StatePill } from '../components/ui'
import { fmtDate, inr, titleCase } from '../utils/format'

function scenarioTone(s: string): string {
  switch (s) {
    case 'STUCK_CLAIM':
    case 'CONFLICTING_STATE':
      return 'red'
    case 'DOCUMENT_INCONSISTENCY':
    case 'MISSING_DOCUMENT':
      return 'amber'
    case 'NORMAL':
      return 'green'
    default:
      return 'gray'
  }
}

function RowActions({ c }: { c: ClaimSummary }) {
  const { t } = useI18n()
  const base = `/claims/${c.id}`
  const cls = 'inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold text-ink-700 hover:bg-ink-100 hover:text-brand-700'
  return (
    <div className="flex flex-wrap items-center gap-0.5">
      <Link to={base} className={cls}><FolderOpen className="h-3.5 w-3.5" /> {t('common.open')}</Link>
      <Link to={`${base}/documents`} className={cls}><FileText className="h-3.5 w-3.5" /> Documents</Link>
      <Link to={`${base}/readiness`} className={cls}><Gauge className="h-3.5 w-3.5" /> Readiness</Link>
      <Link to={`${base}/tracking`} className={cls}><Activity className="h-3.5 w-3.5" /> Tracking</Link>
      {c.journey_id && (
        <Link to={`/journeys/${c.journey_id}/investigation`} className={`${cls} text-amber-700 hover:text-amber-800`}><Search className="h-3.5 w-3.5" /> Investigate</Link>
      )}
    </div>
  )
}

export default function ClaimsPage() {
  const { t } = useI18n()
  const q = useQuery({ queryKey: ['claims'], queryFn: api.claims })

  const claims = q.data ?? []
  const counts = {
    total: claims.length,
    submitted: claims.filter((c) => !!c.submitted_at).length,
    attention: claims.filter((c) => c.scenario && c.scenario !== 'NORMAL').length,
  }

  return (
    <div>
      <PageHeader
        title={t('nav.claims')}
        subtitle="Every claim you have started, with its insurer state, readiness and where it sits in the journey."
        crumbs={[{ label: t('nav.dashboard'), to: '/dashboard' }, { label: t('nav.claims') }]}
        actions={<Link to="/incidents" className="btn-primary"><Plus className="h-4 w-4" /> New claim</Link>}
      />

      {q.isLoading && <Loading label={t('common.loading')} />}
      {q.isError && <ErrorBox message={errorMessage(q.error)} />}

      {q.data && claims.length === 0 && (
        <EmptyState
          title="No claims yet"
          hint="Start by describing what happened. COVE2E will map the incident to your policy and guide you through the documents."
          action={<Link to="/incidents" className="btn-primary"><Plus className="h-4 w-4" /> Describe an incident</Link>}
        />
      )}

      {claims.length > 0 && (
        <>
          <div className="mb-4 grid grid-cols-3 gap-3">
            <div className="card px-4 py-3"><div className="label">Total claims</div><div className="mt-1 text-xl font-bold text-ink-900">{counts.total}</div></div>
            <div className="card px-4 py-3"><div className="label">Submitted to insurer</div><div className="mt-1 text-xl font-bold text-ink-900">{counts.submitted}</div></div>
            <div className="card px-4 py-3"><div className="label">Needs attention</div><div className={`mt-1 text-xl font-bold ${counts.attention ? 'text-amber-600' : 'text-ink-900'}`}>{counts.attention}</div></div>
          </div>

          <Card className="overflow-hidden" title="All claims" subtitle={`${claims.length} claim${claims.length === 1 ? '' : 's'}`}>
            <div className="-mx-5 -mb-5 overflow-x-auto">
              <table className="w-full min-w-[900px] text-left text-sm">
                <thead className="bg-ink-50 text-[11px] uppercase tracking-wider text-ink-500">
                  <tr>
                    <th className="px-5 py-2.5 font-semibold">Claim</th>
                    <th className="px-3 py-2.5 font-semibold">Incident</th>
                    <th className="px-3 py-2.5 font-semibold">Type</th>
                    <th className="px-3 py-2.5 font-semibold">Status</th>
                    <th className="px-3 py-2.5 font-semibold">Insurer status</th>
                    <th className="px-3 py-2.5 text-right font-semibold">Amount</th>
                    <th className="px-3 py-2.5 font-semibold">Submitted</th>
                    <th className="px-3 py-2.5 font-semibold">Scenario</th>
                    <th className="px-3 py-2.5 font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  {claims.map((c) => (
                    <tr key={c.id} className="hover:bg-ink-50/60">
                      <td className="px-5 py-3">
                        <Link to={`/claims/${c.id}`} className="mono font-semibold text-brand-700 hover:underline">{c.claim_number}</Link>
                        {c.external_claim_id && <div className="mono text-[11px] text-ink-400">ref {c.external_claim_id}</div>}
                      </td>
                      <td className="px-3 py-3 text-ink-800">{titleCase(c.incident_type)}</td>
                      <td className="px-3 py-3 text-ink-800">{titleCase(c.claim_type)}</td>
                      <td className="px-3 py-3"><StatePill state={c.status} /></td>
                      <td className="px-3 py-3">{c.external_status ? <StatePill state={c.external_status} /> : <span className="text-xs text-ink-400">—</span>}</td>
                      <td className="px-3 py-3 text-right font-medium text-ink-900">{inr(c.claimed_amount)}</td>
                      <td className="px-3 py-3 text-ink-700">{c.submitted_at ? fmtDate(c.submitted_at) : <span className="text-ink-400">Not submitted</span>}</td>
                      <td className="px-3 py-3">{c.scenario ? <Badge tone={scenarioTone(c.scenario)}>{titleCase(c.scenario)}</Badge> : <span className="text-xs text-ink-400">—</span>}</td>
                      <td className="px-3 py-3"><RowActions c={c} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
