import React, { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { BookOpen, ChevronDown, ChevronRight, Mic, Send, Sparkles, Square } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import { useI18n } from '../i18n'
import { useVoice } from '../hooks/useVoice'
import { fmtDate, inr, pct } from '../utils/format'
import { Badge, Card, Disclaimer, ErrorBox, Loading, PageHeader, ProgressBar, Spinner, StatePill } from '../components/ui'
import type { FactType, PolicyAnswer } from '../types/api'

const QUICK = ['Is ICU covered?', 'What is my room rent limit?', 'Do I have a waiting period?', 'Is dental treatment covered?', 'When does my policy expire?', 'What documents do I need for a claim?']

const FACT: Record<FactType, { label: string; tone: string }> = {
  POLICY_FACT: { label: 'Policy Fact', tone: 'green' },
  AI_INTERPRETATION: { label: 'AI Interpretation', tone: 'purple' },
  MISSING_INFORMATION: { label: 'Missing Information', tone: 'amber' },
  GENERAL_GUIDANCE: { label: 'General Guidance', tone: 'blue' },
  EXTERNAL_INSURER_DECISION: { label: 'External Insurer Decision', tone: 'gray' },
}
const COVERAGE_TONE: Record<PolicyAnswer['coverage'], string> = { YES: 'green', NO: 'red', CONDITIONAL: 'amber', UNKNOWN: 'gray' }

interface QA { id: number; question: string; answer: PolicyAnswer; at: string }

function AnswerBlock({ qa }: { qa: QA }) {
  const [open, setOpen] = useState(false)
  const a = qa.answer
  const rows: { label: string; value: string }[] = [
    { label: 'Why', value: a.why },
    { label: 'Important condition', value: a.important_condition },
    { label: 'What you should do', value: a.what_you_should_do },
    { label: 'Source', value: a.source },
  ]
  return (
    <div className="card card-pad animate-fadeUp">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="text-sm font-semibold text-ink-900">Q: {qa.question}</div>
        <span className="text-xs text-ink-400">{qa.at}</span>
      </div>
      <div className="mt-3 rounded-lg bg-ink-50 p-3">
        <div className="label">Answer</div>
        <p className="mt-1 whitespace-pre-line text-sm text-ink-900">{a.answer}</p>
      </div>
      <dl className="mt-3 space-y-2 text-sm">
        <div className="flex items-start gap-3">
          <dt className="label w-40 shrink-0 pt-0.5">Coverage</dt>
          <dd><Badge tone={COVERAGE_TONE[a.coverage]}>{a.coverage}</Badge></dd>
        </div>
        {rows.map((r) => (
          <div key={r.label} className="flex items-start gap-3">
            <dt className="label w-40 shrink-0 pt-0.5">{r.label}</dt>
            <dd className={`flex-1 ${r.label === 'Source' ? 'mono text-ink-600' : 'text-ink-800'}`}>{r.value || '—'}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {a.fact_types.map((f) => (
          <Badge key={f} tone={FACT[f]?.tone ?? 'gray'}>{FACT[f]?.label ?? f}</Badge>
        ))}
        <Badge tone={a.knowledge_backend === 'cognee' ? 'purple' : 'gray'}>{a.knowledge_backend === 'cognee' ? 'Cognee' : 'Local fallback'}</Badge>
        <div className="ml-auto flex items-center gap-2 text-xs text-ink-500">
          Confidence <ProgressBar value={a.confidence * 100} tone={a.confidence >= 0.75 ? 'green' : a.confidence >= 0.5 ? 'brand' : 'amber'} className="w-20" /> {pct(a.confidence * 100)}
        </div>
      </div>
      {a.retrieved_context.length > 0 && (
        <div className="mt-3 border-t border-ink-100 pt-3">
          <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-1 text-xs font-semibold text-ink-600 hover:text-brand-700">
            {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />} Retrieved policy context ({a.retrieved_context.length})
          </button>
          {open && (
            <ul className="mt-2 space-y-1.5">
              {a.retrieved_context.map((c, i) => (
                <li key={i} className="mono rounded bg-ink-50 p-2 text-ink-700">{c}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

export default function PolicyCompanionPage() {
  const { id = '' } = useParams()
  const { t, lang } = useI18n()
  const voice = useVoice(lang)
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState<QA[]>([])
  const policy = useQuery({ queryKey: ['policy', id], queryFn: () => api.policy(id), enabled: !!id })

  const ask = useMutation({
    mutationFn: (q: string) => api.askPolicy(id, q, lang),
    onSuccess: (res) => {
      setHistory((h) => [{ id: Date.now(), question: res.question, answer: res.answer, at: new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) }, ...h])
      setQuestion('')
    },
  })

  const submit = (q: string) => {
    const text = q.trim()
    if (!text || ask.isPending) return
    ask.mutate(text)
  }

  const toggleMic = async () => {
    if (voice.recording) {
      const text = await voice.stop()
      if (text) setQuestion(text)
    } else {
      await voice.start()
    }
  }

  if (policy.isLoading) return <Loading label={t('common.loading')} />
  if (policy.error || !policy.data) return <ErrorBox message={errorMessage(policy.error)} />
  const p = policy.data

  return (
    <div>
      <PageHeader
        crumbs={[{ label: t('nav.policies'), to: '/policies' }, { label: p.plan_name, to: `/policies/${id}` }, { label: t('policy.companion') }]}
        title={t('policy.companion')}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            {p.insurer} · {p.plan_name} <Badge tone="blue">{p.policy_type}</Badge> <StatePill state={p.status} />
            <span>{inr(p.sum_insured)} · expires {fmtDate(p.end_date)}</span>
          </span>
        }
        actions={<Link to={`/policies/${id}`} className="btn-secondary"><BookOpen className="h-4 w-4" /> Policy details</Link>}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                submit(question)
              }}
            >
              <button type="button" onClick={toggleMic} disabled={!voice.supported || voice.busy} title={t('ask.mic')} className={`btn-secondary !px-3 ${voice.recording ? 'animate-pulseSoft border-rose-300 text-rose-600' : ''}`}>
                {voice.busy ? <Spinner /> : voice.recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              <input className="input" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={voice.recording ? t('ask.listening') : 'Ask anything about this policy…'} />
              <button type="submit" className="btn-primary !px-3" disabled={ask.isPending || !question.trim()}>
                {ask.isPending ? <Spinner /> : <Send className="h-4 w-4" />}
              </button>
            </form>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {QUICK.map((q) => (
                <button key={q} type="button" onClick={() => submit(q)} disabled={ask.isPending} className="rounded-full border border-ink-200 bg-white px-3 py-1 text-xs font-medium text-ink-700 hover:border-brand-300 hover:text-brand-700 disabled:opacity-50">
                  <Sparkles className="mr-1 inline h-3 w-3 text-brand-500" />{q}
                </button>
              ))}
            </div>
            {voice.error && <div className="mt-3 rounded-lg bg-amber-50 p-2 text-xs text-amber-700">{voice.error}</div>}
            {ask.error && <div className="mt-3"><ErrorBox message={errorMessage(ask.error)} /></div>}
            {ask.isPending && <p className="mt-3 flex items-center gap-2 text-xs text-ink-500"><Spinner className="h-3.5 w-3.5" /> Retrieving policy context → grounding the answer…</p>}
            <Disclaimer>COVE2E never fabricates coverage. The insurer makes the final decision.</Disclaimer>
          </Card>

          {history.length === 0 && !ask.isPending && (
            <div className="rounded-xl border border-dashed border-ink-200 bg-white px-6 py-10 text-center text-sm text-ink-500">
              Ask a question or pick a suggestion. Every answer is labelled by fact type and cites the policy section it came from.
            </div>
          )}
          {history.map((qa) => <AnswerBlock key={qa.id} qa={qa} />)}
        </div>

        <div className="space-y-4">
          <Card title="Fact type legend" subtitle="How to read each answer">
            <ul className="space-y-2 text-xs text-ink-600">
              {(Object.keys(FACT) as FactType[]).map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <Badge tone={FACT[f].tone}>{FACT[f].label}</Badge>
                </li>
              ))}
            </ul>
            <dl className="mt-3 space-y-1.5 text-[11px] text-ink-500">
              <div><span className="font-semibold text-emerald-700">Policy Fact</span> — stated in the document, with a section reference.</div>
              <div><span className="font-semibold text-violet-700">AI Interpretation</span> — inference drawn from policy text; verify with the insurer.</div>
              <div><span className="font-semibold text-amber-700">Missing Information</span> — the document does not say; COVE2E will not guess.</div>
              <div><span className="font-semibold text-brand-700">General Guidance</span> — common practice, not specific to this policy.</div>
              <div><span className="font-semibold text-ink-700">External Insurer Decision</span> — only the insurer can decide this.</div>
            </dl>
          </Card>
          <Card title="Knowledge layer">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={p.knowledge_indexed ? 'green' : 'amber'}>{p.knowledge_indexed ? 'Indexed' : 'Not indexed'}</Badge>
              <Badge tone={p.knowledge_backend === 'cognee' ? 'purple' : 'gray'}>{p.knowledge_backend === 'cognee' ? 'Cognee' : 'Local fallback'}</Badge>
            </div>
            <p className="mt-2 text-xs text-ink-500">{p.coverages.length} coverage lines · {p.conditions.length} conditions available for retrieval.</p>
          </Card>
        </div>
      </div>
    </div>
  )
}
