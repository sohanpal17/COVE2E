import React from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ShieldAlert } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import { useI18n } from '../i18n'
import { fmtDateTime } from '../utils/format'
import { Badge, Card, EmptyState, ErrorBox, Loading, PageHeader, StatePill } from '../components/ui'

const PRIORITY_TONE: Record<string, string> = { CRITICAL: 'red', HIGH: 'red', MEDIUM: 'amber', LOW: 'gray' }

export default function EscalationsPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const { data, isLoading, error } = useQuery({ queryKey: ['escalations'], queryFn: api.escalations })

  if (isLoading) return <Loading label={t('common.loading')} />
  if (error || !data) return <ErrorBox message={errorMessage(error)} />

  const open = data.filter((e) => e.status !== 'RESOLVED' && e.status !== 'CLOSED').length

  return (
    <div>
      <PageHeader title={t('nav.escalations')} subtitle={data.length ? `${data.length} packet${data.length === 1 ? '' : 's'} · ${open} open` : 'Handoffs to human agents, with full context.'} />
      {data.length === 0 ? (
        <EmptyState title="No escalations" hint="COVE2E escalates only when states conflict, authority is missing, or recovery fails." />
      ) : (
        <Card>
          <ul className="-m-5 divide-y divide-ink-100">
            {[...data]
              .sort((a, b) => new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime())
              .map((e) => (
                <li key={e.id}>
                  <button onClick={() => navigate(`/escalations/${e.id}`)} className="flex w-full items-start gap-3 px-5 py-4 text-left transition hover:bg-ink-50">
                    <ShieldAlert className={`mt-0.5 h-4 w-4 shrink-0 ${PRIORITY_TONE[e.priority?.toUpperCase()] === 'red' ? 'text-rose-600' : 'text-amber-500'}`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="mono font-semibold text-ink-900">{e.reference}</span>
                        <Badge tone={PRIORITY_TONE[e.priority?.toUpperCase()] ?? 'gray'}>{e.priority}</Badge>
                        <StatePill state={e.status} />
                      </div>
                      <p className="mt-1 text-sm text-ink-800">{e.problem}</p>
                      <p className="mt-1 text-xs text-ink-400">
                        {fmtDateTime(e.created_at)}
                        {e.current_state && <> · state {e.current_state.replace(/_/g, ' ')}</>}
                      </p>
                    </div>
                    <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-ink-300" />
                  </button>
                </li>
              ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
