import React, { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Compass, Search, Sparkles, ThumbsUp, AlertCircle } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import { useI18n } from '../i18n'
import { inr, pct, titleCase } from '../utils/format'
import { Badge, Card, Disclaimer, ErrorBox, Loading, PageHeader, ProgressBar, Spinner } from '../components/ui'
import type { DiscoveryRequest, ProductOut } from '../types/api'

const FAMILY = [
  { value: 'single', label: 'Single' },
  { value: 'married', label: 'Married' },
  { value: 'married_with_children', label: 'Married with children' },
  { value: 'joint_family', label: 'Joint family' },
]
const ASSETS = [
  { value: 'car', label: 'Car' },
  { value: 'two_wheeler', label: 'Two-wheeler' },
  { value: 'home', label: 'Home' },
  { value: 'phone_laptop', label: 'Phone / laptop' },
]
const EXISTING = [
  { value: 'health', label: 'Health' },
  { value: 'motor', label: 'Motor' },
  { value: 'life', label: 'Life' },
  { value: 'none', label: 'None' },
]
const RISKS = [
  { value: 'icu', label: 'ICU' },
  { value: 'family', label: 'Family' },
  { value: 'low_deductible', label: 'Low deductible' },
  { value: 'short_waiting_period', label: 'Short waiting period' },
  { value: 'zero_depreciation', label: 'Zero depreciation' },
  { value: 'roadside_assistance', label: 'Roadside assistance' },
  { value: 'senior_parents', label: 'Senior parents' },
  { value: 'budget', label: 'Budget' },
]

type Form = Omit<DiscoveryRequest, 'language'>

const INITIAL: Form = {
  age: 32,
  family_situation: 'married_with_children',
  occupation: 'Software engineer',
  assets: ['car'],
  existing_coverage: ['none'],
  budget_annual: 20000,
  risk_requirements: ['icu', 'family'],
  insurance_type: 'HEALTH',
}

function Chips({ options, value, onChange }: { options: { value: string; label: string }[]; value: string[]; onChange: (v: string[]) => void }) {
  const toggle = (v: string) => (value.includes(v) ? onChange(value.filter((x) => x !== v)) : onChange([...value, v]))
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = value.includes(o.value)
        return (
          <button type="button" key={o.value} onClick={() => toggle(o.value)} className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${on ? 'border-[#4ccfe0] bg-[#4ccfe0] text-[#002e6e] shadow-xs' : 'border-ink-200 bg-white text-ink-700 hover:border-[#4ccfe0] hover:text-[#002e6e]'}`}>
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

function limitsText(limits: Record<string, any>): string[] {
  return Object.entries(limits || {}).map(([k, v]) => `${titleCase(k)}: ${typeof v === 'number' ? inr(v) : String(v)}`)
}

export default function DiscoveryPage() {
  const { lang } = useI18n()
  const [form, setForm] = useState<Form>(INITIAL)
  const products = useQuery({ queryKey: ['products'], queryFn: api.products })
  const discover = useMutation({ mutationFn: (f: Form) => api.discover({ ...f, language: lang }) })

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }))

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    discover.mutate(form)
  }

  const result = discover.data
  const matches = result?.matches ?? []

  const rows: { label: string; render: (p: ProductOut) => React.ReactNode }[] = [
    { label: 'Coverage / sum insured', render: (p) => <span className="font-semibold text-ink-900">{inr(p.sum_insured)}</span> },
    { label: 'Premium', render: (p) => <>{inr(p.premium_annual)} <span className="text-ink-400">/yr</span></> },
    { label: 'Deductible', render: (p) => inr(p.deductible) },
    { label: 'Waiting period', render: (p) => `${p.waiting_period_days} days` },
    { label: 'Major exclusions', render: (p) => <ul className="list-disc pl-4">{p.exclusions.slice(0, 3).map((x) => <li key={x}>{x}</li>)}</ul> },
    { label: 'Limits', render: (p) => <ul className="space-y-0.5">{limitsText(p.limits).map((x) => <li key={x}>{x}</li>)}</ul> },
    { label: 'Network availability', render: (p) => p.network_info || '—' },
    { label: 'Important conditions', render: (p) => <ul className="list-disc pl-4">{p.conditions.slice(0, 2).map((x) => <li key={x}>{x}</li>)}</ul> },
  ]

  return (
    <div>
      <PageHeader title="Insurance Discovery" subtitle="Compare products side by side based on your situation. COVE2E explains fit; it does not sell." />

      <div className="grid gap-6 lg:grid-cols-3">
        <form onSubmit={submit} className="card card-pad space-y-4 self-start lg:sticky lg:top-20">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Age</label>
              <input type="number" min={18} max={99} className="input mt-1" value={form.age} onChange={(e) => set('age', Number(e.target.value))} />
            </div>
            <div>
              <label className="label">Insurance type</label>
              <select className="input mt-1" value={form.insurance_type} onChange={(e) => set('insurance_type', e.target.value)}>
                <option value="HEALTH">HEALTH</option>
                <option value="MOTOR">MOTOR</option>
              </select>
            </div>
          </div>
          <div>
            <label className="label">Family situation</label>
            <select className="input mt-1" value={form.family_situation} onChange={(e) => set('family_situation', e.target.value)}>
              {FAMILY.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Occupation</label>
            <input className="input mt-1" value={form.occupation} onChange={(e) => set('occupation', e.target.value)} />
          </div>
          <div>
            <label className="label">Assets</label>
            <div className="mt-1"><Chips options={ASSETS} value={form.assets} onChange={(v) => set('assets', v)} /></div>
          </div>
          <div>
            <label className="label">Existing coverage</label>
            <div className="mt-1"><Chips options={EXISTING} value={form.existing_coverage} onChange={(v) => set('existing_coverage', v)} /></div>
          </div>
          <div>
            <label className="label">Annual budget (₹)</label>
            <input type="number" min={0} step={1000} className="input mt-1" value={form.budget_annual} onChange={(e) => set('budget_annual', Number(e.target.value))} />
          </div>
          <div>
            <label className="label">Risk requirements</label>
            <div className="mt-1"><Chips options={RISKS} value={form.risk_requirements} onChange={(v) => set('risk_requirements', v)} /></div>
          </div>
          <button type="submit" className="btn-primary w-full" disabled={discover.isPending}>
            {discover.isPending ? <Spinner /> : <Search className="h-4 w-4" />} Compare products
          </button>
          {discover.error && <ErrorBox message={errorMessage(discover.error)} />}
        </form>

        <div className="space-y-6 lg:col-span-2">
          {discover.isPending && <Loading label="Scoring products against your situation…" />}

          {result && (
            <>
              <div className="rounded-xl border border-brand-200 bg-brand-50 p-4">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-brand-600" />
                  <span className="text-sm font-semibold text-brand-900">Summary</span>
                  <Badge tone={result.narrative_source === 'AI' ? 'purple' : 'blue'}>{result.narrative_source === 'AI' ? 'Sarvam AI' : 'Deterministic'}</Badge>
                </div>
                <p className="mt-2 whitespace-pre-line text-sm text-ink-800">{result.narrative}</p>
              </div>

              {matches.length === 0 ? (
                <Card><p className="text-sm text-ink-500">No products matched these inputs. Try widening the budget or changing the insurance type.</p></Card>
              ) : (
                <>
                  <Card title="Comparison" subtitle={`${matches.length} matching product${matches.length === 1 ? '' : 's'}`}>
                    <div className="-m-5 overflow-x-auto">
                      <table className="w-full min-w-[640px] text-sm">
                        <thead>
                          <tr className="border-b border-ink-200 bg-ink-50 text-left">
                            <th className="label px-4 py-3">Feature</th>
                            {matches.map((m) => (
                              <th key={m.product.id} className="px-4 py-3 align-top">
                                <div className="text-xs font-normal text-ink-500">{m.product.insurer}</div>
                                <div className="font-semibold text-ink-900">{m.product.name}</div>
                                <Badge tone="blue" className="mt-1">{m.product.product_type}</Badge>
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-ink-100">
                          {rows.map((r) => (
                            <tr key={r.label}>
                              <td className="label whitespace-nowrap px-4 py-3 align-top">{r.label}</td>
                              {matches.map((m) => (
                                <td key={m.product.id} className="px-4 py-3 align-top text-xs text-ink-700">{r.render(m.product)}</td>
                              ))}
                            </tr>
                          ))}
                          <tr className="bg-ink-50/60">
                            <td className="label px-4 py-3 align-top">Match score</td>
                            {matches.map((m) => (
                              <td key={m.product.id} className="px-4 py-3 align-top">
                                <div className="flex items-center gap-2">
                                  <ProgressBar value={m.match_score} tone={m.match_score >= 75 ? 'green' : m.match_score >= 50 ? 'brand' : 'amber'} className="flex-1" />
                                  <span className="w-10 text-right text-xs font-semibold text-ink-900">{pct(m.match_score)}</span>
                                </div>
                              </td>
                            ))}
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </Card>

                  <div className="grid gap-4 md:grid-cols-2">
                    {matches.map((m) => (
                      <Card key={m.product.id} title={m.product.name} subtitle={m.product.description}>
                        <div className="space-y-3">
                          <div>
                            <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700"><ThumbsUp className="h-3.5 w-3.5" /> Why this matches</div>
                            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-ink-700">{m.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                            {m.reasons.length === 0 && <p className="text-xs text-ink-400">No specific reasons recorded.</p>}
                          </div>
                          <div>
                            <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-700"><AlertCircle className="h-3.5 w-3.5" /> Keep in mind</div>
                            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-ink-700">{m.cautions.map((c) => <li key={c}>{c}</li>)}</ul>
                            {m.cautions.length === 0 && <p className="text-xs text-ink-400">No cautions recorded.</p>}
                          </div>
                        </div>
                      </Card>
                    ))}
                  </div>
                </>
              )}
              <Disclaimer>{result.disclaimer}</Disclaimer>
            </>
          )}

          {!result && !discover.isPending && (
            <Card title="Catalogue" subtitle="All products COVE2E can compare. Fill in the form to see how each fits your situation.">
              {products.isLoading && <Loading />}
              {products.error && <ErrorBox message={errorMessage(products.error)} />}
              {products.data && (
                <div className="grid gap-3 sm:grid-cols-2">
                  {products.data.map((p) => (
                    <div key={p.id} className="rounded-xl border border-ink-200 p-4">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-xs text-ink-500">{p.insurer}</div>
                          <div className="text-sm font-semibold text-ink-900">{p.name}</div>
                        </div>
                        <Badge tone="blue">{p.product_type}</Badge>
                      </div>
                      <p className="mt-2 line-clamp-2 text-xs text-ink-500">{p.description}</p>
                      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                        <div><div className="label">Sum insured</div><div className="font-semibold text-ink-900">{inr(p.sum_insured)}</div></div>
                        <div><div className="label">Premium</div><div className="font-semibold text-ink-900">{inr(p.premium_annual)}/yr</div></div>
                        <div><div className="label">Deductible</div><div className="text-ink-800">{inr(p.deductible)}</div></div>
                        <div><div className="label">Waiting</div><div className="text-ink-800">{p.waiting_period_days} days</div></div>
                      </div>
                    </div>
                  ))}
                  {products.data.length === 0 && <p className="text-sm text-ink-500">Catalogue is empty.</p>}
                </div>
              )}
              <Disclaimer>Product information is indicative. Terms, exclusions and premiums are set by the insurer.</Disclaimer>
            </Card>
          )}

          {!result && !discover.isPending && (
            <div className="flex items-start gap-2 text-xs text-ink-500">
              <Compass className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              COVE2E ranks products by how closely their coverage, limits and price match the requirements you selected. It never recommends a single winner.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
