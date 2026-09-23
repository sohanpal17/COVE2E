import React, { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, ClipboardList, FileSearch, FileText, Radar, Search, ShieldAlert, UserCog } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import { useI18n } from '../i18n'
import { fmtDateTime, stateLabel } from '../utils/format'
import { Badge, Card, ErrorBox, Loading, PageHeader, StatePill } from '../components/ui'

const PRIORITY_TONE: Record<string, string> = { CRITICAL: 'red', HIGH: 'red', MEDIUM: 'amber', LOW: 'gray' }

function Section({ icon, label, children, tone = 'default' }: { icon: React.ReactNode; label: string; children: React.ReactNode; tone?: 'default' | 'danger' | 'action' }) {
  const cls = tone === 'danger' ? 'border-rose-200 bg-rose-50/60' : tone === 'action' ? 'border-brand-200 bg-brand-50/60' : 'border-ink-100 bg-ink-50/60'
  return (
    <div className={`rounded-lg border p-4 ${cls}`}>
      <div className="label flex items-center gap-1.5">{icon} {label}</div>
      <div className="mt-2 text-sm text-ink-900">{children}</div>
    </div>
  )
}

export default function EscalationDetailsPage() {
  const { id = '' } = useParams()
  const { t } = useI18n()
  const [snapOpen, setSnapOpen] = useState(false)
  const { data: esc, isLoading, error } = useQuery({ queryKey: ['escalation', id], queryFn: () => api.escalation(id), enabled: !!id })

  if (isLoading) return <Loading label={t('common.loading')} />
  if (error || !esc) return <ErrorBox message={errorMessage(error)} />

  const snap = esc.external_snapshot ?? {}
  const hasSnap = snap && Object.keys(snap).length > 0
  const history: Record<string, unknown>[] = Array.isArray(snap.history) ? snap.history.slice(-5) : []

  return (
    <div>
      <PageHeader
        crumbs={[{ label: t('nav.escalations'), to: '/escalations' }, { label: esc.reference }]}
        title={t('esc.title')}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span className="mono font-semibold text-ink-800">{esc.reference}</span>
            <Badge tone={PRIORITY_TONE[esc.priority?.toUpperCase()] ?? 'gray'}>{esc.priority} priority</Badge>
            <StatePill state={esc.status} />
            <span className="text-xs">Created {fmtDateTime(esc.created_at)}</span>
          </span>
        }
        actions={
          <>
            {esc.journey_id && (
              <Link to={`/journeys/${esc.journey_id}/investigation`} className="btn-secondary"><Search className="h-4 w-4" /> Open journey</Link>
            )}
            {esc.claim_id && (
              <Link to={`/claims/${esc.claim_id}`} className="btn-secondary"><Radar className="h-4 w-4" /> Open claim</Link>
            )}
          </>
        }
      />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <Card title={<span className="flex items-center gap-2"><ShieldAlert className="h-4 w-4 text-rose-600" /> Escalation packet</span>} subtitle="Everything a human agent needs to act, prepared by COVE2E.">
            <div className="space-y-3">
              <Section icon={<ShieldAlert className="h-3.5 w-3.5" />} label={t('esc.problem')} tone="danger">
                <p className="font-medium">{esc.problem}</p>
              </Section>

              <Section icon={<FileSearch className="h-3.5 w-3.5" />} label={t('esc.evidence')}>
                {esc.evidence.length ? (
                  <ul className="space-y-1.5">
                    {esc.evidence.map((ev, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <FileSearch className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-500" /> <span>{ev}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-ink-500">{t('common.none')}</p>
                )}
              </Section>

              <Section icon={<Radar className="h-3.5 w-3.5" />} label={t('esc.state')}>
                <StatePill state={esc.current_state} />
              </Section>

              <Section icon={<ClipboardList className="h-3.5 w-3.5" />} label={t('esc.attempted')}>
                {esc.actions_attempted.length ? (
                  <ul className="list-disc space-y-1 pl-4">
                    {esc.actions_attempted.map((a, i) => <li key={i}>{a}</li>)}
                  </ul>
                ) : (
                  <p className="text-ink-500">{t('common.none')}</p>
                )}
              </Section>

              <Section icon={<FileText className="h-3.5 w-3.5" />} label={t('esc.reason')}>
                <p>{esc.reason || '—'}</p>
              </Section>

              <Section icon={<UserCog className="h-3.5 w-3.5" />} label={t('esc.recommended')} tone="action">
                <p className="font-medium text-brand-900">{esc.recommended_action || '—'}</p>
              </Section>
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <button className="flex w-full items-center justify-between text-left" onClick={() => setSnapOpen((v) => !v)} disabled={!hasSnap}>
              <span className="text-sm font-semibold text-ink-900">External snapshot</span>
              {hasSnap ? snapOpen ? <ChevronDown className="h-4 w-4 text-ink-400" /> : <ChevronRight className="h-4 w-4 text-ink-400" /> : <span className="text-xs text-ink-400">not captured</span>}
            </button>
            {hasSnap && !snapOpen && <p className="mt-1 text-xs text-ink-500">Insurer state captured at escalation time.</p>}
            {hasSnap && snapOpen && (
              <div className="mt-3 space-y-3">
                <dl className="grid grid-cols-1 gap-2 text-sm">
                  <div className="flex items-center justify-between"><dt className="text-ink-500">Status</dt><dd><StatePill state={snap.status ? String(snap.status) : null} /></dd></div>
                  <div className="flex items-center justify-between"><dt className="text-ink-500">Settlement</dt><dd><StatePill state={snap.settlement_status ? String(snap.settlement_status) : null} /></dd></div>
                  <div className="flex items-center justify-between"><dt className="text-ink-500">Payment</dt><dd><StatePill state={snap.payment_status ? String(snap.payment_status) : null} /></dd></div>
                </dl>
                {history.length > 0 && (
                  <div>
                    <div className="label">Last {history.length} insurer events</div>
                    <ul className="mono mt-1 space-y-1 text-[11px] text-ink-700">
                      {history.map((h, i) => (
                        <li key={i} className="rounded bg-ink-50 px-2 py-1">
                          <span className="text-ink-400">{h.at ? fmtDateTime(String(h.at)) : '—'}</span> · <span className="font-semibold">{stateLabel(String(h.event ?? ''))}</span>
                          {h.detail ? <span className="text-ink-500"> — {String(h.detail)}</span> : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </Card>

          <Card title="Links">
            <div className="flex flex-col gap-2">
              {esc.journey_id ? (
                <Link to={`/journeys/${esc.journey_id}/investigation`} className="btn-secondary justify-start"><Search className="h-4 w-4" /> Open journey</Link>
              ) : (
                <p className="text-xs text-ink-500">No journey linked.</p>
              )}
              {esc.claim_id ? (
                <Link to={`/claims/${esc.claim_id}`} className="btn-secondary justify-start"><Radar className="h-4 w-4" /> Open claim</Link>
              ) : (
                <p className="text-xs text-ink-500">No claim linked.</p>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
