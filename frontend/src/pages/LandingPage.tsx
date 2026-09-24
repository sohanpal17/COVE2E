import React from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Brain, CheckCircle2, ClipboardCheck, FileSearch, Search, ShieldCheck, Stethoscope, Workflow } from 'lucide-react'
import { useI18n } from '../i18n'
import { useAuth } from '../store/auth'
import { LanguageSelector } from '../layouts/AppLayout'
import { Badge } from '../components/ui'

const LOOP = ['UNDERSTAND', 'INVESTIGATE', 'REASON', 'POLICY / ACTION GATE', 'EXECUTE', 'VERIFY', 'UPDATE JOURNEY', 'RESOLVE / ESCALATE']

const CAPABILITIES = [
  { icon: Brain, title: 'Policy Intelligence', body: 'Policy PDFs become a structured profile and a Cognee knowledge layer, so every answer cites a section.' },
  { icon: Stethoscope, title: 'Incident Understanding', body: 'Describe what happened in English, Hindi or Marathi; COVE2E maps it to the right policy, claim type and urgency.' },
  { icon: ClipboardCheck, title: 'Claim Readiness', body: 'Documents are classified, validated and cross-checked before submission, with a readiness score and next action.' },
  { icon: FileSearch, title: 'Journey Investigation', body: 'When a claim stalls, evidence is gathered across insurer status, timeline and requirements to name the blocker.' },
  { icon: Workflow, title: 'Controlled Recovery', body: 'Every fix passes an Action Gate (safe / confirm / escalate / deny) before n8n executes it against the insurer.' },
  { icon: CheckCircle2, title: 'Outcome Verification', body: 'After execution the external state is re-read and compared, so the journey only moves when reality did.' },
]

export default function LandingPage() {
  const { t } = useI18n()
  const { user } = useAuth()
  const primaryTo = user ? '/dashboard' : '/login'

  return (
    <div className="min-h-screen bg-gradient-to-b from-white via-ink-50 to-ink-50">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl shadow-sm" style={{ backgroundColor: '#4ccfe0', color: '#002e6e' }}><ShieldCheck className="h-5 w-5 stroke-[2.5]" /></div>
          <div>
            <div className="text-base font-bold leading-none text-ink-950">COVE2E</div>
            <div className="text-[11px] text-ink-500">{t('app.tagline')}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <LanguageSelector />
          <Link to={primaryTo} className="btn-primary !py-1.5">{user ? 'Dashboard' : 'Open COVE2E'}</Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 pb-16">
        <section className="animate-fadeUp grid items-center gap-10 py-10 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <Badge tone="blue" className="mb-4">Paytm Build for AI · Insurance Journey Intelligence</Badge>
            <h1 className="text-4xl font-bold leading-tight text-ink-950 sm:text-5xl">
              COVE2E <span className="text-ink-400">·</span> <span style={{ color: '#0993a6' }} className="font-extrabold">{t('app.tagline')}</span>
            </h1>
            <p className="mt-4 max-w-xl text-lg text-ink-700">{t('app.promise')}</p>
            <p className="mt-3 max-w-xl text-sm text-ink-500">
              Conversation is only the interface. Underneath is an Insurance Journey Intelligence and Recovery System that understands your policy,
              investigates stuck claims, reasons about blockers, executes controlled fixes and verifies the outcome.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to={primaryTo} className="btn-primary">Open COVE2E <ArrowRight className="h-4 w-4" /></Link>
              <Link to="/login" className="btn-secondary">Demo login</Link>
            </div>
          </div>
          <div className="lg:col-span-2">
            <div className="card p-5 shadow-lift">
              <div className="label">Operating loop</div>
              <ol className="mt-3 space-y-2">
                {LOOP.map((step, i) => (
                  <li key={step} className="flex items-center gap-3 text-sm">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-cyan-950" style={{ backgroundColor: i === 3 ? '#fbbf24' : '#4ccfe0', color: i === 3 ? '#ffffff' : '#07333d' }}>{i + 1}</span>
                    <span className="font-medium text-ink-900">{step}</span>
                    {i === 3 && <Badge tone="amber">permission</Badge>}
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </section>

        <section className="card overflow-x-auto p-4">
          <div className="flex min-w-max items-center gap-2">
            {LOOP.map((step, i) => (
              <React.Fragment key={step}>
                <div className={`rounded-lg px-3 py-2 text-xs font-semibold ${i === 3 ? 'bg-amber-50 text-amber-700 ring-1 ring-amber-200' : 'bg-brand-50 text-brand-800 ring-1 ring-brand-200'}`}>{step}</div>
                {i < LOOP.length - 1 && <ArrowRight className="h-4 w-4 shrink-0 text-ink-300" />}
              </React.Fragment>
            ))}
          </div>
        </section>

        <section className="mt-10">
          <div className="mb-4 flex items-center gap-2">
            <Search className="h-4 w-4 text-brand-800" />
            <h2 className="text-lg font-bold text-ink-950">Key capabilities</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {CAPABILITIES.map((c) => (
              <div key={c.title} className="card card-pad transition hover:shadow-lift">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-800"><c.icon className="h-5 w-5" /></div>
                <h3 className="mt-3 text-sm font-semibold text-ink-900">{c.title}</h3>
                <p className="mt-1 text-xs leading-relaxed text-ink-500">{c.body}</p>
              </div>
            ))}
          </div>
        </section>
      </main>

      <footer className="border-t border-ink-200 bg-white py-4 text-center text-xs text-ink-500">Sarvam AI · Cognee · n8n · FastAPI · PostgreSQL</footer>
    </div>
  )
}
