"""Structured AI output schemas. The LLM must produce these shapes; FastAPI validates them.

The LLM proposes. The application decides.
"""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class IntentResult(BaseModel):
    intent: Literal[
        "POLICY_QUESTION",
        "INCIDENT_REPORT",
        "START_CLAIM",
        "CLAIM_READINESS",
        "MISSING_DOCUMENTS",
        "TRACK_CLAIM",
        "STUCK_CLAIM",
        "COMPARE_INSURANCE",
        "ESCALATE",
        "GREETING",
        "GENERAL",
    ] = "GENERAL"
    confidence: float = Field(0.5, ge=0, le=1)
    entities: Dict[str, Any] = Field(default_factory=dict)
    language: str = "en"


class PolicyAnswer(BaseModel):
    answer: str
    coverage: Literal["YES", "NO", "CONDITIONAL", "UNKNOWN"] = "UNKNOWN"
    why: str = ""
    important_condition: str = ""
    what_you_should_do: str = ""
    source: str = ""
    fact_types: List[Literal["POLICY_FACT", "AI_INTERPRETATION", "MISSING_INFORMATION", "GENERAL_GUIDANCE", "EXTERNAL_INSURER_DECISION"]] = Field(default_factory=list)
    confidence: float = Field(0.5, ge=0, le=1)
    knowledge_backend: str = "local"
    retrieved_context: List[str] = Field(default_factory=list)


class IncidentClassification(BaseModel):
    incident_type: str
    incident_label: str
    policy_type: Literal["HEALTH", "MOTOR", "GADGET", "UNKNOWN"]
    matched_policy_id: Optional[str] = None
    matched_policy_label: Optional[str] = None
    urgency: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    journey: str = "CLAIM"
    suggested_claim_type: Optional[str] = None
    required_information: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    coverage_note: str = ""
    confidence: float = Field(0.5, ge=0, le=1)
    summary: str = ""


class ReadinessItem(BaseModel):
    label: str
    status: Literal["DONE", "WARNING", "MISSING"]
    detail: str = ""
    document_type: Optional[str] = None


class ClaimReadiness(BaseModel):
    claim_id: str
    percent: int = Field(ge=0, le=100)
    items: List[ReadinessItem]
    outstanding_count: int
    next_action: str
    ready_to_submit: bool
    disclaimer: str = "This percentage measures documentation and process completeness. It is not a prediction of approval or payout."


class InvestigationCheck(BaseModel):
    name: str
    label: str
    status: Literal["OK", "ISSUE", "INFO"]
    finding: str


class InvestigationResult(BaseModel):
    intent: str = "STUCK_CLAIM"
    journey_id: str
    claim_id: Optional[str] = None
    current_state: str
    current_state_label: str
    external_status: Optional[str] = None
    blocker: str
    blocker_label: str
    evidence: List[str]
    affected_step: str
    next_action: str
    next_action_label: str
    confidence: float = Field(ge=0, le=1)
    requires_confirmation: bool
    requires_escalation: bool
    checks: List[InvestigationCheck]
    explanation: str = ""
    explanation_source: Literal["AI", "DETERMINISTIC"] = "DETERMINISTIC"
    days_stuck: Optional[int] = None


class RecoveryStep(BaseModel):
    order: int
    key: str
    label: str
    description: str = ""
    status: Literal["DONE", "READY", "PENDING_USER", "PENDING", "RUNNING", "FAILED", "SKIPPED"] = "PENDING"
    actor: Literal["USER", "SYSTEM", "N8N", "INSURER", "HUMAN_AGENT"] = "SYSTEM"


class Prerequisite(BaseModel):
    key: str
    label: str
    satisfied: bool
    hint: str = ""
    document_type: Optional[str] = None


class ActionProposal(BaseModel):
    id: str
    action_type: str
    title: str
    description: str
    risk_class: str
    gate_decision: str
    gate_reasons: List[str]
    gate_checks: List[Dict[str, Any]]
    prerequisites: List[Prerequisite]
    can_execute: bool
    status: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class RecoveryPlan(BaseModel):
    journey_id: str
    claim_id: Optional[str] = None
    recovery_attempt_id: Optional[str] = None
    blocker: str
    blocker_label: str
    summary: str
    steps: List[RecoveryStep]
    risk_class: str
    action: Optional[ActionProposal] = None
    escalation_id: Optional[str] = None
    status: str
    message: str
    message_source: Literal["AI", "DETERMINISTIC"] = "DETERMINISTIC"


class ExecutionStep(BaseModel):
    key: str
    label: str
    status: Literal["DONE", "FAILED", "SKIPPED"]
    detail: str = ""


class VerificationResult(BaseModel):
    outcome: Literal["VERIFIED", "UNCHANGED", "CONFLICT", "ERROR"]
    before_state: Optional[str]
    after_state: Optional[str]
    expected_state: Optional[str]
    external_snapshot: Dict[str, Any] = Field(default_factory=dict)
    message: str
    journey_state_before: Optional[str] = None
    journey_state_after: Optional[str] = None


class ExecutionResult(BaseModel):
    action_id: str
    status: str
    executor: Literal["n8n", "demo-fallback", "internal"]
    steps: List[ExecutionStep]
    verification: Optional[VerificationResult] = None
    final_message: str
    recovery_status: Optional[str] = None
    escalation_id: Optional[str] = None
    workflow_run_id: Optional[str] = None


class EscalationPacket(BaseModel):
    id: str
    reference: str
    problem: str
    evidence: List[str]
    current_state: str
    actions_attempted: List[str]
    reason: str
    recommended_action: str
    priority: str
    status: str
    journey_id: Optional[str] = None
    claim_id: Optional[str] = None
    external_snapshot: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
