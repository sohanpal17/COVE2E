import React, { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, FileText, FileUp, Lightbulb, MessageSquare, ShieldCheck } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import { useI18n } from '../i18n'
import { fmtDate, inr, sleep } from '../utils/format'
import { Badge, Card, EmptyState, ErrorBox, Loading, PageHeader, Spinner, StatePill } from '../components/ui'

const PIPELINE = ['Upload', 'Extract text', 'Structured policy profile', 'Knowledge layer ingestion (Cognee / local)', 'Ready for Policy Companion']

export default function PoliciesPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({ queryKey: ['policies'], queryFn: api.policies })
  const fileInput = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [step, setStep] = useState(-1) // index of the step currently running; PIPELINE.length = all done
  const [fileName, setFileName] = useState<string | null>(null)

  const upload = useMutation({
    mutationFn: async (file: File) => {
      setFileName(file.name)
      setStep(0)
      let cancelled = false
      const animate = async () => {
        for (let i = 1; i < PIPELINE.length - 1 && !cancelled; i++) {
          await sleep(500)
          if (!cancelled) setStep(i)
        }
      }
      const anim = animate()
      try {
        const res = await api.uploadPolicy(file)
        cancelled = true
        await anim
        setStep(PIPELINE.length)
        return res
      } catch (e) {
        cancelled = true
        await anim
        throw e
      }
    },
    onSuccess: async (policy) => {
      await qc.invalidateQueries({ queryKey: ['policies'] })
      await sleep(400)
      navigate(`/policies/${policy.id}`)
    },
    onError: () => setStep(-1),
  })

  const [fileErr, setFileErr] = useState<string | null>(null)
  const onFile = (f: File | undefined | null) => {
    if (!f) return
    if (!/\.(pdf|txt)$/i.test(f.name)) {
      setFileErr(`"${f.name}" is not supported. Please upload a .pdf or .txt policy document.`)
      return
    }
    setFileErr(null)
    upload.mutate(f)
  }

  return (
    <div>
      <PageHeader title={t('nav.policies')} subtitle="Every policy becomes a structured coverage profile plus a knowledge layer the Policy Companion can cite." />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {isLoading && <Loading label={t('common.loading')} />}
          {error && <ErrorBox message={errorMessage(error)} />}
          {data && data.length === 0 && <EmptyState title="No policies yet" hint="Upload a policy PDF or text file to get started." />}
          {data?.map((p) => (
            <div key={p.id} className="card card-pad">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-700"><ShieldCheck className="h-5 w-5" /></div>
                  <div>
                    <div className="text-xs text-ink-500">{p.insurer}</div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-base font-semibold text-ink-900">{p.plan_name}</span>
                      <Badge tone="blue">{p.policy_type}</Badge>
                      <StatePill state={p.status} />
                    </div>
                    <div className="mono mt-0.5 text-ink-500">{p.policy_number}</div>
                  </div>
                </div>
                <Badge tone={p.knowledge_backend === 'cognee' ? 'purple' : 'gray'}>{p.knowledge_backend === 'cognee' ? 'Cognee knowledge graph' : 'Local knowledge index'}</Badge>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div><div className="label">Sum insured</div><div className="text-sm font-semibold text-ink-900">{inr(p.sum_insured)}</div></div>
                <div><div className="label">Expiry</div><div className="text-sm font-semibold text-ink-900">{fmtDate(p.end_date)}</div>{p.days_to_expiry != null && <div className="text-xs text-ink-500">{p.days_to_expiry} days left</div>}</div>
                <div><div className="label">Deductible</div><div className="text-sm font-semibold text-ink-900">{inr(p.deductible)}</div></div>
                <div><div className="label">Waiting period</div><div className="text-sm font-semibold text-ink-900">{p.waiting_period_days} days</div></div>
              </div>
              <div className="mt-4 flex gap-2">
                <Link to={`/policies/${p.id}`} className="btn-secondary"><FileText className="h-4 w-4" /> Details</Link>
                <Link to={`/policies/${p.id}/companion`} className="btn-primary"><MessageSquare className="h-4 w-4" /> Ask</Link>
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-4">
          <Card title={t('policy.upload')} subtitle="PDF or TXT · text is extracted locally, then indexed">
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); onFile(e.dataTransfer.files?.[0]) }}
              onClick={() => !upload.isPending && fileInput.current?.click()}
              className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-8 text-center transition ${dragging ? 'border-brand-400 bg-brand-50' : 'border-ink-200 bg-ink-50 hover:border-brand-300'} ${upload.isPending ? 'pointer-events-none opacity-60' : ''}`}
            >
              <FileUp className="h-6 w-6 text-brand-600" />
              <p className="mt-2 text-sm font-medium text-ink-800">Drop your policy here</p>
              <p className="text-xs text-ink-500">or click to browse · .pdf, .txt</p>
              <input ref={fileInput} type="file" accept=".pdf,.txt,application/pdf,text/plain" className="hidden" onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = '' }} />
            </div>

            {(upload.isPending || step >= 0) && (
              <div className="mt-4">
                {fileName && <div className="mono mb-2 truncate text-ink-600">{fileName}</div>}
                <ol className="space-y-2">
                  {PIPELINE.map((label, i) => {
                    const done = step > i
                    const running = step === i
                    return (
                      <li key={label} className="flex items-center gap-2 text-sm">
                        <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${done ? 'bg-emerald-500 text-white' : running ? 'bg-brand-600 text-white' : 'bg-ink-100 text-ink-500'}`}>
                          {done ? <Check className="h-3 w-3" /> : running ? <Spinner className="h-3 w-3" /> : i + 1}
                        </span>
                        <span className={done ? 'text-ink-700' : running ? 'font-medium text-ink-900' : 'text-ink-400'}>{label}</span>
                      </li>
                    )
                  })}
                </ol>
              </div>
            )}
            {upload.error && <div className="mt-3"><ErrorBox message={errorMessage(upload.error)} /></div>}
            {fileErr && <div className="mt-3"><ErrorBox message={fileErr} /></div>}
            <p className="mt-3 flex items-start gap-1.5 text-xs text-ink-500">
              <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
              Tip: try <span className="mono">mock-data/policies/health_b.txt</span> from the repository.
            </p>
          </Card>
        </div>
      </div>
    </div>
  )
}
