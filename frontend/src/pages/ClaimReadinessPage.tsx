import React, { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, ArrowRight, FileText, Lock, RefreshCw, Send, ShieldAlert, ShieldCheck, Workflow } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import type { ExecutionResult, ExecutionStep, RiskClass, SubmitClaimResponse } from '../types/api'
import { useI18n } from '../i18n'
import { Badge, Card, CheckList, Disclaimer, ErrorBox, Loading, PageHeader, ProgressBar, Spinner, StatePill, StatusIcon } from '../components/ui'
import { pct, sleep } from '../utils/format'

const DOC_LABELS: Record<string, string> = {
  policy_copy: 'Policy copy', id_proof: 'Identity proof', claim_form: 'Claim form', hospital_bill: 'Hospital bill', discharge_summary: 'Discharge summary', medical_certificate: 'Medical certificate',
  prescription: 'Prescription', diagnostic_report: 'Diagnostic report', driving_license: 'Driving license', rc_copy: 'RC copy', fir_copy: 'FIR copy', repair_estimate: 'Repair estimate',
  damage_photos: 'Damage photos', purchase_invoice: 'Purchase invoice', other: 'Other',
}
const titleCase = (s: string) => s.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())
const docLabel = (type: string | null | undefined) => (type ? DOC_LABELS[type] ?? titleCase(type) : '')

const RISK_LABEL: Record<RiskClass, string> = {
  AUTO_RECOVERABLE: 'Safe to execute automatically',
  USER_CONFIRMATION_REQUIRED: 'User confirmation required',
  HUMAN_ESCALATION_REQUIRED: 'Human escalation required',
}

function Ring({ value, size = 168, stroke = 12 }: { value: number; size?: number; stroke?: number }) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const v = Math.max(0, Math.min(100, value))
  const color = v >= 100 ? '#10b981' : v >= 60 ? '#2563eb' : '#f59e0b'
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e9ecf2" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c - (v / 100) * c} className="transition-all duration-700" />
    </svg>
  )
}

function ExecutionPanel({ result, claimId }: { result: ExecutionResult; claimId: string }) {
  const [shown, setShown] = useState(0)
  const timer = useRef<number | null>(null)
  useEffect(() => {
    setShown(0)
    let i = 0
    const tick = () => {
      i += 1
      setShown(i)
      if (i < result.steps.length) timer.current = window.setTimeout(tick, 600)
    }
    timer.current = window.setTimeout(tick, 250)
    return () => { if (timer.current) window.clearTimeout(timer.current) }
  }, [result])

  const complete = shown >= result.steps.length
  const v = result.verification
  const ok = result.status === 'SUCCEEDED' || result.status === 'VERIFIED' || (v?.outcome === 'VERIFIED')

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Workflow className="h-4 w-4 text-ink-500" />
        <span className="text-sm font-semibold text-ink-900">Execution</span>
        <StatePill state={complete ? result.status : 'EXECUTING'} />
        <Badge tone={result.executor === 'n8n' ? 'purple' : result.executor === 'demo-fallback' ? 'amber' : 'gray'}>Executor: {result.executor}</Badge>
        {result.workflow_run_id && <span className="mono text-[11px] text-ink-400">run {result.workflow_run_id}</span>}
      </div>
      {result.executor === 'demo-fallback' && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs font-medium text-amber-800"><ShieldAlert className="h-3.5 w-3.5" /> Executed via demo fallback (n8n unreachable)</div>
      )}
      <ol className="space-y-2">
        {result.steps.map((s: ExecutionStep, i) => {
          const visible = i < shown
          const running = i === shown && !complete
          return (
            <li key={s.key} className={`flex items-start gap-2 rounded-lg border p-2.5 text-sm transition ${visible ? 'border-ink-200 bg-white opacity-100' : running ? 'border-brand-200 bg-brand-50/50' : 'border-ink-100 bg-ink-50/40 opacity-50'}`}>
              <StatusIcon status={visible ? s.status : running ? 'RUNNING' : 'PENDING'} className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="font-medium text-ink-900">{s.label}</div>
                {visible && s.detail && <div className="text-xs text-ink-500">{s.detail}</div>}
              </div>
              {visible && <StatePill state={s.status} />}
            </li>
          )
        })}
      </ol>

      {complete && (
        <>
          {v && (
            <div className="rounded-lg border border-ink-200 bg-ink-50/60 p-3">
              <div className="mb-2 flex items-center gap-2"><span className="label">Verification</span><StatePill state={v.outcome} /></div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <div className="label">Before</div>
                  <div className="mt-1 font-medium text-ink-800">{v.before_state ? <StatePill state={v.before_state} /> : <span className="text-ink-500">none (not submitted)</span>}</div>
                </div>
                <div>
                  <div className="label">After</div>
                  <div className="mt-1 font-medium text-ink-800">{v.after_state ? <StatePill state={v.after_state} /> : <span className="text-ink-500">—</span>}</div>
                </div>
              </div>
              {v.message && <p className="mt-2 text-xs text-ink-600">{v.message}</p>}
            </div>
          )}
          <div className={`rounded-lg border p-3 text-sm ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-900' : 'border-amber-200 bg-amber-50 text-amber-900'}`}>{result.final_message}</div>
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`/claims/${claimId}/tracking`} className="btn-primary"><Activity className="h-4 w-4" /> Track claim</Link>
            <Link to={`/claims/${claimId}`} className="btn-ghost">Claim details</Link>
          </div>
          <p className="text-xs text-ink-500">Submission means the insurer has received the claim. Approval, settlement and payment are the insurer's decisions and will appear in tracking.</p>
        </>
      )}
    </div>
  )
}

export default function ClaimReadinessPage() {
  const { id = '' } = useParams()
  const { t, lang } = useI18n()
  const qc = useQueryClient()

  const claimQ = useQuery({ queryKey: ['claim', id], queryFn: () => api.claim(id), enabled: !!id })
  const readinessQ = useQuery({ queryKey: ['readiness', id], queryFn: () => api.readiness(id), enabled: !!id })

  const [gate, setGate] = useState<SubmitClaimResponse | null>(null)
  const [execResult, setExecResult] = useState<ExecutionResult | null>(null)

  const prepare = useMutation({
    mutationFn: () => api.prepareSubmission(id),
    onSuccess: (r) => { setGate(r); setExecResult(null); qc.invalidateQueries({ queryKey: ['readiness', id] }) },
  })

  const execute = useMutation({
    mutationFn: async (actionId: string) => {
      await api.approveAction(actionId)
      await sleep(300)
      return api.executeAction(actionId, lang)
    },
    onSuccess: (r) => {
      setExecResult(r)
      qc.invalidateQueries({ queryKey: ['claim', id] })
      qc.invalidateQueries({ queryKey: ['claims'] })
      qc.invalidateQueries({ queryKey: ['readiness', id] })
      qc.invalidateQueries({ queryKey: ['tracking', id] })
      qc.invalidateQueries({ queryKey: ['journeys'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  if (claimQ.isLoading || readinessQ.isLoading) return <Loading label={t('common.loading')} />
  if (claimQ.isError) return <ErrorBox message={errorMessage(claimQ.error)} />
  if (readinessQ.isError) return <ErrorBox message={errorMessage(readinessQ.error)} />
  const claim = claimQ.data
  const r = gate?.readiness ?? readinessQ.data
  if (!claim || !r) return <ErrorBox message="Claim not found" />

  const alreadySubmitted = !!claim.submitted_at
  const action = gate?.action ?? null
  const gateTone = action ? (action.gate_decision === 'SAFE' ? 'green' : action.gate_decision === 'CONFIRM' ? 'amber' : 'red') : 'gray'
  const unmet = action?.prerequisites.filter((p) => !p.satisfied) ?? []

  return (
    <div>
      <PageHeader
        crumbs={[{ label: t('nav.claims'), to: '/claims' }, { label: claim.claim_number, to: `/claims/${claim.id}` }, { label: t('claim.readiness') }]}
        title={t('claim.readiness')}
        subtitle={<span>Documentation and process completeness for <span className="mono font-semibold text-ink-700">{claim.claim_number}</span>. This is not an approval probability.</span>}
        actions={
          <>
            <button className="btn-ghost" onClick={() => readinessQ.refetch()}><RefreshCw className={`h-4 w-4 ${readinessQ.isFetching ? 'animate-spin' : ''}`} /> Refresh</button>
            <Link to={`/claims/${claim.id}/documents`} className="btn-secondary"><FileText className="h-4 w-4" /> {t('claim.documents')}</Link>
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          <Card>
            <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
              <div className="relative mx-auto shrink-0">
                <Ring value={r.percent} />
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <div className="text-4xl font-bold tracking-tight text-ink-950">{pct(r.percent)}</div>
                  <div className="label">Claim readiness</div>
                </div>
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold uppercase tracking-wider text-ink-500">CLAIM READINESS</div>
                  {r.ready_to_submit ? <Badge tone="green">Ready for submission gate</Badge> : <Badge tone="amber">{r.outstanding_count} outstanding</Badge>}
                </div>
                <ProgressBar value={r.percent} className="mt-2" tone={r.percent >= 100 ? 'green' : r.percent >= 60 ? 'brand' : 'amber'} />
                <div className="mt-4 rounded-lg border border-brand-200 bg-brand-50/70 p-3">
                  <div className="label text-brand-700">NEXT ACTION</div>
                  <p className="mt-1 text-sm font-medium text-ink-900">{r.next_action}</p>
                </div>
                <Disclaimer>{r.disclaimer}</Disclaimer>
              </div>
            </div>
          </Card>

          <Card title="Readiness checklist" subtitle={`${r.items.filter((i) => i.status === 'DONE').length}/${r.items.length} complete`}>
            {r.items.length === 0 ? <p className="text-sm text-ink-500">No checklist items.</p> : (
              <ul className="divide-y divide-ink-100">
                {r.items.map((it, i) => (
                  <li key={i} className="flex items-start gap-3 py-2.5">
                    <StatusIcon status={it.status} className="mt-0.5 h-4 w-4 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink-900">
                        {it.label}
                        {it.document_type && <Badge tone="gray">{docLabel(it.document_type)}</Badge>}
                      </div>
                      {it.detail && <div className="text-xs text-ink-500">{it.detail}</div>}
                    </div>
                    <StatePill state={it.status} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-6 lg:col-span-2">
          <Card title={t('claim.submit')} subtitle="Submission passes through the Action Gate before anything is sent to the insurer." action={<Lock className="h-4 w-4 text-ink-400" />}>
            {alreadySubmitted && !execResult && (
              <div className="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
                This claim was already submitted to the insurer{claim.external_claim_id ? <> (ref <span className="mono">{claim.external_claim_id}</span>)</> : null}.
                <div className="mt-2"><Link to={`/claims/${claim.id}/tracking`} className="btn-secondary !py-1.5"><Activity className="h-4 w-4" /> {t('claim.tracking')}</Link></div>
              </div>
            )}

            {!execResult && (
              <button className="btn-primary w-full" disabled={prepare.isPending || execute.isPending} onClick={() => prepare.mutate()}>
                {prepare.isPending ? <><Spinner /> Evaluating action gate…</> : <><ShieldCheck className="h-4 w-4" /> Prepare submission</>}
              </button>
            )}
            {prepare.isError && <div className="mt-3"><ErrorBox message={errorMessage(prepare.error)} /></div>}

            {gate && action && !execResult && (
              <div className="mt-4 space-y-4">
                {gate.message && <p className="text-sm text-ink-700">{gate.message}</p>}
                <div className="rounded-lg border border-ink-200 p-3">
                  <div className="label">PROPOSED ACTION</div>
                  <div className="mt-0.5 text-sm font-semibold text-ink-900">{action.title}</div>
                  {action.description && <p className="mt-0.5 text-xs text-ink-500">{action.description}</p>}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg border border-ink-200 p-3">
                    <div className="label">PERMISSION</div>
                    <div className="mt-1 text-sm font-medium text-ink-900">{RISK_LABEL[action.risk_class] ?? titleCase(action.risk_class)}</div>
                  </div>
                  <div className="rounded-lg border border-ink-200 p-3">
                    <div className="label">GATE DECISION</div>
                    <div className="mt-1"><Badge tone={gateTone}>{action.gate_decision}</Badge></div>
                  </div>
                </div>
                <div>
                  <div className="label mb-1.5">REASON</div>
                  {action.gate_reasons.length ? (
                    <ul className="list-disc space-y-0.5 pl-5 text-sm text-ink-800">{action.gate_reasons.map((g, i) => <li key={i}>{g}</li>)}</ul>
                  ) : <p className="text-sm text-ink-500">{t('common.none')}</p>}
                </div>
                {action.gate_checks.length > 0 && (
                  <div>
                    <div className="label mb-1.5">Gate checks</div>
                    <CheckList items={action.gate_checks.map((g) => ({ label: titleCase(g.name), status: g.passed ? 'DONE' : 'ISSUE', detail: g.detail }))} />
                  </div>
                )}
                {action.prerequisites.length > 0 && (
                  <div>
                    <div className="label mb-1.5">Prerequisites</div>
                    <ul className="space-y-1.5">
                      {action.prerequisites.map((p) => (
                        <li key={p.key} className="flex items-start gap-2 text-sm">
                          <StatusIcon status={p.satisfied ? 'DONE' : 'MISSING'} className="mt-0.5 h-4 w-4 shrink-0" />
                          <div>
                            <div className="text-ink-900">{p.label}{p.document_type && <span className="ml-1 text-xs text-ink-500">({docLabel(p.document_type)})</span>}</div>
                            {!p.satisfied && p.hint && <div className="text-xs text-amber-700">{p.hint}</div>}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {action.can_execute ? (
                  <div className="rounded-lg border border-brand-200 bg-brand-50/60 p-3">
                    <p className="text-xs text-ink-700">COVE2E will submit the claim to the insurer on your confirmation, then re-read the insurer state to verify. Submission does not guarantee approval.</p>
                    <button className="btn-primary mt-3 w-full" disabled={execute.isPending} onClick={() => execute.mutate(action.id)}>
                      {execute.isPending ? <><Spinner /> Submitting to insurer…</> : <><Send className="h-4 w-4" /> [Confirm &amp; Submit]</>}
                    </button>
                    {execute.isError && <div className="mt-2"><ErrorBox message={errorMessage(execute.error)} /></div>}
                  </div>
                ) : (
                  <div className="rounded-lg border border-amber-200 bg-amber-50/70 p-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-amber-900"><ShieldAlert className="h-4 w-4" /> Submission blocked by the Action Gate</div>
                    {unmet.length > 0 && (
                      <ul className="mt-2 space-y-1 text-sm text-amber-900">
                        {unmet.map((p) => <li key={p.key}>• {p.label}{p.hint ? ` — ${p.hint}` : ''}</li>)}
                      </ul>
                    )}
                    <Link to={`/claims/${claim.id}/documents`} className="btn-secondary mt-3 !py-1.5"><FileText className="h-4 w-4" /> Go to Document Center <ArrowRight className="h-3.5 w-3.5" /></Link>
                  </div>
                )}
              </div>
            )}

            {execute.isPending && (
              <div className="mt-4 space-y-2">
                {['Approving action', 'Submitting claim to insurer', 'Verifying insurer state'].map((l, i) => (
                  <div key={l} className="flex items-center gap-2 rounded-lg border border-ink-100 p-2.5 text-sm text-ink-700">
                    <StatusIcon status={i === 0 ? 'RUNNING' : 'PENDING'} className="h-4 w-4" /> {l}…
                  </div>
                ))}
              </div>
            )}

            {execResult && <div className="mt-4"><ExecutionPanel result={execResult} claimId={claim.id} /></div>}
          </Card>
        </div>
      </div>
    </div>
  )
}
