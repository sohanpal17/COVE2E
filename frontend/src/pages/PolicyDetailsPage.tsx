import React, { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Brain, FilePlus2, MessageSquare, RefreshCw, Trash2 } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import { useI18n } from '../i18n'
import { fmtDate, inr, titleCase } from '../utils/format'
import { Badge, Card, ErrorBox, KeyValue, Loading, PageHeader, StatePill } from '../components/ui'
import type { PolicyConditionOut, PolicyCoverageOut } from '../types/api'

type Tab = 'coverage' | 'exclusions' | 'limits' | 'process' | 'documents'
const TABS: { key: Tab; label: string }[] = [
  { key: 'coverage', label: 'Coverage' },
  { key: 'exclusions', label: 'Exclusions' },
  { key: 'limits', label: 'Waiting periods & limits' },
  { key: 'process', label: 'Claim process' },
  { key: 'documents', label: 'Required documents' },
]

const COVERED_TONE: Record<PolicyCoverageOut['covered'], string> = { YES: 'green', NO: 'red', CONDITIONAL: 'amber' }

function ConditionList({ items, ordered = false, empty }: { items: PolicyConditionOut[]; ordered?: boolean; empty: string }) {
  if (items.length === 0) return <p className="text-sm text-ink-500">{empty}</p>
  const Tag = ordered ? 'ol' : 'ul'
  return (
    <Tag className={`space-y-3 ${ordered ? 'list-decimal pl-5' : ''}`}>
      {items.map((c) => (
        <li key={c.id} className="text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-ink-900">{c.title}</span>
            {c.value && <Badge tone="gray">{c.value}</Badge>}
            {!ordered && <Badge tone="blue">{titleCase(c.kind)}</Badge>}
            {c.section_ref && <span className="mono text-ink-400">{c.section_ref}</span>}
          </div>
          {c.description && <p className="mt-0.5 text-xs text-ink-600">{c.description}</p>}
        </li>
      ))}
    </Tag>
  )
}

export default function PolicyDetailsPage() {
  const { id = '' } = useParams()
  const { t } = useI18n()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('coverage')
  const { data, isLoading, error, refetch, isRefetching } = useQuery({ queryKey: ['policy', id], queryFn: () => api.policy(id), enabled: !!id })

  const deletePolicy = useMutation({
    mutationFn: (policyId: string) => api.deletePolicy(policyId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['policies'] })
      navigate('/policies')
    },
  })

  if (isLoading) return <Loading label={t('common.loading')} />
  if (error || !data) return <ErrorBox message={errorMessage(error)} />

  const sp = data.structured_profile || {}
  const roomRent = sp.room_rent_limit as number | string | undefined
  const byKind = (...kinds: string[]) => data.conditions.filter((c) => kinds.includes(c.kind))
  const exclusions = byKind('EXCLUSION')
  const limits = byKind('WAITING_PERIOD', 'LIMIT', 'DEDUCTIBLE', 'CONDITION')
  const process = byKind('CLAIM_PROCEDURE')
  const docs = byKind('REQUIRED_DOCUMENT')

  const kv: { k: string; v: React.ReactNode }[] = [
    { k: t('policy.coverage'), v: <span className="text-base font-bold">{inr(data.sum_insured)}</span> },
    { k: t('policy.period'), v: `${fmtDate(data.start_date)} - ${fmtDate(data.end_date)}` },
    { k: t('policy.waiting'), v: `${data.waiting_period_days} days` },
  ]
  if (roomRent != null && roomRent !== '') kv.push({ k: 'Room Rent', v: typeof roomRent === 'number' ? `${inr(roomRent)}/day` : String(roomRent) })
  kv.push(
    { k: t('policy.deductible'), v: inr(data.deductible) },
    { k: t('policy.claimType'), v: data.claim_types.map(titleCase).join(' / ') || '—' },
    { k: 'Premium', v: `${inr(data.premium)}/yr` },
    { k: 'Policy number', v: <span className="mono">{data.policy_number}</span> },
    { k: 'Holder', v: data.holder_name },
    { k: 'Insured members', v: data.insured_members.length ? data.insured_members.join(', ') : '—' },
  )

  return (
    <div>
      <PageHeader
        crumbs={[{ label: t('nav.policies'), to: '/policies' }, { label: data.plan_name }]}
        title={
          <span className="flex flex-wrap items-center gap-2">
            MY {data.policy_type} POLICY <StatePill state={data.status} />
          </span>
        }
        subtitle={`${data.plan_name} · ${data.insurer}`}
        actions={
          <>
            <button className="btn-secondary" onClick={() => navigate(`/policies/${id}/companion`)}><MessageSquare className="h-4 w-4" /> Open {t('policy.companion')}</button>
            <button className="btn-primary" onClick={() => navigate(`/claims/new?policy_id=${id}`)}><FilePlus2 className="h-4 w-4" /> Start a claim on this policy</button>
            {!data.is_demo && (
              <button
                className="btn-secondary text-red-600 hover:bg-red-50 hover:text-red-700 hover:border-red-200"
                onClick={() => {
                  if (window.confirm('Are you sure you want to delete this policy?')) {
                    deletePolicy.mutate(id)
                  }
                }}
                disabled={deletePolicy.isPending}
              >
                <Trash2 className="h-4 w-4" /> Delete Policy
              </button>
            )}
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <KeyValue items={kv} />
          </Card>

          <Card>
            <div className="-mx-5 -mt-5 mb-4 flex overflow-x-auto border-b border-ink-200 bg-ink-50/50 p-2 gap-1.5 px-5">
              {TABS.map((tb) => (
                <button key={tb.key} onClick={() => setTab(tb.key)} className={`whitespace-nowrap rounded-lg px-3.5 py-2 text-xs font-bold transition ${tab === tb.key ? 'bg-[#4ccfe0] text-[#002e6e] shadow-xs' : 'text-ink-600 hover:bg-white hover:text-ink-900'}`}>
                  {tb.label}
                  <span className={`ml-1.5 rounded-full px-1.5 text-[10px] ${tab === tb.key ? 'bg-[#002e6e] text-white' : 'bg-ink-200 text-ink-700'}`}>
                    {tb.key === 'coverage' ? data.coverages.length : tb.key === 'exclusions' ? exclusions.length : tb.key === 'limits' ? limits.length : tb.key === 'process' ? process.length : docs.length}
                  </span>
                </button>
              ))}
            </div>

            {tab === 'coverage' && (
              data.coverages.length === 0 ? (
                <p className="text-sm text-ink-500">No coverage lines extracted.</p>
              ) : (
                <div className="-mx-5 -mb-5 overflow-x-auto">
                  <table className="w-full min-w-[560px] text-sm">
                    <thead>
                      <tr className="border-b border-ink-200 text-left">
                        <th className="label px-5 py-2">Item</th>
                        <th className="label px-3 py-2">Covered</th>
                        <th className="label px-3 py-2">Limit</th>
                        <th className="label px-3 py-2">Condition</th>
                        <th className="label px-5 py-2">Section</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                      {data.coverages.map((c) => (
                        <tr key={c.id}>
                          <td className="px-5 py-2.5 font-medium text-ink-900">{c.name}</td>
                          <td className="px-3 py-2.5"><Badge tone={COVERED_TONE[c.covered]}>{c.covered}</Badge></td>
                          <td className="px-3 py-2.5 text-ink-700">{c.limit_text || (c.limit_amount != null ? inr(c.limit_amount) : '—')}</td>
                          <td className="px-3 py-2.5 text-xs text-ink-600">{c.condition_text || '—'}</td>
                          <td className="mono px-5 py-2.5 text-ink-400">{c.section_ref || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            )}
            {tab === 'exclusions' && <ConditionList items={exclusions} empty="No exclusions extracted." />}
            {tab === 'limits' && <ConditionList items={limits} empty="No waiting periods or limits extracted." />}
            {tab === 'process' && <ConditionList items={process} ordered empty="No claim procedure steps extracted." />}
            {tab === 'documents' && <ConditionList items={docs} empty="No required documents extracted." />}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Knowledge layer" subtitle="Powers the Policy Companion's cited answers">
            <div className="flex items-center gap-2">
              <Brain className="h-5 w-5 text-violet-600" />
              <Badge tone={data.knowledge_indexed ? 'green' : 'amber'}>{data.knowledge_indexed ? 'Indexed' : 'Not indexed'}</Badge>
              <Badge tone={data.knowledge_backend === 'cognee' ? 'purple' : 'gray'}>{data.knowledge_backend === 'cognee' ? 'Cognee knowledge graph' : 'Local knowledge index'}</Badge>
            </div>
            {data.source_file && <div className="mono mt-3 truncate text-ink-500">Source: {data.source_file}</div>}
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="btn-secondary !py-1.5 text-xs" onClick={() => refetch()} disabled={isRefetching}>
                <RefreshCw className={`h-3.5 w-3.5 ${isRefetching ? 'animate-spin' : ''}`} /> Refresh status
              </button>
              <Link to="/policies" className="btn-ghost !py-1.5 text-xs">Re-upload to re-index</Link>
            </div>
          </Card>

          {Object.keys(sp).length > 0 && (
            <Card title="Structured profile" subtitle="Extracted from the policy document">
              <dl className="space-y-2 text-sm">
                {Object.entries(sp)
                  .filter(([, v]) => v != null && typeof v !== 'object')
                  .slice(0, 14)
                  .map(([k, v]) => (
                    <div key={k} className="flex items-start justify-between gap-3">
                      <dt className="text-xs text-ink-500">{titleCase(k)}</dt>
                      <dd className="text-right text-xs font-medium text-ink-900">{typeof v === 'number' && /amount|limit|premium|sum|deductible/i.test(k) ? inr(v) : String(v)}</dd>
                    </div>
                  ))}
              </dl>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
