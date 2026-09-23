import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertOctagon, AlertTriangle, ArrowRight, Bot, Building2, CheckCircle2, Circle, Clock, Crosshair, FileSearch, Mic, Radar, Search, ShieldAlert, Square, UserCheck, Wrench } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import { useI18n } from '../i18n'
import { useVoice } from '../hooks/useVoice'
import { fmtDateTime, sleep, stateLabel } from '../utils/format'
import { Badge, Card, ErrorBox, Loading, PageHeader, ProgressBar, Spinner, StatePill, StatusIcon, Timeline, toneForState } from '../components/ui'
import type { InvestigationCheck, InvestigationResult, JourneyDetail } from '../types/api'

const DEFAULT_MESSAGE = 'My claim has been stuck for eight days.'

/** Order and labels of the deterministic checks the backend runs. */
const CHECK_PLACEHOLDERS: { name: string; label: string }[] = [
  { name: 'policy', label: 'Policy' },
  { name: 'claim_state', label: 'Claim state' },
  { name: 'documents', label: 'Documents' },
  { name: 'insurer_query', label: 'Insurer query' },
  { name: 'timeline', label: 'Timeline' },
  { name: 'previous_actions', label: 'Previous actions' },
  { name: 'external_state', label: 'External insurer state' },
]
const REVEAL_MS = 450

const BLOCKER_TONE: Record<string, string> = {
  none: 'green',
  resolved: 'green',
  ready_to_submit: 'blue',
  awaiting_insurer: 'blue',
  insurer_delay: 'amber',
  missing_requested_document: 'amber',
  requested_document_not_attached: 'amber',
  missing_required_documents: 'amber',
  document_inconsistency: 'amber',
  conflicting_external_state: 'red',
  escalated: 'red',
  unsupported_state: 'red',
}

function SourceBadge({ source }: { source: 'AI' | 'DETERMINISTIC' | string }) {
  return <Badge tone={source === 'AI' ? 'purple' : 'blue'}>{source === 'AI' ? 'Sarvam AI' : 'Deterministic'}</Badge>
}

function LabelBlock({ label, children, className = '' }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-ink-100 bg-ink-50/60 p-3 ${className}`}>
      <div className="label">{label}</div>
      <div className="mt-1.5">{children}</div>
    </div>
  )
}

/** Animated / resolved check panel. */
function ChecksPanel({ running, revealed, checks }: { running: boolean; revealed: number; checks: InvestigationCheck[] | null }) {
  const byName = new Map((checks ?? []).map((c) => [c.name, c]))
  return (
    <Card className={running ? 'border-brand-200 ring-1 ring-brand-100' : ''}>
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-ink-900">
          {running ? <Spinner className="h-4 w-4 text-brand-600" /> : <FileSearch className="h-4 w-4 text-brand-600" />}
          {running ? 'INVESTIGATING JOURNEY...' : 'INVESTIGATION CHECKS'}
        </h3>
        {checks && !running && (
          <div className="flex gap-1.5 text-xs">
            <Badge tone="green">{checks.filter((c) => c.status === 'OK').length} OK</Badge>
            <Badge tone="amber">{checks.filter((c) => c.status === 'ISSUE').length} issues</Badge>
          </div>
        )}
      </div>
      <ul className="mt-4 space-y-2.5">
        {CHECK_PLACEHOLDERS.map((p, i) => {
          const real = !running ? byName.get(p.name) : undefined
          let icon: React.ReactNode
          if (real) icon = <StatusIcon status={real.status} className="mt-0.5 h-4 w-4 shrink-0" />
          else if (i < revealed) icon = <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
          else if (i === revealed && running) icon = <Spinner className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
          else icon = <Circle className="mt-0.5 h-4 w-4 shrink-0 text-ink-200" />
          const visible = running ? i <= revealed : true
          return (
            <li key={p.name} className={`flex items-start gap-2.5 text-sm transition-opacity duration-300 ${visible ? 'opacity-100' : 'opacity-30'}`}>
              {icon}
              <div className="min-w-0">
                <div className={`font-medium ${real?.status === 'ISSUE' ? 'text-amber-800' : 'text-ink-900'}`}>{real?.label ?? p.label}</div>
                {real && <div className="text-xs text-ink-600">{real.finding}</div>}
                {!real && running && i < revealed && <div className="text-xs text-ink-400">Checked</div>}
              </div>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

function InsurerViewCard({ externalId }: { externalId: string | null | undefined }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['insurer-claim', externalId],
    queryFn: () => api.insurerClaim(externalId as string),
    enabled: !!externalId,
  })
  return (
    <Card title="Insurer view (mock)" subtitle="Live read from the mock insurer system">
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

function EscalateForm({ journeyId, defaultProblem, onDone }: { journeyId: string; defaultProblem: string; onDone: (id: string) => void }) {
  const [problem, setProblem] = useState(defaultProblem)
  const [reason, setReason] = useState('User requested human review.')
  const m = useMutation({
    mutationFn: () => api.createEscalation({ journey_id: journeyId, problem, reason }),
    onSuccess: (esc) => onDone(esc.id),
  })
  return (
    <form
      className="mt-3 space-y-2 rounded-lg border border-rose-200 bg-rose-50/50 p-3"
      onSubmit={(e) => {
        e.preventDefault()
        m.mutate()
      }}
    >
      <div>
        <label className="label">Problem</label>
        <input className="input mt-1" value={problem} onChange={(e) => setProblem(e.target.value)} required />
      </div>
      <div>
        <label className="label">Reason for escalation</label>
        <input className="input mt-1" value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      {m.error && <ErrorBox message={errorMessage(m.error)} />}
      <button type="submit" className="btn-danger" disabled={m.isPending || !problem.trim()}>
        {m.isPending ? <Spinner /> : <ShieldAlert className="h-4 w-4" />} Create escalation packet
      </button>
    </form>
  )
}

export default function JourneyInvestigationPage() {
  const { id = '' } = useParams()
  const { lang, t } = useI18n()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const voice = useVoice(lang)

  const journeyQ = useQuery({ queryKey: ['journey', id], queryFn: () => api.journey(id), enabled: !!id })
  const journey: JourneyDetail | undefined = journeyQ.data

  const [message, setMessage] = useState(DEFAULT_MESSAGE)
  const [result, setResult] = useState<InvestigationResult | null>(null)
  const [running, setRunning] = useState(false)
  const [revealed, setRevealed] = useState(0)
  const [runError, setRunError] = useState<string | null>(null)
  const [showEscalate, setShowEscalate] = useState(false)
  const autoRan = useRef(false)

  const run = useCallback(
    async (msg: string | null) => {
      if (running || !id) return
      setRunning(true)
      setRunError(null)
      setRevealed(0)
      const request = api.investigateJourney(id, msg, lang)
      const reveal = (async () => {
        for (let i = 1; i <= CHECK_PLACEHOLDERS.length; i++) {
          await sleep(REVEAL_MS)
          setRevealed(i)
        }
      })()
      try {
        const [res] = await Promise.all([request, reveal])
        setResult(res)
        qc.invalidateQueries({ queryKey: ['journey', id] })
        qc.invalidateQueries({ queryKey: ['journeys'] })
      } catch (e) {
        setRunError(errorMessage(e))
      } finally {
        setRunning(false)
      }
    },
    [id, lang, qc, running],
  )

  // Auto-run once on mount when no previous investigation exists; otherwise show the last one.
  useEffect(() => {
    if (!journey || autoRan.current) return
    autoRan.current = true
    if (journey.last_investigation) setResult(journey.last_investigation)
    else run(null)
  }, [journey, run])

  const escalationsQ = useQuery({ queryKey: ['escalations'], queryFn: api.escalations, enabled: !!result?.requires_escalation })
  const linkedEscalation = escalationsQ.data?.find((e) => e.journey_id === id)

  const toggleMic = async () => {
    if (voice.recording) {
      const text = await voice.stop()
      if (text) setMessage(text)
    } else {
      await voice.start()
    }
  }

  if (journeyQ.isLoading) return <Loading label={t('common.loading')} />
  if (journeyQ.error || !journey) return <ErrorBox message={errorMessage(journeyQ.error)} />

  const claimId = journey.claim_id ?? journey.claim?.id ?? null
  const blockerTone = result ? BLOCKER_TONE[result.blocker] ?? 'amber' : 'gray'
  const confidencePct = result ? Math.round(result.confidence * (result.confidence <= 1 ? 100 : 1)) : 0

  return (
    <div>
      <PageHeader
        crumbs={[{ label: t('nav.journeys'), to: '/journeys' }, { label: journey.title }]}
        title={t('inv.title')}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-ink-800">{journey.title}</span>
            <StatePill state={journey.current_state} />
            <Badge tone={toneForState(journey.health)}>{stateLabel(journey.health)}</Badge>
            {journey.external_status && (
              <span className="flex items-center gap-1 text-xs">
                <Building2 className="h-3.5 w-3.5 text-ink-400" /> Insurer: <StatePill state={journey.external_status} />
              </span>
            )}
          </span>
        }
        actions={
          <>
            {claimId && (
              <Link to={`/claims/${claimId}/tracking`} className="btn-secondary">
                <Radar className="h-4 w-4" /> Track claim
              </Link>
            )}
            <Link to={`/journeys/${id}/recovery`} className="btn-primary">
              <Wrench className="h-4 w-4" /> Prepare recovery
            </Link>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        {/* Main column */}
        <div className="space-y-5 xl:col-span-2">
          {/* Ask bar */}
          <Card>
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                run(message.trim() || null)
              }}
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white"><Bot className="h-4 w-4" /></div>
              <button type="button" onClick={toggleMic} disabled={!voice.supported || voice.busy || running} title={t('ask.mic')} className={`btn-secondary !px-3 ${voice.recording ? 'animate-pulse border-rose-300 text-rose-600' : ''}`}>
                {voice.busy ? <Spinner /> : voice.recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              <input className="input" value={message} onChange={(e) => setMessage(e.target.value)} placeholder={voice.recording ? t('ask.listening') : t('ask.placeholder')} disabled={running} />
              <button type="submit" className="btn-primary whitespace-nowrap" disabled={running}>
                {running ? <Spinner /> : <Search className="h-4 w-4" />} Investigate
              </button>
            </form>
            {voice.error && <p className="mt-2 text-xs text-amber-700">{voice.error}</p>}
            {runError && <div className="mt-3"><ErrorBox message={runError} /></div>}
          </Card>

          {/* Checks (animated while running) */}
          {(running || result) && <ChecksPanel running={running} revealed={revealed} checks={result?.checks ?? null} />}

          {/* Result */}
          {result && !running && (
            <>
              {/* Explanation bubble */}
              <div className="flex gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white"><Bot className="h-4 w-4" /></div>
                <div className="flex-1 rounded-2xl rounded-tl-sm border border-ink-200 bg-white px-4 py-3 shadow-card">
                  <p className="whitespace-pre-line text-sm text-ink-900">{result.explanation}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <SourceBadge source={result.explanation_source} />
                    {result.days_stuck != null && result.days_stuck > 0 && (
                      <Badge tone="amber"><Clock className="h-3 w-3" /> Stuck for {result.days_stuck} day{result.days_stuck === 1 ? '' : 's'}</Badge>
                    )}
                    {result.requires_confirmation && <Badge tone="amber"><UserCheck className="h-3 w-3" /> User confirmation required</Badge>}
                    {result.requires_escalation && <Badge tone="red"><ShieldAlert className="h-3 w-3" /> Human escalation required</Badge>}
                  </div>
                </div>
              </div>

              <Card>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <LabelBlock label={t('inv.currentState')}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-ink-900">{result.current_state_label}</span>
                      {result.external_status && <StatePill state={result.external_status} />}
                    </div>
                  </LabelBlock>

                  <LabelBlock label={t('inv.blocker')} className={blockerTone === 'red' ? 'border-rose-200 bg-rose-50' : blockerTone === 'amber' ? 'border-amber-200 bg-amber-50' : blockerTone === 'green' ? 'border-emerald-200 bg-emerald-50' : ''}>
                    <div className="flex items-start gap-2">
                      {blockerTone === 'red' ? <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" /> : blockerTone === 'amber' ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" /> : <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />}
                      <div>
                        <div className="text-[10px] font-bold uppercase tracking-wider text-ink-500">Root cause</div>
                        <div className={`text-sm font-semibold ${blockerTone === 'red' ? 'text-rose-800' : blockerTone === 'amber' ? 'text-amber-800' : 'text-ink-900'}`}>{result.blocker_label}</div>
                        <div className="mono mt-0.5 text-[11px] text-ink-500">{result.blocker}</div>
                      </div>
                    </div>
                  </LabelBlock>

                  <LabelBlock label={t('inv.evidence')} className="md:col-span-2">
                    {result.evidence.length ? (
                      <ul className="space-y-1.5">
                        {result.evidence.map((ev, i) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-ink-800">
                            <FileSearch className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-500" />
                            <span>{ev}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-ink-500">No evidence recorded.</p>
                    )}
                  </LabelBlock>

                  <LabelBlock label={t('inv.affected')}>
                    <div className="flex items-center gap-2 text-sm font-medium text-ink-900">
                      <Crosshair className="h-4 w-4 text-ink-400" /> {stateLabel(result.affected_step) || '—'}
                    </div>
                  </LabelBlock>

                  <LabelBlock label={t('inv.nextAction')}>
                    <div className="flex items-center gap-2 text-sm font-medium text-ink-900">
                      <ArrowRight className="h-4 w-4 text-brand-600" /> {result.next_action_label}
                    </div>
                    <div className="mono mt-0.5 text-[11px] text-ink-500">{result.next_action}</div>
                  </LabelBlock>

                  <LabelBlock label={t('inv.confidence')}>
                    <div className="flex items-center gap-3">
                      <ProgressBar value={confidencePct} tone={confidencePct >= 80 ? 'green' : confidencePct >= 50 ? 'amber' : 'red'} className="flex-1" />
                      <span className="text-sm font-semibold text-ink-900">{confidencePct}%</span>
                    </div>
                  </LabelBlock>

                  <LabelBlock label={t('inv.escalation')}>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={result.requires_escalation ? 'red' : 'green'}>{result.requires_escalation ? 'Yes' : 'No'}</Badge>
                      {result.requires_confirmation && <Badge tone="amber">User confirmation required</Badge>}
                    </div>
                  </LabelBlock>
                </div>

                {/* Bottom actions */}
                <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-ink-100 pt-4">
                  <Link to={`/journeys/${id}/recovery`} className="btn-primary">
                    <Wrench className="h-4 w-4" /> Prepare recovery
                  </Link>
                  {claimId && (
                    <Link to={`/claims/${claimId}/tracking`} className="btn-secondary">
                      <Radar className="h-4 w-4" /> Track claim
                    </Link>
                  )}
                  {result.requires_escalation ? (
                    linkedEscalation ? (
                      <Link to={`/escalations/${linkedEscalation.id}`} className="btn-danger">
                        <ShieldAlert className="h-4 w-4" /> View escalation
                      </Link>
                    ) : escalationsQ.isLoading ? (
                      <span className="flex items-center gap-2 text-xs text-ink-500"><Spinner /> Locating escalation…</span>
                    ) : (
                      <button className="btn-danger" onClick={() => setShowEscalate((v) => !v)}>
                        <ShieldAlert className="h-4 w-4" /> Escalate to human
                      </button>
                    )
                  ) : (
                    <button className="btn-ghost" onClick={() => setShowEscalate((v) => !v)}>
                      <ShieldAlert className="h-4 w-4" /> Escalate to human
                    </button>
                  )}
                </div>
                {showEscalate && (
                  <EscalateForm journeyId={id} defaultProblem={result.blocker_label} onDone={(escId) => { qc.invalidateQueries({ queryKey: ['escalations'] }); navigate(`/escalations/${escId}`) }} />
                )}
              </Card>
            </>
          )}
        </div>

        {/* Right column */}
        <div className="space-y-5">
          <Card title="Journey timeline" subtitle={`${journey.timeline.length} events · last update ${fmtDateTime(journey.updated_at)}`}>
            <Timeline events={[...journey.timeline].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())} />
          </Card>
          <InsurerViewCard externalId={journey.claim?.external_claim_id} />
        </div>
      </div>
    </div>
  )
}
