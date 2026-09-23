"""Request/response DTOs for the REST API."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai import (
    ActionProposal,
    ClaimReadiness,
    EscalationPacket,
    ExecutionResult,
    IncidentClassification,
    InvestigationResult,
    PolicyAnswer,
    RecoveryPlan,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Auth ----
class DemoLoginRequest(BaseModel):
    demo_code: str = Field("demo", description="Demo account code, e.g. 'demo'")
    language: Optional[str] = None


class UserOut(ORMModel):
    id: str
    email: str
    name: str
    preferred_language: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UpdateLanguageRequest(BaseModel):
    language: str


# ---- Policies ----
class PolicyCoverageOut(ORMModel):
    id: str
    name: str
    covered: str
    limit_amount: Optional[float]
    limit_text: str
    condition_text: str
    section_ref: str


class PolicyConditionOut(ORMModel):
    id: str
    kind: str
    title: str
    description: str
    value: str
    section_ref: str


class PolicySummary(ORMModel):
    id: str
    policy_number: str
    insurer: str
    policy_type: str
    plan_name: str
    holder_name: str
    sum_insured: float
    premium: float
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    deductible: float
    waiting_period_days: int
    claim_types: List[str]
    status: str
    knowledge_indexed: bool
    knowledge_backend: str
    days_to_expiry: Optional[int] = None


class PolicyDetail(PolicySummary):
    insured_members: List[str]
    structured_profile: Dict[str, Any]
    coverages: List[PolicyCoverageOut]
    conditions: List[PolicyConditionOut]
    source_file: Optional[str]


class PolicyAskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    language: str = "en"


class PolicyAskResponse(BaseModel):
    question: str
    answer: PolicyAnswer
    language: str


# ---- Incidents ----
class IncidentAnalyzeRequest(BaseModel):
    description: str = Field(min_length=3, max_length=2000)
    language: str = "en"


class IncidentAnalyzeResponse(BaseModel):
    classification: IncidentClassification
    policies: List[PolicySummary]


# ---- Claims ----
class ClaimCreateRequest(BaseModel):
    policy_id: str
    claim_type: str
    incident_type: str
    incident_date: Optional[datetime] = None
    incident_time: str = ""
    incident_description: str = ""
    location: str = ""
    affected_asset: str = ""
    people_involved: str = ""
    claimed_amount: float = 0


class DocumentOut(ORMModel):
    id: str
    document_type: str
    file_name: str
    mime_type: str
    size_bytes: int
    extracted_fields: Dict[str, Any]
    classification_confidence: float
    validation_status: str
    issues: List[str]
    attached_to_insurer: bool
    uploaded_at: datetime


class RequirementOut(ORMModel):
    id: str
    document_type: str
    label: str
    description: str
    required: bool
    status: str
    source: str
    fulfilled_by_document_id: Optional[str]


class InsurerQueryOut(ORMModel):
    id: str
    message: str
    requested_document_type: Optional[str]
    status: str
    raised_at: datetime
    resolved_at: Optional[datetime]


class ClaimSummary(ORMModel):
    id: str
    claim_number: str
    policy_id: str
    journey_id: Optional[str]
    claim_type: str
    incident_type: str
    incident_date: Optional[datetime]
    status: str
    external_claim_id: Optional[str]
    external_status: Optional[str]
    settlement_status: str
    payment_status: str
    claimed_amount: float
    submitted_at: Optional[datetime]
    scenario: str
    created_at: datetime
    updated_at: datetime


class ClaimDetail(ClaimSummary):
    incident_time: str
    incident_description: str
    location: str
    affected_asset: str
    people_involved: str
    user_confirmations: Dict[str, Any]
    documents: List[DocumentOut]
    requirements: List[RequirementOut]
    queries: List[InsurerQueryOut]
    policy: Optional[PolicySummary] = None


class DocumentAnalysis(BaseModel):
    document: DocumentOut
    cross_document_issues: List[str]
    readiness: ClaimReadiness


class TimelineEvent(BaseModel):
    id: str
    event_type: str
    from_state: Optional[str]
    to_state: Optional[str]
    actor: str
    description: str
    metadata: Dict[str, Any]
    created_at: datetime


class TrackingStage(BaseModel):
    key: str
    label: str
    status: str  # DONE / CURRENT / PENDING / BLOCKED


class ClaimTracking(BaseModel):
    claim: ClaimSummary
    stages: List[TrackingStage]
    current_state: str
    current_state_label: str
    what_happened: str
    what_is_pending: str
    user_action_required: bool
    next_step: str
    timeline: List[TimelineEvent]
    open_queries: List[InsurerQueryOut]


class SubmitClaimResponse(BaseModel):
    action: ActionProposal
    readiness: ClaimReadiness
    message: str


class ConfirmDocumentValueRequest(BaseModel):
    field: str
    value: str
    note: str = ""


# ---- Journeys ----
class JourneyOut(ORMModel):
    id: str
    policy_id: Optional[str]
    claim_id: Optional[str]
    journey_type: str
    title: str
    current_state: str
    previous_state: Optional[str]
    health: str
    progress_percent: int
    external_status: Optional[str]
    outstanding_requirements: List[str]
    recovery_attempt_count: int
    created_at: datetime
    updated_at: datetime


class JourneyDetail(JourneyOut):
    timeline: List[TimelineEvent] = Field(default_factory=list)
    last_investigation: Optional[Dict[str, Any]] = None
    claim: Optional[ClaimSummary] = None


class InvestigateRequest(BaseModel):
    message: Optional[str] = None
    language: str = "en"


class RecoveryPlanRequest(BaseModel):
    language: str = "en"


class RecoveryAttemptOut(ORMModel):
    id: str
    journey_id: str
    claim_id: Optional[str]
    action_request_id: Optional[str]
    blocker: str
    plan: Dict[str, Any]
    status: str
    before_state: Optional[str]
    after_state: Optional[str]
    result: Optional[Dict[str, Any]]
    created_at: datetime
    completed_at: Optional[datetime]


# ---- Actions ----
class ActionApproveResponse(BaseModel):
    action: ActionProposal
    message: str


class ActionExecuteRequest(BaseModel):
    language: str = "en"


# ---- Dashboard ----
class ImportantDate(BaseModel):
    label: str
    date: datetime
    kind: str
    days_from_now: int
    policy_id: Optional[str] = None
    claim_id: Optional[str] = None


class ActionRequiredItem(BaseModel):
    title: str
    detail: str
    link: str
    journey_id: Optional[str] = None
    claim_id: Optional[str] = None
    severity: str = "ATTENTION"


class DashboardResponse(BaseModel):
    user: UserOut
    policies: List[PolicySummary]
    journeys: List[JourneyOut]
    claims: List[ClaimSummary]
    action_required: List[ActionRequiredItem]
    important_dates: List[ImportantDate]
    unread_notifications: int
    greeting: str
    suggested_actions: List[Dict[str, str]]
    integrations: Dict[str, Any]


# ---- Chat / Ask COVE2E ----
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    language: str = "en"
    journey_id: Optional[str] = None
    claim_id: Optional[str] = None
    policy_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    intent: str
    confidence: float
    language: str
    source: str  # AI / DETERMINISTIC
    data: Dict[str, Any] = Field(default_factory=dict)
    suggested_actions: List[Dict[str, str]] = Field(default_factory=list)
    navigate_to: Optional[str] = None


# ---- Discovery ----
class DiscoveryRequest(BaseModel):
    age: int = Field(ge=0, le=120)
    family_situation: str = "single"
    occupation: str = ""
    assets: List[str] = Field(default_factory=list)
    existing_coverage: List[str] = Field(default_factory=list)
    budget_annual: float = 0
    risk_requirements: List[str] = Field(default_factory=list)
    insurance_type: str = "HEALTH"
    language: str = "en"


class ProductOut(ORMModel):
    id: str
    code: str
    name: str
    insurer: str
    product_type: str
    description: str
    sum_insured: float
    premium_annual: float
    deductible: float
    waiting_period_days: int
    limits: Dict[str, Any]
    exclusions: List[str]
    conditions: List[str]
    network_info: str
    required_documents: List[str]


class DiscoveryMatch(BaseModel):
    product: ProductOut
    match_score: int
    reasons: List[str]
    cautions: List[str]


class DiscoveryResponse(BaseModel):
    matches: List[DiscoveryMatch]
    narrative: str
    narrative_source: str
    disclaimer: str


# ---- Notifications ----
class NotificationOut(ORMModel):
    id: str
    journey_id: Optional[str]
    claim_id: Optional[str]
    kind: str
    title: str
    message: str
    read: bool
    link: str
    created_at: datetime


# ---- Escalations ----
class EscalationCreateRequest(BaseModel):
    journey_id: Optional[str] = None
    claim_id: Optional[str] = None
    problem: str = Field(min_length=3)
    reason: str = ""


# ---- Voice / Translate ----
class TranscribeResponse(BaseModel):
    transcript: str
    language_code: Optional[str]
    source: str


class TranslateRequest(BaseModel):
    text: str
    source_language: str = "en"
    target_language: str


class TranslateResponse(BaseModel):
    translated_text: str
    source: str


class TTSRequest(BaseModel):
    text: str
    language: str = "en"


# ---- Demo ----
class DemoLoadResponse(BaseModel):
    message: str
    user: UserOut
    policy_id: str
    claim_id: str
    journey_id: str
    claim_number: str
    scenarios: Dict[str, Dict[str, str]]


class AuditLogOut(ORMModel):
    id: str
    journey_id: Optional[str]
    claim_id: Optional[str]
    action: str
    actor: str
    previous_state: Optional[str]
    new_state: Optional[str]
    result: str
    created_at: datetime


class IntegrationStatus(BaseModel):
    sarvam: Dict[str, Any]
    cognee: Dict[str, Any]
    n8n: Dict[str, Any]
    database: Dict[str, Any]
    demo_mode: bool


# Re-exports for convenience
__all__ = [
    "InvestigationResult",
    "RecoveryPlan",
    "ExecutionResult",
    "EscalationPacket",
    "IncidentClassification",
    "PolicyAnswer",
]
