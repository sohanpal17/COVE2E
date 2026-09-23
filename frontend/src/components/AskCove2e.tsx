import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Bot, Mic, Send, Sparkles, Square, Volume2 } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import type { ChatResponse } from '../types/api'
import { useI18n } from '../i18n'
import { useVoice, speak } from '../hooks/useVoice'
import { Badge, Spinner } from './ui'

interface Msg { role: 'user' | 'assistant'; text: string; response?: ChatResponse }

interface Props {
  greeting?: string
  suggestions?: { label: string; message?: string; link?: string }[]
  context?: { journey_id?: string | null; claim_id?: string | null; policy_id?: string | null }
  compact?: boolean
  onResponse?: (r: ChatResponse) => void
}

const DEFAULT_SUGGESTIONS = [
  { label: 'Understand my policy', message: 'Is ICU covered under my health policy?' },
  { label: 'Start a claim', message: 'My father was hospitalized yesterday.' },
  { label: 'Check claim readiness', message: 'Is my claim ready to submit?' },
  { label: 'Find missing documents', message: 'Which documents are missing for my claim?' },
  { label: 'Track my claim', message: 'Where is my claim right now?' },
  { label: 'Recover my stuck claim', message: 'My claim has been stuck for eight days.' },
  { label: 'Compare insurance', message: 'Help me compare health insurance options.' },
]

export default function AskCove2e({ greeting, suggestions = DEFAULT_SUGGESTIONS, context, compact, onResponse }: Props) {
  const { lang, t } = useI18n()
  const navigate = useNavigate()
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const voice = useVoice(lang)
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs, busy])

  const send = async (text: string) => {
    const message = text.trim()
    if (!message || busy) return
    setErr(null)
    setInput('')
    setMsgs((m) => [...m, { role: 'user', text: message }])
    setBusy(true)
    try {
      const res = await api.chat({ message, language: lang, ...context })
      setMsgs((m) => [...m, { role: 'assistant', text: res.reply, response: res }])
      onResponse?.(res)
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const toggleMic = async () => {
    if (voice.recording) {
      const text = await voice.stop()
      if (text) setInput(text)
    } else {
      await voice.start()
    }
  }

  return (
    <div className={`flex flex-col ${compact ? 'h-[420px]' : 'h-[560px]'}`}>
      <div className="scrollbar-thin flex-1 space-y-3 overflow-y-auto pr-1">
        {greeting && msgs.length === 0 && (
          <div className="flex gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white"><Bot className="h-4 w-4" /></div>
            <div className="max-w-[85%] whitespace-pre-line rounded-2xl rounded-tl-sm bg-ink-100 px-4 py-3 text-sm text-ink-900">{greeting}</div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : ''}`}>
            {m.role === 'assistant' && <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white"><Bot className="h-4 w-4" /></div>}
            <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${m.role === 'user' ? 'rounded-tr-sm bg-brand-600 text-white' : 'rounded-tl-sm bg-ink-100 text-ink-900'}`}>
              <div className="whitespace-pre-line">{m.text}</div>
              {m.response && (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Badge tone="gray">{m.response.intent.replace(/_/g, ' ')}</Badge>
                  <Badge tone={m.response.source === 'AI' ? 'purple' : 'blue'}>{m.response.source === 'AI' ? 'Sarvam AI' : 'Deterministic'}</Badge>
                  <button className="text-ink-500 hover:text-brand-600" title="Speak" onClick={() => speak(m.text, lang)}><Volume2 className="h-3.5 w-3.5" /></button>
                  {m.response.navigate_to && (
                    <button className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:underline" onClick={() => navigate(m.response!.navigate_to!)}>
                      {t('common.open')} <ArrowRight className="h-3 w-3" />
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white"><Bot className="h-4 w-4" /></div>
            <div className="flex items-center gap-2 rounded-2xl rounded-tl-sm bg-ink-100 px-4 py-3 text-sm text-ink-600"><Spinner /> Understanding → investigating → reasoning…</div>
          </div>
        )}
        {err && <div className="rounded-lg bg-rose-50 p-2 text-xs text-rose-700">{err}</div>}
        {voice.error && <div className="rounded-lg bg-amber-50 p-2 text-xs text-amber-700">{voice.error}</div>}
        <div ref={bottom} />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {suggestions.map((s) => (
          <button key={s.label} className="rounded-full border border-ink-200 bg-white px-3 py-1 text-xs font-medium text-ink-700 hover:border-brand-300 hover:text-brand-700" onClick={() => (s.message ? send(s.message) : s.link && navigate(s.link))}>
            <Sparkles className="mr-1 inline h-3 w-3 text-brand-500" />
            {s.label}
          </button>
        ))}
      </div>

      <form
        className="mt-3 flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          send(input)
        }}
      >
        <button type="button" onClick={toggleMic} disabled={!voice.supported || voice.busy} title={t('ask.mic')} className={`btn-secondary !px-3 ${voice.recording ? 'animate-pulseSoft border-rose-300 text-rose-600' : ''}`}>
          {voice.busy ? <Spinner /> : voice.recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
        </button>
        <input className="input" value={input} onChange={(e) => setInput(e.target.value)} placeholder={voice.recording ? t('ask.listening') : t('ask.placeholder')} />
        <button type="submit" className="btn-primary !px-3" disabled={busy || !input.trim()}>
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  )
}
