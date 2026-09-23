import axios from 'axios'
import type * as T from '../types/api'

export const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

export const http = axios.create({ baseURL: API_BASE, timeout: 60_000 })

const TOKEN_KEY = 'cove2e.token'
export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

http.interceptors.request.use((config) => {
  const token = tokenStore.get()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error?.response?.status === 401) {
      tokenStore.clear()
      if (!location.pathname.startsWith('/login') && location.pathname !== '/') location.assign('/login')
    }
    return Promise.reject(error)
  },
)

export function errorMessage(err: unknown): string {
  const e = err as any
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg).join('; ')
  return e?.message || 'Something went wrong'
}

export const api = {
  // auth
  demoLogin: (demo_code: string, language?: string) => http.post<T.TokenResponse>('/api/auth/demo-login', { demo_code, language }).then((r) => r.data),
  me: () => http.get<T.UserOut>('/api/auth/me').then((r) => r.data),
  setLanguage: (language: string) => http.post<T.UserOut>('/api/auth/language', { language }).then((r) => r.data),

  // dashboard
  dashboard: () => http.get<T.DashboardResponse>('/api/dashboard').then((r) => r.data),
  integrations: () => http.get<T.IntegrationStatus>('/api/integrations').then((r) => r.data),
  audit: (journey_id?: string) => http.get<T.AuditLogOut[]>('/api/audit', { params: { limit: 100, journey_id } }).then((r) => r.data),

  // chat
  chat: (req: T.ChatRequest) => http.post<T.ChatResponse>('/api/chat', req).then((r) => r.data),

  // policies
  policies: () => http.get<T.PolicySummary[]>('/api/policies').then((r) => r.data),
  policy: (id: string) => http.get<T.PolicyDetail>(`/api/policies/${id}`).then((r) => r.data),
  uploadPolicy: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post<T.PolicyDetail>('/api/policies/upload', fd).then((r) => r.data)
  },
  askPolicy: (id: string, question: string, language: string) => http.post<T.PolicyAskResponse>(`/api/policies/${id}/ask`, { question, language }).then((r) => r.data),

  // incidents
  analyzeIncident: (description: string, language: string) => http.post<T.IncidentAnalyzeResponse>('/api/incidents/analyze', { description, language }).then((r) => r.data),

  // claims
  claims: () => http.get<T.ClaimSummary[]>('/api/claims').then((r) => r.data),
  claim: (id: string) => http.get<T.ClaimDetail>(`/api/claims/${id}`).then((r) => r.data),
  createClaim: (req: T.ClaimCreateRequest) => http.post<T.ClaimDetail>('/api/claims', req).then((r) => r.data),
  uploadDocument: (claimId: string, file: File, document_type?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    if (document_type) fd.append('document_type', document_type)
    return http.post<T.DocumentAnalysis>(`/api/claims/${claimId}/documents`, fd).then((r) => r.data)
  },
  uploadSampleDocument: (claimId: string, document_type: string) => {
    const fd = new FormData()
    fd.append('document_type', document_type)
    return http.post<T.DocumentAnalysis>(`/api/claims/${claimId}/documents/sample`, fd).then((r) => r.data)
  },
  readiness: (claimId: string) => http.get<T.ClaimReadiness>(`/api/claims/${claimId}/readiness`).then((r) => r.data),
  timeline: (claimId: string) => http.get<T.TimelineEvent[]>(`/api/claims/${claimId}/timeline`).then((r) => r.data),
  tracking: (claimId: string) => http.get<T.ClaimTracking>(`/api/claims/${claimId}/tracking`).then((r) => r.data),
  prepareSubmission: (claimId: string) => http.post<T.SubmitClaimResponse>(`/api/claims/${claimId}/submit`).then((r) => r.data),
  investigateClaim: (claimId: string, message: string | null, language: string) => http.post<T.InvestigationResult>(`/api/claims/${claimId}/investigate`, { message, language }).then((r) => r.data),
  confirmValue: (claimId: string, field: string, value: string, note = '') => http.post<T.ActionApproveResponse>(`/api/claims/${claimId}/confirm-value`, { field, value, note }).then((r) => r.data),

  // actions
  action: (id: string) => http.get<T.ActionProposal>(`/api/actions/${id}`).then((r) => r.data),
  actions: (journey_id?: string) => http.get<T.ActionProposal[]>('/api/actions', { params: { journey_id } }).then((r) => r.data),
  approveAction: (id: string) => http.post<T.ActionApproveResponse>(`/api/actions/${id}/approve`).then((r) => r.data),
  executeAction: (id: string, language: string) => http.post<T.ExecutionResult>(`/api/actions/${id}/execute`, { language }).then((r) => r.data),

  // journeys
  journeys: () => http.get<T.JourneyOut[]>('/api/journeys').then((r) => r.data),
  journey: (id: string) => http.get<T.JourneyDetail>(`/api/journeys/${id}`).then((r) => r.data),
  investigateJourney: (id: string, message: string | null, language: string) => http.post<T.InvestigationResult>(`/api/journeys/${id}/investigation`, { message, language }).then((r) => r.data),
  recoveryPlan: (id: string, language: string) => http.post<T.RecoveryPlan>(`/api/journeys/${id}/recovery`, { language }).then((r) => r.data),
  recoveryAttempts: (id: string) => http.get<T.RecoveryAttemptOut[]>(`/api/journeys/${id}/recovery-attempts`).then((r) => r.data),

  // discovery
  products: () => http.get<T.ProductOut[]>('/api/discovery/products').then((r) => r.data),
  discover: (req: T.DiscoveryRequest) => http.post<T.DiscoveryResponse>('/api/discovery', req).then((r) => r.data),

  // notifications
  notifications: () => http.get<T.NotificationOut[]>('/api/notifications').then((r) => r.data),
  markRead: (id: string) => http.post<T.NotificationOut>(`/api/notifications/${id}/read`).then((r) => r.data),
  markAllRead: () => http.post('/api/notifications/read-all').then((r) => r.data),

  // escalations
  escalations: () => http.get<T.EscalationPacket[]>('/api/escalations').then((r) => r.data),
  escalation: (id: string) => http.get<T.EscalationPacket>(`/api/escalations/${id}`).then((r) => r.data),
  createEscalation: (body: { journey_id?: string | null; claim_id?: string | null; problem: string; reason?: string }) => http.post<T.EscalationPacket>('/api/escalations', body).then((r) => r.data),

  // voice / translate
  transcribe: (blob: Blob, language?: string) => {
    const fd = new FormData()
    fd.append('file', blob, 'recording.webm')
    if (language) fd.append('language', language)
    return http.post<T.TranscribeResponse>('/api/voice/transcribe', fd).then((r) => r.data)
  },
  speak: (text: string, language: string) => http.post<{ audio_base64: string; format: string }>('/api/voice/speak', { text, language }).then((r) => r.data),
  translate: (text: string, source_language: string, target_language: string) => http.post<T.TranslateResponse>('/api/translate', { text, source_language, target_language }).then((r) => r.data),

  // demo
  loadDemo: () => http.post<T.DemoLoadResponse>('/api/demo/load-recovery-demo').then((r) => r.data),
  scenarios: () => http.get<Record<string, { claim_id: string; journey_id: string; claim_number: string }>>('/api/demo/scenarios').then((r) => r.data),

  // mock insurer (read-only view for the demo)
  insurerClaim: (externalId: string) => http.get<Record<string, any>>(`/mock-insurer/claims/${externalId}`).then((r) => r.data),
}
