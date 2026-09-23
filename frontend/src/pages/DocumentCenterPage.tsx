import React, { useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, CheckCircle2, FileText, Gauge, ScanSearch, Sparkles, Upload } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import type { ClaimDetail, DocumentAnalysis, DocumentOut, RequirementOut } from '../types/api'
import { useI18n } from '../i18n'
import { Badge, Card, Disclaimer, ErrorBox, KeyValue, Loading, PageHeader, ProgressBar, Spinner, StatePill } from '../components/ui'
import { fmtDateTime, pct, titleCase } from '../utils/format'

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

const SAMPLE_TYPES = new Set(['policy_copy', 'id_proof', 'claim_form', 'hospital_bill', 'discharge_summary', 'medical_certificate'])
const COMPARE_FIELDS: { key: string; label: string }[] = [
  { key: 'admission_date', label: 'Admission date' },
  { key: 'discharge_date', label: 'Discharge date' },
  { key: 'patient_name', label: 'Patient name' },
]

const isDoneStatus = (s: string) => s === 'DONE' || s === 'FULFILLED' || s === 'VALID' || s === 'COMPLETE'

function RequirementRow({ req, claimId, onResult, busyKey, setBusyKey }: { req: RequirementOut; claimId: string; onResult: (a: DocumentAnalysis) => void; busyKey: string | null; setBusyKey: (k: string | null) => void }) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [err, setErr] = useState<string | null>(null)

  const done = () => {
    qc.invalidateQueries({ queryKey: ['claim', claimId] })
    qc.invalidateQueries({ queryKey: ['readiness', claimId] })
    qc.invalidateQueries({ queryKey: ['claims'] })
  }

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadDocument(claimId, file, req.document_type),
    onMutate: () => { setErr(null); setBusyKey(`${req.id}:file`) },
    onSuccess: (a) => { onResult(a); done() },
    onError: (e) => setErr(errorMessage(e)),
    onSettled: () => setBusyKey(null),
  })
  const sample = useMutation({
    mutationFn: () => api.uploadSampleDocument(claimId, req.document_type),
    onMutate: () => { setErr(null); setBusyKey(`${req.id}:sample`) },
    onSuccess: (a) => { onResult(a); done() },
    onError: (e) => setErr(errorMessage(e)),
    onSettled: () => setBusyKey(null),
  })

  const busy = busyKey !== null
  const mine = busyKey?.startsWith(`${req.id}:`)
  const fulfilled = isDoneStatus(req.status)

  return (
    <li className={`rounded-lg border p-3 ${req.source === 'INSURER_QUERY' ? 'border-amber-200 bg-amber-50/60' : fulfilled ? 'border-emerald-100 bg-emerald-50/40' : 'border-ink-200 bg-white'}`}>
      <div className="flex flex-wrap items-start gap-2">
        <div className="mt-0.5">{fulfilled ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <FileText className="h-4 w-4 text-ink-400" />}</div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-ink-900">{req.label || docLabel(req.document_type)}</span>
            <StatePill state={req.status} />
            {req.source === 'INSURER_QUERY' && <Badge tone="amber">Requested by insurer</Badge>}
          </div>
          {req.description && <p className="mt-0.5 text-xs text-ink-500">{req.description}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input ref={fileRef} type="file" accept=".pdf,.txt,.png,.jpg,.jpeg" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = '' }} />
            <button type="button" className="btn-secondary !px-3 !py-1.5 text-xs" disabled={busy} onClick={() => fileRef.current?.click()}>
              {mine && upload.isPending ? <Spinner /> : <Upload className="h-3.5 w-3.5" />} {fulfilled ? 'Replace file' : 'Upload file'}
            </button>
            {SAMPLE_TYPES.has(req.document_type) && (
              <button type="button" className="btn-ghost !px-3 !py-1.5 text-xs" disabled={busy} onClick={() => sample.mutate()}>
                {mine && sample.isPending ? <Spinner /> : <Sparkles className="h-3.5 w-3.5 text-brand-500" />} Use sample document (demo)
              </button>
            )}
            <span className="text-[11px] text-ink-400">PDF, TXT, PNG, JPG</span>
          </div>
          {err && <div className="mt-2"><ErrorBox message={err} /></div>}
        </div>
      </div>
    </li>
  )
}

function IntelligencePanel({ analysis, fallbackDoc }: { analysis: DocumentAnalysis | null; fallbackDoc: DocumentOut | null }) {
  const doc = analysis?.document ?? fallbackDoc
  if (!doc) {
    return (
      <div className="flex flex-col items-center py-8 text-center">
        <ScanSearch className="h-8 w-8 text-ink-300" />
        <p className="mt-2 text-sm font-semibold text-ink-700">No document analysed yet</p>
        <p className="mt-1 text-xs text-ink-500">Upload a document to see classification, extracted fields and validation.</p>
      </div>
    )
  }
  const fields = Object.entries(doc.extracted_fields || {}).filter(([k, v]) => !k.endsWith('_raw') && k !== 'all_dates' && v != null && v !== '' && !(Array.isArray(v) && v.length === 0))
  const conf = doc.classification_confidence <= 1 ? doc.classification_confidence * 100 : doc.classification_confidence
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <FileText className="h-4 w-4 text-ink-400" />
        <span className="truncate text-sm font-semibold text-ink-900">{doc.file_name}</span>
        <Badge tone="blue">{docLabel(doc.document_type)}</Badge>
        <StatePill state={doc.validation_status} />
        {doc.attached_to_insurer && <Badge tone="green">Sent to insurer</Badge>}
      </div>
      <div>
        <div className="flex items-center justify-between text-xs">
          <span className="label">Classification confidence</span>
          <span className="font-semibold text-ink-700">{pct(conf)}</span>
        </div>
        <ProgressBar value={conf} className="mt-1.5" tone={conf >= 80 ? 'green' : conf >= 50 ? 'brand' : 'amber'} />
        <div className="mt-1 text-[11px] text-ink-400">Uploaded {fmtDateTime(doc.uploaded_at)} · {Math.max(1, Math.round(doc.size_bytes / 1024))} KB</div>
      </div>
      <div>
        <div className="label mb-2">Extracted fields</div>
        {fields.length ? (
          <KeyValue items={fields.map(([k, v]) => ({ k: titleCase(k), v: Array.isArray(v) ? v.join(', ') : typeof v === 'object' ? JSON.stringify(v) : String(v) }))} />
        ) : (
          <p className="text-sm text-ink-500">No structured fields extracted.</p>
        )}
      </div>
      <div>
        <div className="label mb-2">Validation issues</div>
        {doc.issues.length ? (
          <ul className="space-y-1">
            {doc.issues.map((iss, i) => (
              <li key={i} className="flex items-start gap-1.5 text-sm text-amber-700"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {iss}</li>
            ))}
          </ul>
        ) : (
          <p className="flex items-center gap-1.5 text-sm text-emerald-700"><CheckCircle2 className="h-4 w-4" /> No issues detected.</p>
        )}
      </div>
    </div>
  )
}

function ConsistencyPanel({ claim, crossIssues }: { claim: ClaimDetail; crossIssues: string[] }) {
  const qc = useQueryClient()
  const [choice, setChoice] = useState<Record<string, string>>({})
  const [confirmedNow, setConfirmedNow] = useState<Record<string, string>>({})

  const docsWithFields = useMemo(() => claim.documents.filter((d) => COMPARE_FIELDS.some((f) => d.extracted_fields?.[f.key])), [claim.documents])

  const mismatches = useMemo(() => {
    return COMPARE_FIELDS.map((f) => {
      const values = docsWithFields
        .map((d) => ({ doc: d, value: d.extracted_fields?.[f.key] != null ? String(d.extracted_fields[f.key]) : '' }))
        .filter((x) => x.value)
      const distinct = Array.from(new Set(values.map((x) => x.value)))
      return { field: f, values, distinct, mismatch: distinct.length > 1 }
    }).filter((m) => m.mismatch)
  }, [docsWithFields])

  const confirm = useMutation({
    mutationFn: ({ field, value, note }: { field: string; value: string; note: string }) => api.confirmValue(claim.id, field, value, note),
    onSuccess: (_r, vars) => {
      setConfirmedNow((s) => ({ ...s, [vars.field]: vars.value }))
      qc.invalidateQueries({ queryKey: ['claim', claim.id] })
      qc.invalidateQueries({ queryKey: ['readiness', claim.id] })
    },
  })

  const confirmedValue = (field: string): string | null => {
    const fromClaim = claim.user_confirmations?.[field]
    if (fromClaim != null) return typeof fromClaim === 'object' ? String(fromClaim.value ?? JSON.stringify(fromClaim)) : String(fromClaim)
    return confirmedNow[field] ?? null
  }

  return (
    <div className="space-y-4">
      {crossIssues.length > 0 && (
        <ul className="space-y-1">
          {crossIssues.map((iss, i) => (
            <li key={i} className="flex items-start gap-1.5 rounded-lg bg-amber-50 p-2 text-sm text-amber-800"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {iss}</li>
          ))}
        </ul>
      )}

      {docsWithFields.length === 0 ? (
        <p className="text-sm text-ink-500">No comparable fields yet. Upload a hospital bill and discharge summary to cross-check dates and names.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-ink-500">
              <tr>
                <th className="py-1.5 pr-3 font-semibold">Document</th>
                {COMPARE_FIELDS.map((f) => <th key={f.key} className="py-1.5 pr-3 font-semibold">{f.label}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {docsWithFields.map((d) => (
                <tr key={d.id}>
                  <td className="py-2 pr-3">
                    <div className="font-medium text-ink-900">{docLabel(d.document_type)}</div>
                    <div className="truncate text-[11px] text-ink-400">{d.file_name}</div>
                  </td>
                  {COMPARE_FIELDS.map((f) => {
                    const v = d.extracted_fields?.[f.key]
                    const mm = mismatches.find((m) => m.field.key === f.key)
                    return (
                      <td key={f.key} className={`py-2 pr-3 ${mm && v ? 'font-semibold text-amber-700' : 'text-ink-800'}`}>{v != null && v !== '' ? String(v) : <span className="text-ink-300">—</span>}</td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {mismatches.map((m) => {
        const confirmed = confirmedValue(m.field.key)
        const selected = choice[m.field.key] ?? ''
        return (
          <div key={m.field.key} className="rounded-lg border border-amber-200 bg-amber-50/70 p-4">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <div className="flex-1">
                <div className="text-sm font-semibold text-amber-900">Potential inconsistency: {m.field.label.toLowerCase()}s differ</div>
                <p className="mt-0.5 text-xs text-amber-800">Please verify the correct value before submission. COVE2E will not change any document.</p>
                {confirmed ? (
                  <div className="mt-3 flex items-center gap-2 rounded-lg bg-white p-2.5 text-sm text-emerald-800 ring-1 ring-emerald-200">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500" /> You confirmed <span className="font-semibold">{confirmed}</span> as the correct {m.field.label.toLowerCase()}.
                  </div>
                ) : (
                  <>
                    <div className="mt-3 space-y-1.5">
                      {m.values.map((x) => (
                        <label key={x.doc.id} className={`flex cursor-pointer items-center gap-2 rounded-lg border bg-white p-2 text-sm ${selected === x.value ? 'border-brand-400 ring-1 ring-brand-200' : 'border-ink-200'}`}>
                          <input type="radio" name={`confirm-${m.field.key}`} value={x.value} checked={selected === x.value} onChange={() => setChoice((s) => ({ ...s, [m.field.key]: x.value }))} />
                          <span className="font-semibold text-ink-900">{x.value}</span>
                          <span className="text-xs text-ink-500">from {docLabel(x.doc.document_type)} · {x.doc.file_name}</span>
                        </label>
                      ))}
                    </div>
                    <div className="mt-3 flex items-center gap-2">
                      <button
                        className="btn-primary !py-1.5"
                        disabled={!selected || confirm.isPending}
                        onClick={() => {
                          const src = m.values.find((x) => x.value === selected)
                          confirm.mutate({ field: m.field.key, value: selected, note: src ? `Confirmed by user from ${docLabel(src.doc.document_type)} (${src.doc.file_name})` : 'Confirmed by user' })
                        }}
                      >
                        {confirm.isPending && confirm.variables?.field === m.field.key ? <Spinner /> : <CheckCircle2 className="h-4 w-4" />} Confirm
                      </button>
                      {confirm.isError && confirm.variables?.field === m.field.key && <span className="text-xs text-rose-700">{errorMessage(confirm.error)}</span>}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )
      })}

      {mismatches.length === 0 && docsWithFields.length > 1 && crossIssues.length === 0 && (
        <p className="flex items-center gap-1.5 text-sm text-emerald-700"><CheckCircle2 className="h-4 w-4" /> Compared fields are consistent across documents.</p>
      )}
    </div>
  )
}

export default function DocumentCenterPage() {
  const { id = '' } = useParams()
  const { t } = useI18n()
  const [lastAnalysis, setLastAnalysis] = useState<DocumentAnalysis | null>(null)
  const [busyKey, setBusyKey] = useState<string | null>(null)

  const claimQ = useQuery({ queryKey: ['claim', id], queryFn: () => api.claim(id), enabled: !!id })
  const readinessQ = useQuery({ queryKey: ['readiness', id], queryFn: () => api.readiness(id), enabled: !!id })

  if (claimQ.isLoading) return <Loading label={t('common.loading')} />
  if (claimQ.isError) return <ErrorBox message={errorMessage(claimQ.error)} />
  const claim = claimQ.data
  if (!claim) return <ErrorBox message="Claim not found" />

  const required = claim.requirements.filter((r) => r.required)
  const optional = claim.requirements.filter((r) => !r.required)
  const latestDoc = claim.documents.length ? [...claim.documents].sort((a, b) => new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime())[0] : null
  const readiness = lastAnalysis?.readiness ?? readinessQ.data ?? null
  const fulfilledCount = claim.requirements.filter((r) => isDoneStatus(r.status)).length

  return (
    <div>
      <PageHeader
        crumbs={[{ label: t('nav.claims'), to: '/claims' }, { label: claim.claim_number, to: `/claims/${claim.id}` }, { label: t('claim.documents') }]}
        title={t('claim.documents')}
        subtitle={<span>Stage 4 · Document Checklist for <span className="mono font-semibold text-ink-700">{claim.claim_number}</span> · {fulfilledCount}/{claim.requirements.length} requirements fulfilled</span>}
        actions={<Link to={`/claims/${claim.id}/readiness`} className="btn-primary"><Gauge className="h-4 w-4" /> Check readiness</Link>}
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          <Card title="Required documents" subtitle="Each upload is classified, its fields extracted and validated against the claim.">
            {required.length === 0 ? <p className="text-sm text-ink-500">No required documents for this claim.</p> : (
              <ul className="space-y-2">
                {required.map((r) => <RequirementRow key={r.id} req={r} claimId={claim.id} onResult={setLastAnalysis} busyKey={busyKey} setBusyKey={setBusyKey} />)}
              </ul>
            )}
          </Card>
          {optional.length > 0 && (
            <Card title="Optional documents" subtitle="Helpful for faster processing but not mandatory.">
              <ul className="space-y-2">
                {optional.map((r) => <RequirementRow key={r.id} req={r} claimId={claim.id} onResult={setLastAnalysis} busyKey={busyKey} setBusyKey={setBusyKey} />)}
              </ul>
            </Card>
          )}

          <Card title="Cross-document consistency" subtitle="COVE2E compares key fields across uploaded documents. Mismatches are flagged for you to verify — nothing is auto-corrected.">
            <ConsistencyPanel claim={claim} crossIssues={lastAnalysis?.cross_document_issues ?? []} />
          </Card>
        </div>

        <div className="space-y-6 lg:col-span-2">
          <Card title="Document Intelligence" subtitle={lastAnalysis ? 'Result of your latest upload' : latestDoc ? 'Most recent document on this claim' : undefined} action={<ScanSearch className="h-4 w-4 text-ink-400" />}>
            <IntelligencePanel analysis={lastAnalysis} fallbackDoc={latestDoc} />
          </Card>

          <Card title={t('claim.readiness')} subtitle="Documentation and process completeness only.">
            {readinessQ.isLoading && !readiness ? <Loading /> : readiness ? (
              <>
                <div className="flex items-end justify-between">
                  <div className="text-3xl font-bold text-ink-900">{pct(readiness.percent)}</div>
                  <div className="text-right text-xs text-ink-500">
                    <div><span className="font-semibold text-ink-800">{readiness.outstanding_count}</span> outstanding</div>
                    <div>{readiness.ready_to_submit ? <Badge tone="green">Ready for submission gate</Badge> : <Badge tone="amber">Not ready yet</Badge>}</div>
                  </div>
                </div>
                <ProgressBar value={readiness.percent} className="mt-2" tone={readiness.percent >= 100 ? 'green' : readiness.percent >= 60 ? 'brand' : 'amber'} />
                <div className="mt-3 rounded-lg bg-ink-50 p-2.5 text-sm text-ink-800"><span className="label">{t('claim.nextAction')}</span><div className="mt-0.5">{readiness.next_action}</div></div>
                <Link to={`/claims/${claim.id}/readiness`} className="btn-secondary mt-3 w-full">Check readiness <ArrowRight className="h-4 w-4" /></Link>
                <Disclaimer>{readiness.disclaimer}</Disclaimer>
              </>
            ) : readinessQ.isError ? <ErrorBox message={errorMessage(readinessQ.error)} /> : <p className="text-sm text-ink-500">Readiness unavailable.</p>}
          </Card>

          {claim.documents.length > 0 && (
            <Card title="All uploads" subtitle={`${claim.documents.length} document${claim.documents.length === 1 ? '' : 's'}`}>
              <ul className="divide-y divide-ink-100">
                {claim.documents.map((d) => (
                  <li key={d.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                    <button type="button" className="truncate font-medium text-ink-900 hover:text-brand-700" onClick={() => setLastAnalysis({ document: d, cross_document_issues: lastAnalysis?.cross_document_issues ?? [], readiness: readiness ?? { claim_id: claim.id, percent: 0, items: [], outstanding_count: 0, next_action: '', ready_to_submit: false, disclaimer: '' } })}>{d.file_name}</button>
                    <Badge tone="gray">{docLabel(d.document_type)}</Badge>
                    <StatePill state={d.validation_status} />
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
