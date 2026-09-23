import React from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, Building2, FileText, Gauge, Search } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import type { ClaimDetail } from '../types/api'
import { useI18n } from '../i18n'
import { Badge, Card, ErrorBox, KeyValue, Loading, PageHeader, StatePill } from '../components/ui'
import { fmtDate, fmtDateTime, inr, relDays, titleCase } from '../utils/format'

const DOC_LABELS: Record<string, string> = {
  policy_copy: 'Policy copy',
  id_proof: 'Identity proof',
  claim_form: 'Claim form',
  hospital_bill: 'Hospital bill',
  discharge_summary: 'Discharge summary',
  medical_certificate: 'Medical certificate',
  prescription: 'Prescription',
  diagnostic_report: 'Diagnostic report',
  driving_license: 'Driving license',
  rc_copy: 'RC copy',
  fir_copy: 'FIR copy',
  repair_estimate: 'Repair estimate',
  damage_photos: 'Damage photos',
  purchase_invoice: 'Purchase invoice',
  other: 'Other',
}
const docLabel = (type: string | null | undefined) => (type ? DOC_LABELS[type] ?? titleCase(type) : '—')

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

function InsurerView({ externalId }: { externalId: string }) {
  const q = useQuery({ queryKey: ['insurer-claim', externalId], queryFn: () => api.insurerClaim(externalId) })
  if (q.isLoading) return <Loading label="Reading insurer system…" />
  if (q.isError) return <ErrorBox message={errorMessage(q.error)} />
  const d = q.data ?? {}
  const openQueries = Array.isArray(d.open_queries) ? d.open_queries.length : typeof d.open_queries === 'number' ? d.open_queries : Array.isArray(d.queries) ? d.queries.filter((x: { status?: string }) => x?.status !== 'RESOLVED').length : 0
  const docs = Array.isArray(d.documents) ? d.documents.length : typeof d.documents_count === 'number' ? d.documents_count : 0
  return (
    <>
      {d.conflict ? (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-sm text-rose-700">
          <AlertTriangle className="h-4 w-4 shrink-0" /> <Badge tone="red">State conflict</Badge> Insurer state differs from what COVE2E recorded.
        </div>
      ) : null}
      <KeyValue
        items={[
          { k: 'Insurer status', v: <StatePill state={typeof d.status === 'string' ? d.status : null} /> },
          { k: 'Settlement', v: <StatePill state={typeof d.settlement_status === 'string' ? d.settlement_status : null} /> },
          { k: 'Payment', v: <StatePill state={typeof d.payment_status === 'string' ? d.payment_status : null} /> },
          { k: 'Open queries', v: <span className={openQueries ? 'text-amber-700' : ''}>{openQueries}</span> },
          { k: 'Documents on file', v: docs },
          { k: 'Reference', v: <span className="mono">{externalId}</span> },
        ]}
      />
    </>
  )
}

export default function ClaimDetailPage() {
  const { id = '' } = useParams()
  const { t } = useI18n()
  const q = useQuery({ queryKey: ['claim', id], queryFn: () => api.claim(id), enabled: !!id })

  if (q.isLoading) return <Loading label={t('common.loading')} />
  if (q.isError) return <ErrorBox message={errorMessage(q.error)} />
  const c: ClaimDetail | undefined = q.data
  if (!c) return <ErrorBox message="Claim not found" />

  const base = `/claims/${c.id}`

  return (
    <div>
      <PageHeader
        crumbs={[{ label: t('nav.claims'), to: '/claims' }, { label: c.claim_number }]}
        title={
          <span className="flex flex-wrap items-center gap-2">
            <span className="mono text-2xl">{c.claim_number}</span>
            <StatePill state={c.status} />
            {c.scenario && c.scenario !== 'NORMAL' && <Badge tone={scenarioTone(c.scenario)}>{titleCase(c.scenario)}</Badge>}
          </span>
        }
        subtitle={`${titleCase(c.incident_type)} · ${titleCase(c.claim_type)} · created ${fmtDate(c.created_at)}`}
        actions={
          <>
            <Link to={`${base}/documents`} className="btn-secondary"><FileText className="h-4 w-4" /> Documents</Link>
            <Link to={`${base}/readiness`} className="btn-secondary"><Gauge className="h-4 w-4" /> Readiness</Link>
            <Link to={`${base}/tracking`} className="btn-secondary"><Activity className="h-4 w-4" /> Tracking</Link>
            {c.journey_id && <Link to={`/journeys/${c.journey_id}/investigation`} className="btn-primary"><Search className="h-4 w-4" /> Investigate</Link>}
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Claim details">
            <KeyValue
              items={[
                { k: 'Policy', v: c.policy ? <span>{c.policy.plan_name} <span className="mono text-ink-500">· {c.policy.policy_number}</span></span> : '—' },
                { k: 'Claim type', v: titleCase(c.claim_type) },
                { k: 'Incident type', v: titleCase(c.incident_type) },
                { k: 'Incident date / time', v: `${fmtDate(c.incident_date)}${c.incident_time ? ` · ${c.incident_time}` : ''}` },
                { k: 'Location', v: c.location || '—' },
                { k: 'Affected asset', v: c.affected_asset || '—' },
                { k: 'People involved', v: c.people_involved || '—' },
                { k: 'Claimed amount', v: inr(c.claimed_amount) },
                { k: 'Insurer reference', v: c.external_claim_id ? <span className="mono">{c.external_claim_id}</span> : 'Not submitted' },
                { k: 'External status', v: <StatePill state={c.external_status} /> },
                { k: 'Settlement status', v: <StatePill state={c.settlement_status} /> },
                { k: 'Payment status', v: <StatePill state={c.payment_status} /> },
                { k: 'Submitted at', v: c.submitted_at ? fmtDateTime(c.submitted_at) : 'Not submitted' },
              ]}
            />
            {c.incident_description && (
              <div className="mt-4 border-t border-ink-100 pt-3">
                <div className="label">Incident description</div>
                <p className="mt-1 text-sm text-ink-800">{c.incident_description}</p>
              </div>
            )}
          </Card>

          <Card title="Requirements checklist" subtitle={`${c.requirements.filter((r) => r.status === 'DONE' || r.status === 'FULFILLED').length}/${c.requirements.length} fulfilled`} action={<Link to={`${base}/documents`} className="text-xs font-semibold text-brand-700 hover:underline">{t('claim.documents')}</Link>}>
            {c.requirements.length === 0 ? (
              <p className="text-sm text-ink-500">No requirements recorded.</p>
            ) : (
              <ul className="divide-y divide-ink-100">
                {c.requirements.map((r) => (
                  <li key={r.id} className={`flex flex-wrap items-center gap-2 py-2.5 ${r.source === 'INSURER_QUERY' ? '-mx-2 rounded-lg bg-amber-50/70 px-2' : ''}`}>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-ink-900">{r.label || docLabel(r.document_type)}</div>
                      {r.description && <div className="text-xs text-ink-500">{r.description}</div>}
                    </div>
                    <Badge tone={r.required ? 'blue' : 'gray'}>{r.required ? 'Required' : 'Optional'}</Badge>
                    {r.source === 'INSURER_QUERY' ? <Badge tone="amber">Requested by insurer</Badge> : <Badge tone="gray">{titleCase(r.source)}</Badge>}
                    <StatePill state={r.status} />
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Documents" subtitle={`${c.documents.length} uploaded`}>
            {c.documents.length === 0 ? (
              <p className="text-sm text-ink-500">No documents uploaded yet. <Link to={`${base}/documents`} className="font-semibold text-brand-700 hover:underline">Open the Document Center</Link>.</p>
            ) : (
              <ul className="divide-y divide-ink-100">
                {c.documents.map((d) => (
                  <li key={d.id} className="py-2.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <FileText className="h-4 w-4 text-ink-400" />
                      <span className="text-sm font-medium text-ink-900">{d.file_name}</span>
                      <Badge tone="gray">{docLabel(d.document_type)}</Badge>
                      <StatePill state={d.validation_status} />
                      {d.attached_to_insurer && <Badge tone="green">Sent to insurer</Badge>}
                      <span className="ml-auto text-xs text-ink-400">{fmtDateTime(d.uploaded_at)}</span>
                    </div>
                    {d.issues.length > 0 && (
                      <ul className="mt-1.5 space-y-0.5 pl-6">
                        {d.issues.map((iss, i) => (
                          <li key={i} className="flex items-start gap-1.5 text-xs text-amber-700"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> {iss}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Insurer view (mock)" subtitle="Read directly from the insurer system for this demo." action={<Building2 className="h-4 w-4 text-ink-400" />}>
            {c.external_claim_id ? <InsurerView externalId={c.external_claim_id} /> : <p className="text-sm text-ink-500">This claim has not been submitted to the insurer yet, so there is no insurer record to show.</p>}
          </Card>

          <Card title="Insurer queries" subtitle={`${c.queries.filter((x) => x.status !== 'RESOLVED').length} open`}>
            {c.queries.length === 0 ? (
              <p className="text-sm text-ink-500">No queries raised by the insurer.</p>
            ) : (
              <ul className="space-y-3">
                {c.queries.map((qq) => (
                  <li key={qq.id} className={`rounded-lg border p-3 ${qq.status === 'RESOLVED' ? 'border-ink-200 bg-white' : 'border-amber-200 bg-amber-50/70'}`}>
                    <div className="flex items-center justify-between gap-2">
                      <StatePill state={qq.status} />
                      <span className="text-xs text-ink-500">raised {relDays(qq.raised_at) || fmtDate(qq.raised_at)}</span>
                    </div>
                    <p className="mt-1.5 text-sm text-ink-800">{qq.message}</p>
                    {qq.requested_document_type && <div className="mt-1 text-xs text-ink-600">Requested: <span className="font-medium">{docLabel(qq.requested_document_type)}</span></div>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
