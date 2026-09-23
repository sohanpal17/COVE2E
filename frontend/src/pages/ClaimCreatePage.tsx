import React, { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, Check, ClipboardList, FileText, ShieldCheck, Stethoscope } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import type { ClaimCreateRequest, PolicySummary } from '../types/api'
import { useI18n } from '../i18n'
import { Badge, Card, CheckList, Disclaimer, ErrorBox, Loading, PageHeader, Stat } from '../components/ui'
import { fmtDate, inr, titleCase } from '../utils/format'

const STAGES = [
  { n: 1, label: 'Incident Capture', icon: Stethoscope },
  { n: 2, label: 'Coverage Understanding', icon: ShieldCheck },
  { n: 3, label: 'Claim Type', icon: ClipboardList },
  { n: 4, label: 'Document Checklist', icon: FileText },
]

const CLAIM_TYPES: Record<string, { value: string; label: string; hint: string }[]> = {
  HEALTH: [
    { value: 'CASHLESS', label: 'Cashless', hint: 'Network hospital settles directly with the insurer.' },
    { value: 'REIMBURSEMENT', label: 'Reimbursement', hint: 'You pay first and claim the amount back.' },
  ],
  MOTOR: [
    { value: 'OWN_DAMAGE', label: 'Own damage', hint: 'Damage to your own vehicle.' },
    { value: 'THIRD_PARTY', label: 'Third party', hint: 'Damage or injury caused to others.' },
  ],
  GADGET: [{ value: 'GADGET', label: 'Gadget', hint: 'Theft, loss or accidental damage to the device.' }],
}

const INCIDENT_TYPES = ['HOSPITALIZATION', 'ACCIDENT', 'VEHICLE_DAMAGE', 'THEFT', 'ILLNESS', 'DEVICE_DAMAGE', 'OTHER']

type CheckStatus = 'DONE' | 'WARNING' | 'MISSING' | 'PENDING'

function dayDiff(a: Date, b: Date) {
  return Math.floor((a.getTime() - b.getTime()) / 86_400_000)
}

function coverageChecks(policy: PolicySummary | undefined, incidentDate: string): { label: string; status: CheckStatus; detail?: string }[] {
  const unknown = (label: string, detail: string) => ({ label, status: 'PENDING' as CheckStatus, detail })
  if (!policy) return [unknown('Incident date is after policy start', 'Select a policy'), unknown('Within policy period', 'Select a policy'), unknown('Waiting period elapsed', 'Select a policy')]
  const inc = incidentDate ? new Date(incidentDate) : null
  const start = policy.start_date ? new Date(policy.start_date) : null
  const end = policy.end_date ? new Date(policy.end_date) : null
  if (!inc || Number.isNaN(inc.getTime())) {
    return [unknown('Incident date is after policy start', 'Enter the incident date'), unknown('Within policy period', 'Enter the incident date'), unknown('Waiting period elapsed', 'Enter the incident date')]
  }
  const out: { label: string; status: CheckStatus; detail?: string }[] = []
  if (!start) out.push(unknown('Incident date is after policy start', 'Policy start date unknown'))
  else out.push({ label: 'Incident date is after policy start', status: inc >= start ? 'DONE' : 'MISSING', detail: `Policy started ${fmtDate(policy.start_date)}` })
  if (!start || !end) out.push(unknown('Within policy period', 'Policy period dates unknown'))
  else out.push({ label: 'Within policy period', status: inc >= start && inc <= end ? 'DONE' : 'MISSING', detail: `${fmtDate(policy.start_date)} → ${fmtDate(policy.end_date)}` })
  if (!start) out.push(unknown(`Waiting period elapsed (${policy.waiting_period_days} days)`, 'Policy start date unknown'))
  else {
    const since = dayDiff(inc, start)
    const ok = since >= (policy.waiting_period_days || 0)
    out.push({
      label: `Waiting period elapsed (${since} days since start, ${policy.waiting_period_days} required)`,
      status: ok ? 'DONE' : 'WARNING',
      detail: ok ? 'Waiting period satisfied for this incident date.' : 'Incident falls inside the waiting period — the insurer may apply exclusions.',
    })
  }
  return out
}

export default function ClaimCreatePage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const [sp] = useSearchParams()

  const policiesQ = useQuery({ queryKey: ['policies'], queryFn: api.policies })
  const policies = policiesQ.data ?? []

  const [policyId, setPolicyId] = useState(sp.get('policy_id') ?? '')
  const [incidentType, setIncidentType] = useState(sp.get('incident_type') ?? '')
  const [claimType, setClaimType] = useState(sp.get('claim_type') ?? '')
  const [description, setDescription] = useState(sp.get('description') ?? '')
  const [incidentDate, setIncidentDate] = useState('')
  const [incidentTime, setIncidentTime] = useState('')
  const [location, setLocation] = useState('')
  const [asset, setAsset] = useState('')
  const [people, setPeople] = useState('')
  const [amount, setAmount] = useState('')

  useEffect(() => {
    if (!policyId && policies.length) setPolicyId(policies[0].id)
  }, [policies, policyId])

  const policy = useMemo(() => policies.find((p) => p.id === policyId), [policies, policyId])
  const typeOptions = useMemo(() => {
    if (!policy) return []
    const fromPolicy = (policy.claim_types || []).map((v) => ({ value: v, label: titleCase(v), hint: '' }))
    const known = CLAIM_TYPES[policy.policy_type] ?? []
    if (!known.length) return fromPolicy
    // keep known labels/hints, but include any extra types the policy lists
    const extras = fromPolicy.filter((f) => !known.some((k) => k.value === f.value))
    return [...known, ...extras]
  }, [policy])

  useEffect(() => {
    if (typeOptions.length && !typeOptions.some((o) => o.value === claimType)) setClaimType(typeOptions[0].value)
  }, [typeOptions, claimType])

  const checks = useMemo(() => coverageChecks(policy, incidentDate), [policy, incidentDate])

  const create = useMutation({
    mutationFn: (req: ClaimCreateRequest) => api.createClaim(req),
    onSuccess: (claim) => navigate(`/claims/${claim.id}/documents`),
  })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!policyId || !claimType) return
    const req: ClaimCreateRequest = {
      policy_id: policyId,
      claim_type: claimType,
      incident_type: incidentType || 'OTHER',
      incident_date: incidentDate ? new Date(`${incidentDate}T${incidentTime || '00:00'}:00`).toISOString() : null,
      incident_time: incidentTime,
      incident_description: description,
      location,
      affected_asset: asset,
      people_involved: people,
      claimed_amount: amount ? Number(amount) : undefined,
    }
    create.mutate(req)
  }

  const activeStage = 3

  return (
    <div>
      <PageHeader
        title="Start a claim"
        subtitle="COVE2E captures the incident, checks your coverage and picks the claim type. Documents come next."
        crumbs={[{ label: t('nav.claims'), to: '/claims' }, { label: 'New claim' }]}
      />

      <ol className="mb-6 grid gap-2 sm:grid-cols-4">
        {STAGES.map((s) => {
          const done = s.n < activeStage
          const current = s.n <= activeStage && !done
          const Icon = s.icon
          return (
            <li key={s.n} className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 ${s.n <= activeStage ? 'border-brand-200 bg-brand-50/60' : 'border-ink-200 bg-white'}`}>
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ${done ? 'bg-emerald-500 text-white' : current ? 'bg-brand-600 text-white' : 'bg-ink-100 text-ink-500'}`}>
                {done ? <Check className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
              </div>
              <div className="min-w-0">
                <div className="label">Stage {s.n}</div>
                <div className="truncate text-sm font-semibold text-ink-900">{s.label}</div>
              </div>
              {s.n === 4 && <Badge tone="gray" className="ml-auto">After creation</Badge>}
            </li>
          )
        })}
      </ol>

      {policiesQ.isLoading && <Loading label={t('common.loading')} />}
      {policiesQ.isError && <ErrorBox message={errorMessage(policiesQ.error)} />}

      {policiesQ.data && policies.length === 0 && (
        <Card>
          <p className="text-sm text-ink-700">You have no policies on file. Upload a policy first so COVE2E can check coverage.</p>
          <Link to="/policies" className="btn-primary mt-3">{t('nav.policies')} <ArrowRight className="h-4 w-4" /></Link>
        </Card>
      )}

      {policies.length > 0 && (
        <form onSubmit={submit} className="grid gap-6 lg:grid-cols-5">
          <div className="space-y-6 lg:col-span-3">
            <Card title="Stage 1 · Incident Capture" subtitle="What happened, when and where.">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <label className="label">Policy</label>
                  <select className="input mt-1" value={policyId} onChange={(e) => setPolicyId(e.target.value)}>
                    {policies.map((p) => (
                      <option key={p.id} value={p.id}>{p.plan_name} · {p.policy_number} ({p.policy_type})</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label">Incident type</label>
                  <select className="input mt-1" value={incidentType} onChange={(e) => setIncidentType(e.target.value)}>
                    <option value="">Select…</option>
                    {(incidentType && !INCIDENT_TYPES.includes(incidentType) ? [incidentType, ...INCIDENT_TYPES] : INCIDENT_TYPES).map((v) => (
                      <option key={v} value={v}>{titleCase(v)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label">Claimed amount (₹)</label>
                  <input className="input mt-1" type="number" min={0} step={1} value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="e.g. 85000" />
                </div>
                <div>
                  <label className="label">Incident date</label>
                  <input className="input mt-1" type="date" value={incidentDate} onChange={(e) => setIncidentDate(e.target.value)} required />
                </div>
                <div>
                  <label className="label">Time</label>
                  <input className="input mt-1" type="time" value={incidentTime} onChange={(e) => setIncidentTime(e.target.value)} />
                </div>
                <div className="sm:col-span-2">
                  <label className="label">Location</label>
                  <input className="input mt-1" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Hospital, city or place of incident" />
                </div>
                <div className="sm:col-span-2">
                  <label className="label">Incident description</label>
                  <textarea className="input mt-1 min-h-[96px]" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Describe what happened" />
                </div>
                <div>
                  <label className="label">Affected asset</label>
                  <input className="input mt-1" value={asset} onChange={(e) => setAsset(e.target.value)} placeholder="e.g. Father (insured member), MH12 AB 1234, iPhone 15" />
                </div>
                <div>
                  <label className="label">People involved</label>
                  <input className="input mt-1" value={people} onChange={(e) => setPeople(e.target.value)} placeholder="Names / relationship" />
                </div>
              </div>
            </Card>

            <Card title="Stage 3 · Claim Type" subtitle="Choose how this claim will be processed.">
              {typeOptions.length === 0 ? (
                <p className="text-sm text-ink-500">No claim types available for the selected policy.</p>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  {typeOptions.map((o) => (
                    <label key={o.value} className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${claimType === o.value ? 'border-brand-400 bg-brand-50/60 ring-1 ring-brand-200' : 'border-ink-200 hover:border-ink-300'}`}>
                      <input type="radio" name="claim_type" className="mt-1" value={o.value} checked={claimType === o.value} onChange={() => setClaimType(o.value)} />
                      <div>
                        <div className="text-sm font-semibold text-ink-900">{o.label}</div>
                        {o.hint && <div className="text-xs text-ink-500">{o.hint}</div>}
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </Card>

            {create.isError && <ErrorBox message={errorMessage(create.error)} />}

            <div className="flex flex-wrap items-center gap-2">
              <button type="submit" className="btn-primary" disabled={create.isPending || !policyId || !claimType || !incidentDate}>
                {create.isPending ? 'Creating claim…' : 'Create claim & continue to documents'} <ArrowRight className="h-4 w-4" />
              </button>
              <Link to="/claims" className="btn-ghost">{t('common.cancel')}</Link>
              <span className="text-xs text-ink-500">Stage 4 (Document Checklist) opens in the Document Center after the claim is created.</span>
            </div>
          </div>

          <div className="space-y-6 lg:col-span-2">
            <Card title="Stage 2 · Coverage Understanding" subtitle={policy ? `${policy.insurer} · ${policy.plan_name}` : 'Select a policy'}>
              {policy ? (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <Stat label="Sum insured" value={inr(policy.sum_insured)} />
                    <Stat label={t('policy.deductible')} value={inr(policy.deductible)} />
                    <Stat label={t('policy.waiting')} value={`${policy.waiting_period_days} days`} />
                    <Stat label={t('policy.period')} value={<span className="text-sm">{fmtDate(policy.start_date)} → {fmtDate(policy.end_date)}</span>} sub={policy.days_to_expiry != null ? `${policy.days_to_expiry} days to expiry` : undefined} />
                  </div>
                  <div className="mt-4">
                    <div className="label mb-1.5">Claim types under this policy</div>
                    <div className="flex flex-wrap gap-1.5">
                      {(policy.claim_types || []).length ? policy.claim_types.map((ct) => <Badge key={ct} tone={ct === claimType ? 'blue' : 'gray'}>{titleCase(ct)}</Badge>) : <span className="text-xs text-ink-500">{t('common.none')}</span>}
                    </div>
                  </div>
                  <div className="mt-4 border-t border-ink-100 pt-4">
                    <div className="label mb-2">Live coverage checks</div>
                    <CheckList items={checks} />
                  </div>
                  <Disclaimer>These checks are computed from policy dates only. They indicate eligibility conditions, not the insurer's decision.</Disclaimer>
                </>
              ) : (
                <p className="text-sm text-ink-500">Select a policy to see coverage details.</p>
              )}
            </Card>
          </div>
        </form>
      )}
    </div>
  )
}
