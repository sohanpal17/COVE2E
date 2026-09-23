import React, { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, Check, Database, ShieldCheck, UserCircle2 } from 'lucide-react'
import { useAuth } from '../store/auth'
import { useI18n } from '../i18n'
import { api, errorMessage } from '../services/api'
import { LanguageSelector } from '../layouts/AppLayout'
import { Badge, ErrorBox, Spinner } from '../components/ui'
import type { Language } from '../types/api'

const ACCOUNTS: { code: string; name: string; lang: Language; langLabel: string; hint: string }[] = [
  { code: 'demo', name: 'Rohan Mehta', lang: 'en', langLabel: 'English', hint: 'Health policy · stuck hospitalization claim' },
  { code: 'demo-hi', name: 'Rohan Mehta', lang: 'hi', langLabel: 'हिन्दी · Hindi', hint: 'Same journey, Hindi interface' },
  { code: 'demo-mr', name: 'Rohan Mehta', lang: 'mr', langLabel: 'मराठी · Marathi', hint: 'Same journey, Marathi interface' },
]

export default function LoginPage() {
  const { login } = useAuth()
  const { t, setLang } = useI18n()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from
  const [code, setCode] = useState('demo')
  const [loadDemo, setLoadDemo] = useState(true)
  const [phase, setPhase] = useState<'idle' | 'login' | 'seeding'>('idle')
  const [err, setErr] = useState<string | null>(null)

  const account = ACCOUNTS.find((a) => a.code === code)!

  const choose = (a: (typeof ACCOUNTS)[number]) => {
    setCode(a.code)
    setLang(a.lang)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr(null)
    setPhase('login')
    try {
      await login(account.code, account.lang)
      setLang(account.lang)
      if (loadDemo) {
        setPhase('seeding')
        await api.loadDemo()
        navigate('/dashboard', { replace: true })
      } else {
        navigate(from && from !== '/login' ? from : '/dashboard', { replace: true })
      }
    } catch (e2) {
      setErr(errorMessage(e2))
      setPhase('idle')
    }
  }

  const busy = phase !== 'idle'

  return (
    <div className="flex min-h-screen flex-col bg-ink-50">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-5">
        <Link to="/" className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 text-white"><ShieldCheck className="h-5 w-5" /></div>
          <div>
            <div className="text-base font-bold leading-none text-ink-950">COVE2E</div>
            <div className="text-[11px] text-ink-500">{t('app.tagline')}</div>
          </div>
        </Link>
        <LanguageSelector />
      </header>

      <main className="flex flex-1 items-center justify-center px-6 pb-16">
        <form onSubmit={submit} className="card w-full max-w-lg animate-fadeUp p-6 shadow-lift">
          <h1 className="text-xl font-bold text-ink-950">{t('login.title')}</h1>
          <p className="mt-1 text-sm text-ink-500">Choose a demo account. Each account sets the interface language and talks to the same FastAPI backend.</p>

          <div className="mt-5 space-y-2">
            {ACCOUNTS.map((a) => {
              const active = a.code === code
              return (
                <button
                  type="button"
                  key={a.code}
                  disabled={busy}
                  onClick={() => choose(a)}
                  className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left transition ${active ? 'border-brand-400 bg-brand-50 ring-2 ring-brand-100' : 'border-ink-200 bg-white hover:border-brand-200'}`}
                >
                  <UserCircle2 className={`h-8 w-8 ${active ? 'text-brand-600' : 'text-ink-300'}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-sm font-semibold text-ink-900">
                      {a.name}
                      <span className="mono text-ink-400">{a.code}</span>
                    </div>
                    <div className="text-xs text-ink-500">{a.hint}</div>
                  </div>
                  <Badge tone={active ? 'blue' : 'gray'}>{a.langLabel}</Badge>
                  {active && <Check className="h-4 w-4 text-brand-600" />}
                </button>
              )
            })}
          </div>

          <label className="mt-4 flex items-start gap-2 rounded-lg bg-ink-50 p-3 text-sm text-ink-700">
            <input type="checkbox" className="mt-0.5" checked={loadDemo} disabled={busy} onChange={(e) => setLoadDemo(e.target.checked)} />
            <span>
              <span className="flex items-center gap-1.5 font-medium text-ink-900"><Database className="h-3.5 w-3.5 text-brand-600" /> Load Recovery Demo data after login</span>
              <span className="text-xs text-ink-500">Seeds a health policy, a claim stuck in DOCUMENT_PENDING for 8 days, documents, timeline and an open insurer query.</span>
            </span>
          </label>

          {err && <div className="mt-4"><ErrorBox message={err} /></div>}

          <button type="submit" className="btn-primary mt-5 w-full" disabled={busy}>
            {busy ? <Spinner /> : <ArrowRight className="h-4 w-4" />}
            {phase === 'seeding' ? 'Loading demo…' : phase === 'login' ? 'Signing in…' : t('login.demo')}
          </button>
          {phase === 'seeding' && (
            <p className="mt-3 flex items-center gap-2 text-xs text-ink-500">
              <Spinner className="h-3.5 w-3.5" /> Populating demo user, policy, claim, documents, timeline, insurer query and stuck state…
            </p>
          )}
        </form>
      </main>
    </div>
  )
}
