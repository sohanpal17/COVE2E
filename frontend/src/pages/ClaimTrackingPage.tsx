import React from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, Check, FileText, HelpCircle, RefreshCw, Search } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import type { TrackingStage } from '../types/api'
import { useI18n } from '../i18n'
import { Badge, Card, ErrorBox, Loading, PageHeader, StatePill, Timeline } from '../components/ui'
import { fmtDate, inr, relDays, titleCase } from '../utils/format'

const DOC_LABELS: Record<string, string> = {
  policy_copy: 'Policy copy', id_proof: 'Identity proof', claim_form: 'Claim form', hospital_bill: 'Hospital bill', discharge_summary: 'Discharge summary', medical_certificate: 'Medical certificate',
  prescription: 'Prescription', diagnostic_report: 'Diagnostic report', driving_license: 'Driving license', rc_copy: 'RC copy', fir_copy: 'FIR copy', repair_estimate: 'Repair estimate',
  damage_photos: 'Damage photos', purchase_invoice: 'Purchase invoice', other: 'Other',
}
const docLabel = (type: string | null | undefined) => (type ? DOC_LABELS[type] ?? titleCase(type) : '')

function StageDot({ status }: { status: TrackingStage['status'] }) {
  switch (status) {
    case 'DONE':
      return <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-500 text-white ring-4 ring-white"><Check className="h-4 w-4" /></span>
    case 'CURRENT':
      return <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 ring-4 ring-brand-100"><span className="h-2.5 w-2.5 rounded-full bg-white" /></span>
    case 'BLOCKED':
      return <span className="flex h-7 w-7 items-center justify-center rounded-full bg-amber-400 text-white ring-4 ring-amber-100"><AlertTriangle className="h-4 w-4" /></span>
    default:
      return <span className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-ink-300 bg-white ring-4 ring-white" />
  }
}

export default function ClaimTrackingPage() {
  const { id = '' } = useParams()
  const { t } = useI18n()
  const q = useQuery({ queryKey: ['tracking', id], queryFn: () => api.tracking(id), enabled: !!id })

  if (q.isLoading) return <Loading label={t('common.loading')} />
  if (q.isError) return <ErrorBox message={errorMessage(q.error)} />
  const tr = q.data
  if (!tr) return <ErrorBox message="Tracking unavailable" />
  const claim = tr.claim

  return (
    <div>
      <PageHeader
        crumbs={[{ label: t('nav.claims'), to: '/claims' }, { label: claim.claim_number, to: `/claims/${claim.id}` }, { label: t('claim.tracking') }]}
        title={<span>CLAIM <span className="mono">#{claim.claim_number}</span></span>}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span>{titleCase(claim.incident_type)} · {titleCase(claim.claim_type)} · {inr(claim.claimed_amount)}</span>
            {claim.external_claim_id && <span>· Insurer reference <span className="mono font-semibold text-ink-700">{claim.external_claim_id}</span></span>}
            {claim.submitted_at && <span>· submitted {fmtDate(claim.submitted_at)}</span>}
          </span>
        }
        actions={
          <>
            <button className="btn-ghost" onClick={() => q.refetch()}><RefreshCw className={`h-4 w-4 ${q.isFetching ? 'animate-spin' : ''}`} /> Refresh</button>
            <Link to={`/claims/${claim.id}/documents`} className="btn-secondary"><FileText className="h-4 w-4" /> Documents</Link>
            {claim.journey_id && (
              <Link to={`/journeys/${claim.journey_id}/investigation`} className="btn-primary"><HelpCircle className="h-4 w-4" /> Why is my claim stuck?</Link>
            )}
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <Card title="Claim progress" subtitle="Where this claim sits in the end-to-end journey.">
            <ol className="relative ml-3.5">
              {tr.stages.map((s, i) => {
                const last = i === tr.stages.length - 1
                const lineColor = s.status === 'DONE' ? 'bg-emerald-400' : 'bg-ink-200'
                return (
                  <li key={s.key} className="relative flex items-start gap-4 pb-6 last:pb-0">
                    {!last && <span className={`absolute left-[13px] top-7 h-[calc(100%-28px)] w-0.5 ${lineColor}`} />}
                    <div className="relative z-10 -ml-0"><StageDot status={s.status} /></div>
                    <div className="min-w-0 pt-1">
                      <div className={`text-sm font-semibold ${s.status === 'CURRENT' ? 'text-brand-700' : s.status === 'BLOCKED' ? 'text-amber-700' : s.status === 'DONE' ? 'text-ink-900' : 'text-ink-400'}`}>{s.label}</div>
                      <div className="text-[11px] uppercase tracking-wider text-ink-400">{s.status === 'DONE' ? 'Completed' : s.status === 'CURRENT' ? 'In progress' : s.status === 'BLOCKED' ? 'Blocked' : 'Pending'}</div>
                    </div>
                  </li>
                )
              })}
            </ol>
          </Card>
        </div>

        <div className="space-y-6 lg:col-span-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <Card title="Current state">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-lg font-semibold text-ink-900">{tr.current_state_label}</span>
                <StatePill state={tr.current_state} />
              </div>
              {claim.external_status && <div className="mt-2 text-xs text-ink-500">Insurer status: <StatePill state={claim.external_status} /></div>}
            </Card>
            <Card title="User action required">
              <div className="flex items-center gap-2">
                {tr.user_action_required ? <Badge tone="amber">Yes — action needed from you</Badge> : <Badge tone="green">No — nothing needed right now</Badge>}
              </div>
              <div className="mt-3">
                <div className="label">Next step</div>
                <p className="mt-0.5 text-sm text-ink-900">{tr.next_step || '—'}</p>
              </div>
            </Card>
            <Card title="What happened">
              <p className="text-sm text-ink-800">{tr.what_happened || '—'}</p>
            </Card>
            <Card title="What is pending">
              <p className="text-sm text-ink-800">{tr.what_is_pending || '—'}</p>
            </Card>
          </div>

          {tr.open_queries.length > 0 && (
            <Card title="Open insurer queries" subtitle="The insurer is waiting on these before the claim can move." className="border-amber-200">
              <ul className="space-y-2">
                {tr.open_queries.map((oq) => (
                  <li key={oq.id} className="rounded-lg border border-amber-200 bg-amber-50/70 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-xs font-semibold text-amber-800"><AlertTriangle className="h-3.5 w-3.5" /> Query raised {relDays(oq.raised_at) || fmtDate(oq.raised_at)}</span>
                      <StatePill state={oq.status} />
                    </div>
                    <p className="mt-1.5 text-sm text-ink-900">{oq.message}</p>
                    {oq.requested_document_type && (
                      <div className="mt-2 flex items-center gap-2 text-xs text-ink-700">
                        Requested: <Badge tone="amber">{docLabel(oq.requested_document_type)}</Badge>
                        <Link to={`/claims/${claim.id}/documents`} className="inline-flex items-center gap-1 font-semibold text-brand-700 hover:underline">Upload now <ArrowRight className="h-3 w-3" /></Link>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card title="Timeline" subtitle={`${tr.timeline.length} event${tr.timeline.length === 1 ? '' : 's'}`}>
            <Timeline events={tr.timeline} />
          </Card>

          <div className="flex flex-wrap items-center gap-2">
            {claim.journey_id && <Link to={`/journeys/${claim.journey_id}/investigation`} className="btn-secondary"><Search className="h-4 w-4" /> Why is my claim stuck?</Link>}
            <Link to={`/claims/${claim.id}/documents`} className="btn-secondary"><FileText className="h-4 w-4" /> Documents</Link>
            <Link to={`/claims/${claim.id}`} className="btn-ghost">Claim details <ArrowRight className="h-4 w-4" /></Link>
          </div>
        </div>
      </div>
    </div>
  )
}
