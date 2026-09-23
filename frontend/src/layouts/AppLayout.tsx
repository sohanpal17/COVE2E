import React from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bell, Compass, FileText, Globe, LayoutDashboard, LogOut, Route, ShieldAlert, ShieldCheck, Siren, Stethoscope } from 'lucide-react'
import { useAuth } from '../store/auth'
import { LANGUAGES, useI18n } from '../i18n'
import { api } from '../services/api'
import type { Language } from '../types/api'

const NAV = [
  { to: '/dashboard', key: 'nav.dashboard', icon: LayoutDashboard },
  { to: '/policies', key: 'nav.policies', icon: ShieldCheck },
  { to: '/incidents', key: 'nav.incidents', icon: Stethoscope },
  { to: '/claims', key: 'nav.claims', icon: FileText },
  { to: '/journeys', key: 'nav.journeys', icon: Route },
  { to: '/discovery', key: 'nav.discovery', icon: Compass },
  { to: '/escalations', key: 'nav.escalations', icon: Siren },
  { to: '/notifications', key: 'nav.notifications', icon: Bell },
]

export function LanguageSelector({ className = '' }: { className?: string }) {
  const { lang, setLang } = useI18n()
  return (
    <label className={`inline-flex items-center gap-1.5 rounded-lg border border-ink-200 bg-white px-2 py-1 text-xs text-ink-700 ${className}`}>
      <Globe className="h-3.5 w-3.5 text-ink-500" />
      <select className="bg-transparent text-xs font-medium focus:outline-none" value={lang} onChange={(e) => setLang(e.target.value as Language)}>
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>{l.native}</option>
        ))}
      </select>
    </label>
  )
}

export default function AppLayout() {
  const { user, logout } = useAuth()
  const { t } = useI18n()
  const navigate = useNavigate()
  const { data: notifications } = useQuery({ queryKey: ['notifications'], queryFn: api.notifications, refetchInterval: 15_000 })
  const { data: integrations } = useQuery({ queryKey: ['integrations'], queryFn: api.integrations, staleTime: 60_000 })
  const unread = notifications?.filter((n) => !n.read).length ?? 0

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-ink-200 bg-white lg:flex">
        <div className="flex items-center gap-2 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 text-white"><ShieldCheck className="h-5 w-5" /></div>
          <div>
            <div className="text-base font-bold leading-none text-ink-950">COVE2E</div>
            <div className="text-[11px] text-ink-500">{t('app.tagline')}</div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-600 hover:bg-ink-50 hover:text-ink-900'}`}>
              <n.icon className="h-4 w-4" />
              <span className="flex-1">{t(n.key)}</span>
              {n.to === '/notifications' && unread > 0 && <span className="rounded-full bg-rose-500 px-1.5 text-[10px] font-bold text-white">{unread}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-ink-200 p-3">
          <div className="mb-2 space-y-1 px-2 text-[11px] text-ink-500">
            <IntegrationDot label="Sarvam AI" ok={!!integrations?.sarvam?.configured} hint={integrations?.sarvam?.configured ? 'connected' : 'fallback'} />
            <IntegrationDot label="Cognee" ok={!!integrations?.cognee?.available} hint={integrations?.cognee?.available ? 'graph' : 'local'} />
            <IntegrationDot label="n8n" ok={!!integrations?.n8n?.reachable} hint={integrations?.n8n?.reachable ? 'reachable' : 'demo fallback'} />
          </div>
          <div className="flex items-center justify-between rounded-lg bg-ink-50 px-3 py-2">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-ink-900">{user?.name}</div>
              <div className="truncate text-[11px] text-ink-500">{user?.email}</div>
            </div>
            <button title={t('nav.logout')} className="text-ink-500 hover:text-rose-600" onClick={() => { logout(); navigate('/') }}><LogOut className="h-4 w-4" /></button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-ink-200 bg-white/80 px-4 py-2.5 backdrop-blur lg:px-8">
          <div className="flex items-center gap-2 lg:hidden">
            <ShieldCheck className="h-5 w-5 text-brand-600" />
            <span className="font-bold">COVE2E</span>
          </div>
          <div className="hidden text-xs text-ink-500 lg:block">Understand → Investigate → Reason → Gate → Execute → Verify → Update</div>
          <div className="flex items-center gap-2">
            {integrations?.demo_mode && <span className="pill bg-amber-50 text-amber-700 ring-1 ring-amber-200"><ShieldAlert className="h-3 w-3" /> Demo mode</span>}
            <LanguageSelector />
            <NavLink to="/notifications" className="relative rounded-lg p-2 text-ink-600 hover:bg-ink-100">
              <Bell className="h-4 w-4" />
              {unread > 0 && <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-rose-500 ring-2 ring-white" />}
            </NavLink>
          </div>
        </header>
        <main className="flex-1 px-4 py-6 lg:px-8">
          <div className="mx-auto max-w-6xl animate-fadeUp">
            <Outlet />
          </div>
        </main>
        <nav className="sticky bottom-0 flex justify-around border-t border-ink-200 bg-white py-1 lg:hidden">
          {NAV.slice(0, 5).map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => `flex flex-col items-center gap-0.5 px-2 py-1 text-[10px] ${isActive ? 'text-brand-700' : 'text-ink-500'}`}>
              <n.icon className="h-4 w-4" />
              {t(n.key).split(' ')[0]}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  )
}

function IntegrationDot({ label, ok, hint }: { label: string; ok: boolean; hint?: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? 'bg-emerald-500' : 'bg-amber-400'}`} />
      <span className="flex-1">{label}</span>
      <span className="text-ink-400">{hint}</span>
    </div>
  )
}
