import React, { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertOctagon, AlertTriangle, ArrowRight, Bot, Building2, CheckCircle2, ExternalLink, FileUp, History, LayoutDashboard, ListChecks, Lock, Radar, RefreshCw, ScrollText, Search, ShieldAlert, ShieldCheck, Sparkles, Upload, Workflow, XCircle, Zap } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import { useI18n } from '../i18n'
import { fmtDateTime, relDays, sleep, stateLabel } from '../utils/format'
import { Badge, Card, CheckList, ErrorBox, Loading, PageHeader, Spinner, StatePill, StatusIcon, StepRow, toneForState } from '../components/ui'
import type { ActionProposal, ExecutionResult, GateDecision, Prerequisite, RecoveryPlan, RiskClass } from '../types/api'

const STEP_REVEAL_MS = 600
const VERIFY_MS = 800

const RISK_TEXT: Record<RiskClass, string> = {
  AUTO_RECOVERABLE: 'Safe — no confirmation needed',
  USER_CONFIRMATION_REQUIRED: 'User confirmation required',
  HUMAN_ESCALATION_REQUIRED: 'Human escalation required',
}
const RISK_TONE: Record<RiskClass, string> = { AUTO_RECOVERABLE: 'green', USER_CONFIRMATION_REQUIRED: 'amber', HUMAN_ESCALATION_REQUIRED: 'red' }
const GATE_TONE: Record<GateDecision, string> = { SAFE: 'green', CONFIRM: 'amber', ESCALATE: 'red', DENY: 'red' }
const ACTOR_TONE: Record<string, string> = { USER: 'amber', SYSTEM: 'gray', N8N: 'blue', INSURER: 'purple', HUMAN_AGENT: 'red' }

type Phase = 'idle' | 'approving' | 'executing' | 'verifying' | 'done' | 'error'

function SourceBadge({ source }: { source: 'AI' | 'DETERMINISTIC' | string }) {
  return <Badge tone={source === 'AI' ? 'purple' : 'blue'}>{source === 'AI' ? 'Sarvam AI' : 'Deterministic'}</Badge>
}

function Bubble({ text, source, tone = 'default' }: { text: string; source?: string; tone?: 'default' | 'success' }) {
  return (
    <div className="flex gap-3">
      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white ${tone === 'success' ? 'bg-emerald-600' : 'bg-brand-600'}`}><Bot className="h-4 w-4" /></div>
      <div className={`flex-1 rounded-2xl rounded-tl-sm border px-4 py-3 shadow-card ${tone === 'success' ? 'border-emerald-200 bg-emerald-50' : 'border-ink-200 bg-white'}`}>
        <p className="whitespace-pre-line text-sm text-ink-900">{text}</p>
        {source && <div className="mt-2"><SourceBadge source={source} /></div>}
      </div>
    </div>
  )
}

function InsurerViewCard({ externalId }: { externalId: string | null | undefined }) {
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ['insurer-claim', externalId],
    queryFn: () => api.insurerClaim(externalId as string),
    enabled: !!externalId,
  })
  return (
    <Card title="Insurer view (mock)" subtitle="Live read from the mock insurer system" action={isFetching ? <Spinner className="h-3.5 w-3.5 text-ink-400" /> : undefined}>
      {!externalId ? (
        <p className="text-sm text-ink-500">Claim not yet registered with the insurer.</p>
      ) : isLoading ? (
        <Loading />
      ) : error || !data ? (
        <ErrorBox message={errorMessage(error)} />
      ) : (
        <div className="space-y-3">
          {data.conflict && (
            <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-xs text-rose-700">
              <AlertOctagon className="mt-0.5 h-3.5 w-3.5 shrink-0" /> Insurer systems report conflicting states. Requires human reconciliation.
            </div>
          )}
          <dl className="grid grid-cols-1 gap-2 text-sm">
            <div className="flex items-center justify-between"><dt className="text-ink-500">Status</dt><dd><StatePill state={data.status} /></dd></div>
            <div className="flex items-center justify-between"><dt className="text-ink-500">Settlement</dt><dd className={data.conflict ? 'font-semibold text-rose-700' : ''}><StatePill state={data.settlement_status} /></dd></div>
            <div className="flex items-center justify-between"><dt className="text-ink-500">Payment</dt><dd className={data.conflict ? 'font-semibold text-rose-700' : ''}><StatePill state={data.payment_status} /></dd></div>
          </dl>
          <div>
            <div className="label">Open queries</div>
            {Array.isArray(data.open_queries) && data.open_queries.length ? (
              <ul className="mt-1 space-y-1.5">
                {data.open_queries.map((q: Record<string, unknown>, i: number) => (
                  <li key={i} className="rounded-md bg-amber-50 p-2 text-xs text-amber-800">
                    {String(q.message ?? q.detail ?? 'Query open')}
                    {q.requested_document_type ? <span className="mono ml-1 text-amber-700">[{String(q.requested_document_type)}]</span> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-xs text-ink-500">None</p>
            )}
          </div>
          {Array.isArray(data.documents) && (
            <div>
              <div className="label">Documents at insurer</div>
              <p className="mono mt-1 text-xs text-ink-700">{data.documents.length ? data.documents.map((d: Record<string, unknown>) => String(d.document_type ?? d.type ?? d.name ?? '')).join(', ') : 'none'}</p>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

/** Upload controls for an unsatisfied document prerequisite. */
function DocumentUploader({ claimId, prereq, onUploaded }: { claimId: string; prereq: Prerequisite; onUploaded: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const docType = prereq.document_type as string
  const sample = useMutation({ mutationFn: () => api.uploadSampleDocument(claimId, docType), onSuccess: onUploaded })
  const real = useMutation({ mutationFn: (file: File) => api.uploadDocument(claimId, file, docType), onSuccess: onUploaded })
  const busy = sample.isPending || real.isPending
  return (
    <div className="mt-2 rounded-lg border border-dashed border-amber-300 bg-amber-50/60 p-3">
      <p className="flex items-center gap-1.5 text-xs font-semibold text-amber-800"><FileUp className="h-3.5 w-3.5" /> Upload required: {stateLabel(docType)}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button type="button" className="btn-primary !py-1.5 text-xs" disabled={busy} onClick={() => sample.mutate()}>
          {sample.isPending ? <Spinner /> : <Sparkles className="h-3.5 w-3.5" />} Use sample {docType === 'medical_certificate' ? 'medical certificate' : stateLabel(docType).toLowerCase()} (demo)
        </button>
        <button type="button" className="btn-secondary !py-1.5 text-xs" disabled={busy} onClick={() => fileRef.current?.click()}>
          {real.isPending ? <Spinner /> : <Upload className="h-3.5 w-3.5" />} Upload file
        </button>
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          accept=".pdf,.png,.jpg,.jpeg,.txt"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) real.mutate(f)
            e.target.value = ''
          }}
        />
      </div>
      {(sample.error || real.error) && <div className="mt-2"><ErrorBox message={errorMessage(sample.error || real.error)} /></div>}
    </div>
  )
}

/** Radio resolver for CONFIRM_DOCUMENT_VALUE actions. */
function ValueResolver({ claimId, action, onConfirmed }: { claimId: string; action: ActionProposal; onConfirmed: () => void }) {
  const field = String(action.payload.field ?? 'value')
  const options = (action.payload.options ?? {}) as Record<string, string>
  const [value, setValue] = useState<string>('')
  const m = useMutation({ mutationFn: () => api.confirmValue(claimId, field, value, 'confirmed in recovery'), onSuccess: onConfirmed })
  const entries = Object.entries(options)
  return (
    <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50/60 p-4">
      <div className="label">Resolve: which {stateLabel(field).toLowerCase()} is correct?</div>
      <p className="mt-1 text-xs text-ink-600">Nothing is modified in any document. Your confirmation is recorded against the claim only.</p>
      <div className="mt-3 space-y-2">
        {entries.length === 0 && <p className="text-sm text-ink-500">No conflicting values found.</p>}
        {entries.map(([docLabel, v]) => (
          <label key={docLabel} className={`flex cursor-pointer items-center gap-3 rounded-lg border bg-white p-3 text-sm transition ${value === String(v) ? 'border-brand-400 ring-2 ring-brand-100' : 'border-ink-200 hover:border-ink-300'}`}>
            <input type="radio" name={`resolve-${field}`} className="h-4 w-4 accent-brand-600" checked={value === String(v)} onChange={() => setValue(String(v))} />
            <span className="mono font-semibold text-ink-900">{String(v)}</span>
            <span className="ml-auto text-xs text-ink-500">from {docLabel}</span>
          </label>
        ))}
      </div>
      {m.error && <div className="mt-2"><ErrorBox message={errorMessage(m.error)} /></div>}
      <button type="button" className="btn-primary mt-3" disabled={!value || m.isPending} onClick={() => m.mutate()}>
        {m.isPending ? <Spinner /> : <CheckCircle2 className="h-4 w-4" />} Confirm value
      </button>
    </div>
  )
}

function ExecutorBadge({ executor }: { executor: ExecutionResult['executor'] }) {
  if (executor === 'n8n') return <Badge tone="blue"><Workflow className="h-3 w-3" /> Executed via n8n workflow</Badge>
  if (executor === 'demo-fallback') return <Badge tone="amber"><AlertTriangle className="h-3 w-3" /> Executed via demo fallback (n8n unreachable)</Badge>
  return <Badge tone="gray"><Zap className="h-3 w-3" /> Executed internally</Badge>
}

export default function JourneyRecoveryPage() {
  const { id = '' } = useParams()
  const { lang, t } = useI18n()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const journeyQ = useQuery({ queryKey: ['journey', id], queryFn: () => api.journey(id), enabled: !!id })
  const planQ = useQuery({ queryKey: ['recovery-plan', id, lang], queryFn: () => api.recoveryPlan(id, lang), enabled: !!id, refetchOnMount: 'always', staleTime: Infinity })
  const attemptsQ = useQuery({ queryKey: ['recovery-attempts', id], queryFn: () => api.recoveryAttempts(id), enabled: !!id })
  const auditQ = useQuery({ queryKey: ['audit', id], queryFn: () => api.audit(id), enabled: !!id })

  const [phase, setPhase] = useState<Phase>('idle')
  const [exec, setExec] = useState<ExecutionResult | null>(null)
  const [revealed, setRevealed] = useState(0)
  const [execError, setExecError] = useState<string | null>(null)

  const journey = journeyQ.data
  const plan: RecoveryPlan | undefined = planQ.data
  const claimId = journey?.claim_id ?? journey?.claim?.id ?? plan?.claim_id ?? null
  const externalId = journey?.claim?.external_claim_id

  const refreshSide = () => {
    qc.invalidateQueries({ queryKey: ['recovery-attempts', id] })
    qc.invalidateQueries({ queryKey: ['audit', id] })
    qc.invalidateQueries({ queryKey: ['insurer-claim', externalId] })
  }

  const afterPrerequisiteChange = () => {
    qc.invalidateQueries({ queryKey: ['journey', id] })
    qc.invalidateQueries({ queryKey: ['claims'] })
    qc.invalidateQueries({ queryKey: ['claim', claimId] })
    planQ.refetch()
    refreshSide()
  }

  const runRecovery = async (action: ActionProposal) => {
    if (phase !== 'idle' && phase !== 'error') return
    setExecError(null)
    setExec(null)
    setRevealed(0)
    try {
      setPhase('approving')
      await api.approveAction(action.id)
      setPhase('executing')
      const res = await api.executeAction(action.id, lang)
      setExec(res)
      for (let i = 1; i <= res.steps.length; i++) {
        await sleep(STEP_REVEAL_MS)
        setRevealed(i)
      }
      setPhase('verifying')
      await sleep(VERIFY_MS)
      setPhase('done')
      ;['journey', 'journeys', 'dashboard', 'claims', 'notifications'].forEach((k) => qc.invalidateQueries({ queryKey: k === 'journey' ? ['journey', id] : [k] }))
      qc.invalidateQueries({ queryKey: ['escalations'] })
      refreshSide()
    } catch (e) {
      setExecError(errorMessage(e))
      setPhase('error')
    }
  }

  if (journeyQ.isLoading || planQ.isLoading) return <Loading label={t('common.loading')} />
  if (journeyQ.error || !journey) return <ErrorBox message={errorMessage(journeyQ.error)} />
  if (planQ.error || !plan) return <ErrorBox message={errorMessage(planQ.error)} />

  const action = plan.action
  const isEscalation = plan.risk_class === 'HUMAN_ESCALATION_REQUIRED'
  const canConfirm = !!action && action.can_execute && (action.gate_decision === 'SAFE' || action.gate_decision === 'CONFIRM') && !isEscalation
  const isValueResolver = action?.action_type === 'CONFIRM_DOCUMENT_VALUE'
  const executing = phase === 'approving' || phase === 'executing' || phase === 'verifying'
  const verification = exec?.verification ?? null
  const doneSteps = plan.steps.filter((s) => s.status === 'DONE').length

  return (
    <div>
      <PageHeader
        crumbs={[{ label: t('nav.journeys'), to: '/journeys' }, { label: journey.title, to: `/journeys/${id}/investigation` }, { label: t('rec.title') }]}
        title={t('rec.title')}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-ink-800">{journey.title}</span>
            <StatePill state={journey.current_state} />
            {journey.external_status && (
              <span className="flex items-center gap-1 text-xs">
                <Building2 className="h-3.5 w-3.5 text-ink-400" /> Insurer: <StatePill state={journey.external_status} />
              </span>
            )}
          </span>
        }
        actions={
          <>
            <Link to={`/journeys/${id}/investigation`} className="btn-secondary"><Search className="h-4 w-4" /> Investigation</Link>
            <button className="btn-ghost" onClick={() => planQ.refetch()} disabled={planQ.isFetching || executing} title="Re-evaluate plan">
              {planQ.isFetching ? <Spinner /> : <RefreshCw className="h-4 w-4" />} Re-evaluate
            </button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          {/* BLOCKER */}
          <Card>
            <div className="label">Blocker</div>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <AlertTriangle className={`h-5 w-5 ${isEscalation ? 'text-rose-600' : 'text-amber-500'}`} />
              <h2 className="text-lg font-semibold text-ink-900">{plan.blocker_label}</h2>
              <span className="mono text-[11px] text-ink-500">{plan.blocker}</span>
              <StatePill state={plan.status} />
            </div>
            <p className="mt-2 text-sm text-ink-700">{plan.summary}</p>
            <div className="mt-4"><Bubble text={plan.message} source={plan.message_source} /></div>
          </Card>

          {/* HUMAN ESCALATION */}
          {isEscalation && (
            <Card className="border-rose-300 bg-rose-50">
              <div className="flex items-start gap-3">
                <ShieldAlert className="mt-0.5 h-6 w-6 shrink-0 text-rose-600" />
                <div className="flex-1">
                  <h3 className="text-base font-bold tracking-wide text-rose-800">HUMAN ESCALATION REQUIRED</h3>
                  <p className="mt-1 text-sm text-rose-900">
                    COVE2E detected conflicting states between systems (decision, settlement or payment). Reconciling them requires insurer authority, so COVE2E will <strong>not</strong> resolve this automatically. Automated actions on this journey are paused and an escalation packet has been prepared for a human agent.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {plan.escalation_id ? (
                      <Link to={`/escalations/${plan.escalation_id}`} className="btn-danger"><ExternalLink className="h-4 w-4" /> Open escalation packet</Link>
                    ) : (
                      <Link to="/escalations" className="btn-danger"><ExternalLink className="h-4 w-4" /> View escalations</Link>
                    )}
                    {claimId && <Link to={`/claims/${claimId}/tracking`} className="btn-secondary"><Radar className="h-4 w-4" /> Track claim</Link>}
                  </div>
                </div>
              </div>
            </Card>
          )}

          {/* RECOVERY PLAN */}
          <Card title={<span className="uppercase tracking-wide">{t('rec.plan')}</span>} subtitle={`${doneSteps} of ${plan.steps.length} steps complete`} action={<Badge tone={RISK_TONE[plan.risk_class]}>{stateLabel(plan.risk_class)}</Badge>}>
            <ol className="space-y-4">
              {plan.steps.map((s) => (
                <li key={s.key} className="flex items-start justify-between gap-3">
                  <StepRow n={s.order} label={s.label} description={s.description} status={s.status} />
                  <Badge tone={ACTOR_TONE[s.actor] ?? 'gray'} className="mt-1 shrink-0">{stateLabel(s.actor)}</Badge>
                </li>
              ))}
            </ol>
          </Card>

          {/* ACTION GATE */}
          {action && (
            <Card title={<span className="flex items-center gap-2 uppercase tracking-wide"><Lock className="h-4 w-4 text-brand-600" /> Action Gate</span>} subtitle="Every action passes through the permission gate before anything leaves COVE2E." action={<Badge tone={GATE_TONE[action.gate_decision]}>{action.gate_decision}</Badge>}>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="rounded-lg border border-ink-100 bg-ink-50/60 p-3 md:col-span-2">
                  <div className="label">{t('rec.proposed')}</div>
                  <div className="mt-1 text-sm font-semibold text-ink-900">{action.title}</div>
                  <p className="text-sm text-ink-600">{action.description}</p>
                  <div className="mono mt-1 text-[11px] text-ink-500">{action.action_type} · {action.status}</div>
                </div>

                <div className="rounded-lg border border-ink-100 bg-ink-50/60 p-3">
                  <div className="label">{t('rec.permission')}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <Badge tone={RISK_TONE[action.risk_class]}>{action.risk_class === 'AUTO_RECOVERABLE' ? <ShieldCheck className="h-3 w-3" /> : action.risk_class === 'HUMAN_ESCALATION_REQUIRED' ? <ShieldAlert className="h-3 w-3" /> : <Lock className="h-3 w-3" />}{RISK_TEXT[action.risk_class]}</Badge>
                    <Badge tone={GATE_TONE[action.gate_decision]}>Gate: {action.gate_decision}</Badge>
                  </div>
                </div>

                <div className="rounded-lg border border-ink-100 bg-ink-50/60 p-3">
                  <div className="label">{t('rec.reason')}</div>
                  {action.gate_reasons.length ? (
                    <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm text-ink-800">
                      {action.gate_reasons.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  ) : (
                    <p className="mt-1 text-sm text-ink-500">No additional reasons.</p>
                  )}
                </div>

                <div className="rounded-lg border border-ink-100 bg-ink-50/60 p-3">
                  <div className="label flex items-center gap-1"><ListChecks className="h-3.5 w-3.5" /> Gate checks</div>
                  <div className="mt-2">
                    <CheckList items={action.gate_checks.map((c) => ({ label: stateLabel(c.name), status: c.passed ? 'DONE' : 'ISSUE', detail: c.detail }))} />
                  </div>
                </div>

                <div className="rounded-lg border border-ink-100 bg-ink-50/60 p-3">
                  <div className="label">Prerequisites</div>
                  {action.prerequisites.length === 0 && <p className="mt-1 text-sm text-ink-500">None.</p>}
                  <ul className="mt-2 space-y-2">
                    {action.prerequisites.map((p) => (
                      <li key={p.key} className="text-sm">
                        <div className="flex items-start gap-2">
                          {p.satisfied ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />}
                          <div className="min-w-0 flex-1">
                            <div className={p.satisfied ? 'text-ink-900' : 'font-medium text-ink-900'}>{p.label}</div>
                            {p.hint && <div className="text-xs text-ink-500">{p.hint}</div>}
                            {!p.satisfied && p.document_type && claimId && phase === 'idle' && (
                              <DocumentUploader claimId={claimId} prereq={p} onUploaded={afterPrerequisiteChange} />
                            )}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Value resolver (document inconsistency) */}
              {isValueResolver && claimId && phase === 'idle' && <ValueResolver claimId={claimId} action={action} onConfirmed={afterPrerequisiteChange} />}

              {/* Confirm */}
              {!isEscalation && !isValueResolver && phase === 'idle' && (
                <div className="mt-5 border-t border-ink-100 pt-4">
                  <Bubble text={canConfirm ? 'I have prepared the recovery action. Confirm to submit the document.' : action.can_execute ? 'This action cannot be executed by COVE2E under the current gate decision.' : 'The recovery action is prepared but a prerequisite is still outstanding. Complete it above and the gate will re-evaluate.'} />
                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <button className="btn-primary !px-6 !py-3 text-base" disabled={!canConfirm} onClick={() => runRecovery(action)}>
                      <ShieldCheck className="h-5 w-5" /> Confirm Recovery
                    </button>
                    <span className="text-xs text-ink-500">{t('rec.confirm')} · approve → execute via workflow → verify with insurer</span>
                  </div>
                  {!canConfirm && (
                    <p className="mt-2 flex items-center gap-1 text-xs text-ink-500"><Lock className="h-3 w-3" /> Enabled once every prerequisite is satisfied and the gate returns SAFE or CONFIRM.</p>
                  )}
                </div>
              )}

              {phase === 'error' && (
                <div className="mt-5 space-y-2 border-t border-ink-100 pt-4">
                  <ErrorBox message={execError ?? 'Recovery execution failed.'} />
                  <button className="btn-secondary" onClick={() => { setPhase('idle'); planQ.refetch() }}><RefreshCw className="h-4 w-4" /> Re-evaluate plan</button>
                </div>
              )}
            </Card>
          )}

          {/* EXECUTION */}
          {(executing || phase === 'done') && (
            <Card className={phase === 'done' ? '' : 'border-brand-200 ring-1 ring-brand-100'}>
              <h3 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-ink-900">
                {phase === 'done' ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <Spinner className="h-4 w-4 text-brand-600" />}
                {phase === 'approving' ? 'RECORDING YOUR CONFIRMATION...' : phase === 'executing' ? 'EXECUTING RECOVERY...' : phase === 'verifying' ? 'VERIFYING EXTERNAL STATE...' : 'ACTION EXECUTED ✓'}
              </h3>
              {phase === 'executing' && !exec && <p className="mt-2 flex items-center gap-2 text-xs text-ink-500"><Workflow className="h-3.5 w-3.5" /> Handing the approved action to the recovery workflow…</p>}

              {exec && (
                <ul className="mt-4 space-y-2.5">
                  {exec.steps.map((s, i) => {
                    const shown = i < revealed || phase === 'done'
                    const active = i === revealed && phase === 'executing'
                    return (
                      <li key={s.key} className={`flex items-start gap-2.5 text-sm transition-opacity duration-300 ${shown || active ? 'opacity-100' : 'opacity-25'}`}>
                        {shown ? <StatusIcon status={s.status} className="mt-0.5 h-4 w-4 shrink-0" /> : active ? <Spinner className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" /> : <span className="mt-1 h-3 w-3 shrink-0 rounded-full border border-ink-200" />}
                        <div>
                          <div className="font-medium text-ink-900">{s.label}</div>
                          {shown && s.detail && <div className="text-xs text-ink-500">{s.detail}</div>}
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}

              {phase === 'verifying' && (
                <div className="mt-4 flex items-center gap-2 rounded-lg bg-brand-50 p-3 text-sm text-brand-800"><Spinner /> {t('rec.verifying')} Re-querying the insurer to confirm the state actually changed.</div>
              )}

              {phase === 'done' && exec && (
                <div className="mt-5 space-y-4 border-t border-ink-100 pt-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <ExecutorBadge executor={exec.executor} />
                    {exec.workflow_run_id && <span className="mono text-[11px] text-ink-500">run {exec.workflow_run_id}</span>}
                    {exec.recovery_status && <StatePill state={exec.recovery_status} />}
                  </div>

                  {verification ? (
                    <>
                      <div className="rounded-lg border border-ink-100 bg-ink-50/60 p-3">
                        <div className="label">Outcome verification</div>
                        <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
                          <span className="text-ink-500">{t('rec.before')}:</span> <StatePill state={verification.before_state} />
                          <ArrowRight className="h-4 w-4 text-ink-400" />
                          <span className="text-ink-500">{t('rec.after')}:</span> <StatePill state={verification.after_state} />
                          {verification.expected_state && <span className="text-xs text-ink-500">(expected {stateLabel(verification.expected_state)})</span>}
                        </div>
                        {(verification.journey_state_before || verification.journey_state_after) && (
                          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-ink-600">
                            Journey: <StatePill state={verification.journey_state_before} /> <ArrowRight className="h-3 w-3 text-ink-400" /> <StatePill state={verification.journey_state_after} />
                          </div>
                        )}
                        <p className="mt-2 text-sm text-ink-700">{verification.message}</p>
                      </div>

                      {verification.outcome === 'VERIFIED' && (
                        <div className="flex items-center gap-3 rounded-lg border border-emerald-300 bg-emerald-50 p-4">
                          <CheckCircle2 className="h-6 w-6 text-emerald-600" />
                          <div>
                            <div className="text-base font-bold tracking-wide text-emerald-800">RECOVERY SUCCESSFUL ✓</div>
                            <div className="text-xs text-emerald-700">External state verified with the insurer after execution.</div>
                          </div>
                        </div>
                      )}
                      {verification.outcome === 'UNCHANGED' && (
                        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4">
                          <AlertTriangle className="h-6 w-6 text-amber-600" />
                          <div className="flex-1">
                            <div className="text-base font-bold tracking-wide text-amber-800">REINVESTIGATE</div>
                            <div className="text-xs text-amber-700">The insurer state did not change as expected. COVE2E will not assume success.</div>
                          </div>
                          <Link to={`/journeys/${id}/investigation`} className="btn-secondary"><Search className="h-4 w-4" /> Re-investigate</Link>
                        </div>
                      )}
                      {(verification.outcome === 'CONFLICT' || verification.outcome === 'ERROR') && (
                        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-rose-300 bg-rose-50 p-4">
                          <AlertOctagon className="h-6 w-6 text-rose-600" />
                          <div className="flex-1">
                            <div className="text-base font-bold tracking-wide text-rose-800">{verification.outcome === 'CONFLICT' ? 'ESCALATED' : 'VERIFICATION ERROR'}</div>
                            <div className="text-xs text-rose-700">{verification.outcome === 'CONFLICT' ? 'Conflicting states detected after execution. A human agent must reconcile.' : 'The external state could not be verified.'}</div>
                          </div>
                          {exec.escalation_id ? (
                            <Link to={`/escalations/${exec.escalation_id}`} className="btn-danger"><ExternalLink className="h-4 w-4" /> Open escalation</Link>
                          ) : (
                            <Link to="/escalations" className="btn-danger"><ExternalLink className="h-4 w-4" /> Escalations</Link>
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">No verification result was returned. Treat the outcome as unconfirmed.</div>
                  )}

                  <div>
                    <div className="label mb-2">Final response</div>
                    <Bubble text={exec.final_message} tone={verification?.outcome === 'VERIFIED' ? 'success' : 'default'} />
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {claimId && <Link to={`/claims/${claimId}/tracking`} className="btn-primary"><Radar className="h-4 w-4" /> Track claim</Link>}
                    <button className="btn-secondary" onClick={() => navigate('/dashboard')}><LayoutDashboard className="h-4 w-4" /> Back to dashboard</button>
                  </div>
                </div>
              )}
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-5">
          <InsurerViewCard externalId={externalId} />

          <Card title={<span className="flex items-center gap-2"><History className="h-4 w-4 text-ink-400" /> Recovery attempts</span>}>
            {attemptsQ.isLoading ? (
              <Loading />
            ) : attemptsQ.error ? (
              <ErrorBox message={errorMessage(attemptsQ.error)} />
            ) : !attemptsQ.data?.length ? (
              <p className="text-sm text-ink-500">No recovery attempts yet.</p>
            ) : (
              <ul className="space-y-3">
                {[...attemptsQ.data].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).map((a) => (
                  <li key={a.id} className="rounded-lg border border-ink-100 p-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium text-ink-900">{stateLabel(a.blocker)}</span>
                      <StatePill state={a.status} />
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-ink-600">
                      <StatePill state={a.before_state} /> <ArrowRight className="h-3 w-3 text-ink-400" /> <StatePill state={a.after_state} />
                    </div>
                    <div className="mt-1 text-xs text-ink-400">{relDays(a.created_at) || 'today'} · {fmtDateTime(a.created_at)}</div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title={<span className="flex items-center gap-2"><ScrollText className="h-4 w-4 text-ink-400" /> Audit trail</span>} subtitle="Every action, actor and state change is recorded.">
            {auditQ.isLoading ? (
              <Loading />
            ) : auditQ.error ? (
              <ErrorBox message={errorMessage(auditQ.error)} />
            ) : !auditQ.data?.length ? (
              <p className="text-sm text-ink-500">No audit records yet.</p>
            ) : (
              <ul className="scrollbar-thin max-h-[420px] space-y-2 overflow-y-auto pr-1">
                {[...auditQ.data].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).map((r) => (
                  <li key={r.id} className="border-b border-ink-100 pb-2 last:border-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={toneForState(r.result) === 'gray' ? 'blue' : toneForState(r.result)}>{stateLabel(r.action)}</Badge>
                      <Badge tone={ACTOR_TONE[r.actor] ?? 'gray'}>{stateLabel(r.actor)}</Badge>
                    </div>
                    <div className="mono mt-1 text-[11px] text-ink-500">
                      {fmtDateTime(r.created_at)}
                      {(r.previous_state || r.new_state) && <> · {r.previous_state ?? '—'} → {r.new_state ?? '—'}</>}
                    </div>
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
