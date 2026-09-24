// TypeScript mirror of backend/app/schemas/api.py and schemas/ai.py

export type Language = 'en' | 'hi' | 'mr'

export interface UserOut { id: string; email: string; name: string; preferred_language: string }
export interface TokenResponse { access_token: string; token_type: string; user: UserOut }

// ---- Policies ----
export interface PolicyCoverageOut { id: string; name: string; covered: 'YES' | 'NO' | 'CONDITIONAL'; limit_amount: number | null; limit_text: string; condition_text: string; section_ref: string }
export interface PolicyConditionOut { id: string; kind: string; title: string; description: string; value: string; section_ref: string }
export interface PolicySummary {
  id: string; policy_number: string; insurer: string; policy_type: string; plan_name: string; holder_name: string
  sum_insured: number; premium: number; start_date: string | null; end_date: string | null; deductible: number
  waiting_period_days: number; claim_types: string[]; status: string; knowledge_indexed: boolean; knowledge_backend: string
  days_to_expiry: number | null; is_demo?: boolean
}
export interface PolicyDetail extends PolicySummary {
  insured_members: string[]; structured_profile: Record<string, any>; coverages: PolicyCoverageOut[]; conditions: PolicyConditionOut[]; source_file: string | null
}
export type FactType = 'POLICY_FACT' | 'AI_INTERPRETATION' | 'MISSING_INFORMATION' | 'GENERAL_GUIDANCE' | 'EXTERNAL_INSURER_DECISION'
export interface PolicyAnswer {
  answer: string; coverage: 'YES' | 'NO' | 'CONDITIONAL' | 'UNKNOWN'; why: string; important_condition: string; what_you_should_do: string
  source: string; fact_types: FactType[]; confidence: number; knowledge_backend: string; retrieved_context: string[]
}
export interface PolicyAskResponse { question: string; answer: PolicyAnswer; language: string }

// ---- Incidents ----
export interface IncidentClassification {
  incident_type: string; incident_label: string; policy_type: 'HEALTH' | 'MOTOR' | 'GADGET' | 'UNKNOWN'; matched_policy_id: string | null; matched_policy_label: string | null
  urgency: 'LOW' | 'MEDIUM' | 'HIGH'; journey: string; suggested_claim_type: string | null; required_information: string[]; next_actions: string[]
  coverage_note: string; confidence: number; summary: string
}
export interface IncidentAnalyzeResponse { classification: IncidentClassification; policies: PolicySummary[] }

// ---- Claims ----
export interface ClaimCreateRequest {
  policy_id: string; claim_type: string; incident_type: string; incident_date?: string | null; incident_time?: string; incident_description?: string
  location?: string; affected_asset?: string; people_involved?: string; claimed_amount?: number
}
export interface DocumentOut {
  id: string; document_type: string; file_name: string; mime_type: string; size_bytes: number; extracted_fields: Record<string, any>
  classification_confidence: number; validation_status: 'VALID' | 'NEEDS_REVIEW' | 'INVALID' | 'PENDING'; issues: string[]; attached_to_insurer: boolean; uploaded_at: string
}
export interface RequirementOut { id: string; document_type: string; label: string; description: string; required: boolean; status: string; source: string; fulfilled_by_document_id: string | null }
export interface InsurerQueryOut { id: string; message: string; requested_document_type: string | null; status: string; raised_at: string; resolved_at: string | null }
export interface ClaimSummary {
  id: string; claim_number: string; policy_id: string; journey_id: string | null; claim_type: string; incident_type: string; incident_date: string | null
  status: string; external_claim_id: string | null; external_status: string | null; settlement_status: string; payment_status: string; claimed_amount: number
  submitted_at: string | null; scenario: string; created_at: string; updated_at: string
}
export interface ClaimDetail extends ClaimSummary {
  incident_time: string; incident_description: string; location: string; affected_asset: string; people_involved: string; user_confirmations: Record<string, any>
  documents: DocumentOut[]; requirements: RequirementOut[]; queries: InsurerQueryOut[]; policy: PolicySummary | null
}
export interface ReadinessItem { label: string; status: 'DONE' | 'WARNING' | 'MISSING'; detail: string; document_type: string | null }
export interface ClaimReadiness { claim_id: string; percent: number; items: ReadinessItem[]; outstanding_count: number; next_action: string; ready_to_submit: boolean; disclaimer: string }
export interface DocumentAnalysis { document: DocumentOut; cross_document_issues: string[]; readiness: ClaimReadiness }
export interface TimelineEvent { id: string; event_type: string; from_state: string | null; to_state: string | null; actor: string; description: string; metadata: Record<string, any>; created_at: string }
export interface TrackingStage { key: string; label: string; status: 'DONE' | 'CURRENT' | 'PENDING' | 'BLOCKED' }
export interface ClaimTracking {
  claim: ClaimSummary; stages: TrackingStage[]; current_state: string; current_state_label: string; what_happened: string; what_is_pending: string
  user_action_required: boolean; next_step: string; timeline: TimelineEvent[]; open_queries: InsurerQueryOut[]
}

// ---- Actions / Gate ----
export type GateDecision = 'SAFE' | 'CONFIRM' | 'ESCALATE' | 'DENY'
export type RiskClass = 'AUTO_RECOVERABLE' | 'USER_CONFIRMATION_REQUIRED' | 'HUMAN_ESCALATION_REQUIRED'
export interface Prerequisite { key: string; label: string; satisfied: boolean; hint: string; document_type: string | null }
export interface GateCheck { name: string; passed: boolean; detail: string }
export interface ActionProposal {
  id: string; action_type: string; title: string; description: string; risk_class: RiskClass; gate_decision: GateDecision; gate_reasons: string[]
  gate_checks: GateCheck[]; prerequisites: Prerequisite[]; can_execute: boolean; status: string; payload: Record<string, any>
}
export interface SubmitClaimResponse { action: ActionProposal; readiness: ClaimReadiness; message: string }
export interface ActionApproveResponse { action: ActionProposal; message: string }
export interface ExecutionStep { key: string; label: string; status: 'DONE' | 'FAILED' | 'SKIPPED'; detail: string }
export interface VerificationResult {
  outcome: 'VERIFIED' | 'UNCHANGED' | 'CONFLICT' | 'ERROR'; before_state: string | null; after_state: string | null; expected_state: string | null
  external_snapshot: Record<string, any>; message: string; journey_state_before: string | null; journey_state_after: string | null
}
export interface ExecutionResult {
  action_id: string; status: string; executor: 'n8n' | 'demo-fallback' | 'internal'; steps: ExecutionStep[]; verification: VerificationResult | null
  final_message: string; recovery_status: string | null; escalation_id: string | null; workflow_run_id: string | null
}

// ---- Journeys / Investigation / Recovery ----
export interface JourneyOut {
  id: string; policy_id: string | null; claim_id: string | null; journey_type: string; title: string; current_state: string; previous_state: string | null
  health: 'HEALTHY' | 'ATTENTION' | 'BLOCKED' | 'ESCALATED' | 'COMPLETE'; progress_percent: number; external_status: string | null
  outstanding_requirements: string[]; recovery_attempt_count: number; created_at: string; updated_at: string
}
export interface JourneyDetail extends JourneyOut { timeline: TimelineEvent[]; last_investigation: InvestigationResult | null; claim: ClaimSummary | null }
export interface InvestigationCheck { name: string; label: string; status: 'OK' | 'ISSUE' | 'INFO'; finding: string }
export interface InvestigationResult {
  intent: string; journey_id: string; claim_id: string | null; current_state: string; current_state_label: string; external_status: string | null
  blocker: string; blocker_label: string; evidence: string[]; affected_step: string; next_action: string; next_action_label: string; confidence: number
  requires_confirmation: boolean; requires_escalation: boolean; checks: InvestigationCheck[]; explanation: string; explanation_source: 'AI' | 'DETERMINISTIC'; days_stuck: number | null
}
export interface RecoveryStep { order: number; key: string; label: string; description: string; status: 'DONE' | 'READY' | 'PENDING_USER' | 'PENDING' | 'RUNNING' | 'FAILED' | 'SKIPPED'; actor: string }
export interface RecoveryPlan {
  journey_id: string; claim_id: string | null; recovery_attempt_id: string | null; blocker: string; blocker_label: string; summary: string; steps: RecoveryStep[]
  risk_class: RiskClass; action: ActionProposal | null; escalation_id: string | null; status: string; message: string; message_source: 'AI' | 'DETERMINISTIC'
}
export interface RecoveryAttemptOut {
  id: string; journey_id: string; claim_id: string | null; action_request_id: string | null; blocker: string; plan: { steps?: RecoveryStep[]; summary?: string; risk_class?: string }
  status: string; before_state: string | null; after_state: string | null; result: Record<string, any> | null; created_at: string; completed_at: string | null
}

// ---- Dashboard ----
export interface ImportantDate { label: string; date: string; kind: string; days_from_now: number; policy_id: string | null; claim_id: string | null }
export interface ActionRequiredItem { title: string; detail: string; link: string; journey_id: string | null; claim_id: string | null; severity: string }
export interface IntegrationStatus { sarvam: Record<string, any>; cognee: Record<string, any>; n8n: Record<string, any>; database: Record<string, any>; demo_mode: boolean }
export interface DashboardResponse {
  user: UserOut; policies: PolicySummary[]; journeys: JourneyOut[]; claims: ClaimSummary[]; action_required: ActionRequiredItem[]; important_dates: ImportantDate[]
  unread_notifications: number; greeting: string; suggested_actions: { key: string; label: string; link: string }[]; integrations: IntegrationStatus
}

// ---- Chat ----
export interface ChatRequest { message: string; language: Language; journey_id?: string | null; claim_id?: string | null; policy_id?: string | null }
export interface ChatResponse {
  reply: string; intent: string; confidence: number; language: string; source: 'AI' | 'DETERMINISTIC' | string; data: Record<string, any>
  suggested_actions: { label: string; link: string }[]; navigate_to: string | null
}

// ---- Discovery ----
export interface DiscoveryRequest {
  age: number; family_situation: string; occupation: string; assets: string[]; existing_coverage: string[]; budget_annual: number
  risk_requirements: string[]; insurance_type: string; language: Language
}
export interface ProductOut {
  id: string; code: string; name: string; insurer: string; product_type: string; description: string; sum_insured: number; premium_annual: number; deductible: number
  waiting_period_days: number; limits: Record<string, any>; exclusions: string[]; conditions: string[]; network_info: string; required_documents: string[]
}
export interface DiscoveryMatch { product: ProductOut; match_score: number; reasons: string[]; cautions: string[] }
export interface DiscoveryResponse { matches: DiscoveryMatch[]; narrative: string; narrative_source: string; disclaimer: string }

// ---- Notifications / Escalations ----
export interface NotificationOut { id: string; journey_id: string | null; claim_id: string | null; kind: 'INFO' | 'ACTION_REQUIRED' | 'SUCCESS' | 'WARNING'; title: string; message: string; read: boolean; link: string; created_at: string }
export interface EscalationPacket {
  id: string; reference: string; problem: string; evidence: string[]; current_state: string; actions_attempted: string[]; reason: string; recommended_action: string
  priority: string; status: string; journey_id: string | null; claim_id: string | null; external_snapshot: Record<string, any>; created_at: string | null
}

// ---- Voice / Translate / Demo ----
export interface TranscribeResponse { transcript: string; language_code: string | null; source: string }
export interface TranslateResponse { translated_text: string; source: string }
export interface DemoLoadResponse { message: string; user: UserOut; policy_id: string; claim_id: string; journey_id: string; claim_number: string; scenarios: Record<string, { claim_id: string; journey_id: string; claim_number: string }> }
export interface AuditLogOut { id: string; journey_id: string | null; claim_id: string | null; action: string; actor: string; previous_state: string | null; new_state: string | null; result: string; created_at: string }
