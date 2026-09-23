import React from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, Radar, Search, Wrench } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import { useI18n } from '../i18n'
import { relDays, stateLabel } from '../utils/format'
import { Badge, Card, EmptyState, ErrorBox, Loading, PageHeader, ProgressBar, StatePill, toneForState } from '../components/ui'
import type { JourneyOut } from '../types/api'

const HEALTH_LABEL: Record<JourneyOut['health'], string> = {
  HEALTHY: 'Healthy',
  ATTENTION: 'Needs attention',
  BLOCKED: 'Blocked',
  ESCALATED: 'Escalated',
  COMPLETE: 'Complete',
}

function progressTone(health: JourneyOut['health']): 'brand' | 'green' | 'amber' | 'red' {
  switch (health) {
    case 'HEALTHY':
    case 'COMPLETE':
      return 'green'
    case 'ATTENTION':
    case 'BLOCKED':
      return 'amber'
    case 'ESCALATED':
      return 'red'
    default:
      return 'brand'
  }
}

function JourneyCard({ j }: { j: JourneyOut }) {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-base font-semibold text-ink-900">{j.title}</h3>
            <StatePill state={j.current_state} />
            <Badge tone={toneForState(j.health)}>{HEALTH_LABEL[j.health] ?? j.health}</Badge>
          </div>
          <p className="mt-1 text-xs text-ink-500">
            {stateLabel(j.journey_type)} · updated {relDays(j.updated_at) || 'today'}
          </p>
        </div>
        <div className="text-right text-xs text-ink-500">
          <div className="label">External status</div>
          <div className="mt-0.5">{j.external_status ? <StatePill state={j.external_status} /> : <span className="text-ink-400">Not submitted</span>}</div>
        </div>
      </div>

      <div className="mt-4">
        <div className="mb-1 flex items-center justify-between text-xs text-ink-500">
          <span>Journey progress</span>
          <span className="font-semibold text-ink-700">{Math.round(j.progress_percent)}%</span>
        </div>
        <ProgressBar value={j.progress_percent} tone={progressTone(j.health)} />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <div className="label">Outstanding requirements</div>
          {j.outstanding_requirements.length ? (
            <div className="mt-1 flex flex-wrap gap-1.5">
              {j.outstanding_requirements.map((r) => (
                <Badge key={r} tone="amber">{r}</Badge>
              ))}
            </div>
          ) : (
            <p className="mt-1 text-sm text-ink-500">None</p>
          )}
        </div>
        <div>
          <div className="label">Recovery attempts</div>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-ink-800">
            <Activity className="h-3.5 w-3.5 text-ink-400" /> {j.recovery_attempt_count}
          </p>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2 border-t border-ink-100 pt-4">
        <Link to={`/journeys/${j.id}/investigation`} className="btn-primary">
          <Search className="h-4 w-4" /> Investigate
        </Link>
        <Link to={`/journeys/${j.id}/recovery`} className="btn-secondary">
          <Wrench className="h-4 w-4" /> Recovery
        </Link>
        {j.claim_id && (
          <Link to={`/claims/${j.claim_id}/tracking`} className="btn-ghost">
            <Radar className="h-4 w-4" /> Track claim <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        )}
      </div>
    </Card>
  )
}

export default function JourneysPage() {
  const { t } = useI18n()
  const { data, isLoading, error } = useQuery({ queryKey: ['journeys'], queryFn: api.journeys })

  if (isLoading) return <Loading label={t('common.loading')} />
  if (error || !data) return <ErrorBox message={errorMessage(error)} />

  const blocked = data.filter((j) => j.health === 'BLOCKED' || j.health === 'ESCALATED').length

  return (
    <div>
      <PageHeader
        title={t('nav.journeys')}
        subtitle={data.length ? `${data.length} journey${data.length === 1 ? '' : 's'} · ${blocked} need${blocked === 1 ? 's' : ''} attention` : 'Every policy, claim and recovery you have in flight.'}
      />
      {data.length === 0 ? (
        <EmptyState
          title="No journeys yet"
          hint="Load the Recovery Demo from the dashboard to see a stuck health claim investigated and recovered end-to-end."
          action={
            <Link to="/dashboard" className="btn-primary">
              {t('login.loadDemo')} <ArrowRight className="h-4 w-4" />
            </Link>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {data.map((j) => (
            <JourneyCard key={j.id} j={j} />
          ))}
        </div>
      )}
    </div>
  )
}
