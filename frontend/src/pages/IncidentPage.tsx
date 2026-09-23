import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, Bot, FileText, ListChecks, Mic, Route as RouteIcon, ShieldCheck, Sparkles, Square, Stethoscope } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import type { IncidentAnalyzeResponse } from '../types/api'
import { useI18n } from '../i18n'
import { useVoice } from '../hooks/useVoice'
import { Badge, Card, Disclaimer, ErrorBox, PageHeader, ProgressBar, Spinner, StatusIcon } from '../components/ui'
import { pct, titleCase } from '../utils/format'

const EXAMPLES = ['My father was hospitalized yesterday.', 'My car was hit while parked.', 'My phone was stolen.', 'I had an accident.']

function urgencyTone(u: string): string {
  if (u === 'HIGH') return 'red'
  if (u === 'MEDIUM') return 'amber'
  return 'green'
}

function Block({ icon: Icon, label, children }: { icon: React.ComponentType<{ className?: string }>; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-ink-100 bg-ink-50/60 p-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-brand-600 ring-1 ring-ink-200"><Icon className="h-4 w-4" /></div>
      <div className="min-w-0 flex-1">
        <div className="label">{label}</div>
        <div className="mt-1 text-sm text-ink-900">{children}</div>
      </div>
    </div>
  )
}

export default function IncidentPage() {
  const { lang, t } = useI18n()
  const navigate = useNavigate()
  const voice = useVoice(lang)
  const [text, setText] = useState('')

  const analyze = useMutation({
    mutationFn: (description: string) => api.analyzeIncident(description, lang),
  })

  const submit = (e?: React.FormEvent) => {
    e?.preventDefault()
    const d = text.trim()
    if (!d) return
    analyze.mutate(d)
  }

  const toggleMic = async () => {
    if (voice.recording) {
      const transcript = await voice.stop()
      if (transcript) setText((prev) => (prev ? `${prev} ${transcript}` : transcript))
    } else {
      await voice.start()
    }
  }

  const result: IncidentAnalyzeResponse | undefined = analyze.data
  const c = result?.classification

  const startClaimHref = c?.matched_policy_id
    ? `/claims/new?policy_id=${encodeURIComponent(c.matched_policy_id)}&incident_type=${encodeURIComponent(c.incident_type)}&claim_type=${encodeURIComponent(c.suggested_claim_type ?? '')}&description=${encodeURIComponent(text.trim())}`
    : null

  return (
    <div>
      <PageHeader
        title={t('nav.incidents')}
        subtitle="Describe what happened in your own words. COVE2E maps it to your policy, the right claim type and what you need next."
        crumbs={[{ label: t('nav.dashboard'), to: '/dashboard' }, { label: t('nav.incidents') }]}
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Describe what happened" subtitle="Type or speak in English, Hindi or Marathi.">
            <form onSubmit={submit} className="space-y-3">
              <div className="relative">
                <textarea
                  className="input min-h-[140px] resize-y pr-12"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder={voice.recording ? t('ask.listening') : 'e.g. My father was admitted to hospital yesterday with chest pain…'}
                />
                <button
                  type="button"
                  onClick={toggleMic}
                  disabled={!voice.supported || voice.busy}
                  title={t('ask.mic')}
                  className={`absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-lg border bg-white text-ink-600 hover:text-brand-600 ${voice.recording ? 'animate-pulse border-rose-300 text-rose-600' : 'border-ink-200'}`}
                >
                  {voice.busy ? <Spinner /> : voice.recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                </button>
              </div>
              {voice.error && <div className="rounded-lg bg-amber-50 p-2 text-xs text-amber-700">{voice.error}</div>}

              <div>
                <div className="label mb-1.5">Examples</div>
                <div className="flex flex-wrap gap-1.5">
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex}
                      type="button"
                      onClick={() => setText(ex)}
                      className="rounded-full border border-ink-200 bg-white px-3 py-1 text-xs font-medium text-ink-700 hover:border-brand-300 hover:text-brand-700"
                    >
                      <Sparkles className="mr-1 inline h-3 w-3 text-brand-500" />
                      {ex}
                    </button>
                  ))}
                </div>
              </div>

              <button type="submit" className="btn-primary w-full" disabled={analyze.isPending || !text.trim()}>
                {analyze.isPending ? <><Spinner /> Understanding incident…</> : <><Bot className="h-4 w-4" /> Analyze incident</>}
              </button>
            </form>
            <Disclaimer>COVE2E proposes a classification and next steps. Nothing is filed — a claim is only created when you choose to proceed.</Disclaimer>
          </Card>
        </div>

        <div className="space-y-4 lg:col-span-3">
          {analyze.isError && <ErrorBox message={errorMessage(analyze.error)} />}

          {!c && !analyze.isPending && !analyze.isError && (
            <Card>
              <div className="flex flex-col items-center py-10 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600"><Stethoscope className="h-6 w-6" /></div>
                <p className="mt-3 text-sm font-semibold text-ink-800">Your incident understanding will appear here</p>
                <p className="mt-1 max-w-sm text-xs text-ink-500">Incident type, matching policy, journey, urgency, coverage note, required information and next actions.</p>
              </div>
            </Card>
          )}

          {analyze.isPending && (
            <Card>
              <div className="flex items-center gap-2 py-10 text-sm text-ink-500"><Spinner /> Understanding → matching policy → reasoning…</div>
            </Card>
          )}

          {c && (
            <>
              <Card
                title="Incident understanding"
                subtitle={c.summary}
                action={<Badge tone={urgencyTone(c.urgency)}><AlertTriangle className="h-3 w-3" /> {c.urgency} urgency</Badge>}
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  <Block icon={Stethoscope} label="Incident">
                    <span className="font-semibold">{c.incident_label || titleCase(c.incident_type)}</span>
                    <div className="mt-0.5 text-xs text-ink-500 mono">{c.incident_type}</div>
                  </Block>
                  <Block icon={ShieldCheck} label="Policy">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={c.policy_type === 'UNKNOWN' ? 'gray' : 'blue'}>{c.policy_type}</Badge>
                      {c.matched_policy_label ? (
                        <span className="font-semibold">{c.matched_policy_label}</span>
                      ) : (
                        <Link to="/discovery" className="inline-flex items-center gap-1 text-sm font-semibold text-brand-700 hover:underline">
                          No matching active policy — compare options <ArrowRight className="h-3 w-3" />
                        </Link>
                      )}
                    </div>
                  </Block>
                  <Block icon={RouteIcon} label="Journey">
                    <span className="font-semibold">{titleCase(c.journey)}</span>
                    {c.suggested_claim_type && <div className="mt-0.5 text-xs text-ink-500">Suggested claim type: <span className="font-medium text-ink-700">{titleCase(c.suggested_claim_type)}</span></div>}
                  </Block>
                  <Block icon={AlertTriangle} label="Urgency">
                    <Badge tone={urgencyTone(c.urgency)}>{c.urgency}</Badge>
                  </Block>
                </div>

                <div className="mt-4 rounded-lg border border-brand-100 bg-brand-50/60 p-3">
                  <div className="label text-brand-700">Coverage note</div>
                  <p className="mt-1 text-sm text-ink-800">{c.coverage_note || 'No coverage note available.'}</p>
                </div>

                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <div>
                    <div className="mb-2 flex items-center gap-1.5 label"><FileText className="h-3.5 w-3.5" /> Required information</div>
                    {c.required_information.length ? (
                      <ul className="space-y-1.5">
                        {c.required_information.map((r, i) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-ink-800"><StatusIcon status="PENDING" className="mt-0.5 h-4 w-4 shrink-0" /> {r}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-ink-500">{t('common.none')}</p>
                    )}
                  </div>
                  <div>
                    <div className="mb-2 flex items-center gap-1.5 label"><ListChecks className="h-3.5 w-3.5" /> Next actions</div>
                    {c.next_actions.length ? (
                      <ol className="space-y-1.5">
                        {c.next_actions.map((a, i) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-ink-800">
                            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-600 text-[11px] font-bold text-white">{i + 1}</span>
                            {a}
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="text-sm text-ink-500">{t('common.none')}</p>
                    )}
                  </div>
                </div>

                <div className="mt-5">
                  <div className="flex items-center justify-between text-xs text-ink-500">
                    <span className="label">Classification confidence</span>
                    <span className="font-semibold text-ink-700">{pct(c.confidence * (c.confidence <= 1 ? 100 : 1))}</span>
                  </div>
                  <ProgressBar value={c.confidence <= 1 ? c.confidence * 100 : c.confidence} className="mt-1.5" />
                </div>

                <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-ink-100 pt-4">
                  {startClaimHref ? (
                    <button className="btn-primary" onClick={() => navigate(startClaimHref)}>
                      Start this claim <ArrowRight className="h-4 w-4" />
                    </button>
                  ) : (
                    <Link to="/discovery" className="btn-secondary">Compare insurance options <ArrowRight className="h-4 w-4" /></Link>
                  )}
                  <Link to="/policies" className="btn-ghost">{t('nav.policies')}</Link>
                  <span className="ml-auto text-xs text-ink-500">AI proposes · you decide. The claim is only created when you proceed.</span>
                </div>
              </Card>

              {result && result.policies.length > 0 && (
                <Card title="Policies considered" subtitle="Active policies COVE2E checked while matching this incident.">
                  <ul className="divide-y divide-ink-100">
                    {result.policies.map((p) => (
                      <li key={p.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                        <div className="min-w-0">
                          <div className="truncate font-medium text-ink-900">{p.plan_name}</div>
                          <div className="text-xs text-ink-500">{p.insurer} · <span className="mono">{p.policy_number}</span></div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge tone={p.id === c.matched_policy_id ? 'green' : 'gray'}>{p.id === c.matched_policy_id ? 'Matched' : p.policy_type}</Badge>
                          <Link to={`/policies/${p.id}`} className="text-xs font-semibold text-brand-700 hover:underline">{t('common.open')}</Link>
                        </div>
                      </li>
                    ))}
                  </ul>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
