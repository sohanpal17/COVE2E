"""SQLAlchemy models for COVE2E.

All public identifiers are UUID strings (String(36)) so the schema is portable
between PostgreSQL (primary) and SQLite (local fallback / tests).
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(8), default="en")
    demo_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)

    policies: Mapped[List["Policy"]] = relationship(back_populates="user")


class InsuranceProduct(Base, TimestampMixin):
    __tablename__ = "insurance_products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    insurer: Mapped[str] = mapped_column(String(255))
    product_type: Mapped[str] = mapped_column(String(32), index=True)  # HEALTH / MOTOR
    description: Mapped[str] = mapped_column(Text, default="")
    sum_insured: Mapped[float] = mapped_column(Float)
    premium_annual: Mapped[float] = mapped_column(Float)
    deductible: Mapped[float] = mapped_column(Float, default=0)
    waiting_period_days: Mapped[int] = mapped_column(Integer, default=0)
    limits: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    exclusions: Mapped[List[str]] = mapped_column(JSON, default=list)
    conditions: Mapped[List[str]] = mapped_column(JSON, default=list)
    network_info: Mapped[str] = mapped_column(String(255), default="")
    required_documents: Mapped[List[str]] = mapped_column(JSON, default=list)
    suitability_tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    min_age: Mapped[int] = mapped_column(Integer, default=18)
    max_age: Mapped[int] = mapped_column(Integer, default=65)


class Policy(Base, TimestampMixin):
    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    product_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("insurance_products.id"), nullable=True)
    policy_number: Mapped[str] = mapped_column(String(64), index=True)
    insurer: Mapped[str] = mapped_column(String(255))
    policy_type: Mapped[str] = mapped_column(String(32), index=True)
    plan_name: Mapped[str] = mapped_column(String(255), default="")
    holder_name: Mapped[str] = mapped_column(String(255), default="")
    insured_members: Mapped[List[str]] = mapped_column(JSON, default=list)
    sum_insured: Mapped[float] = mapped_column(Float, default=0)
    premium: Mapped[float] = mapped_column(Float, default=0)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deductible: Mapped[float] = mapped_column(Float, default=0)
    waiting_period_days: Mapped[int] = mapped_column(Integer, default=0)
    claim_types: Mapped[List[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    source_file: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    structured_profile: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    knowledge_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    knowledge_backend: Mapped[str] = mapped_column(String(32), default="local")

    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="policies")
    coverages: Mapped[List["PolicyCoverage"]] = relationship(back_populates="policy", cascade="all, delete-orphan")
    conditions: Mapped[List["PolicyCondition"]] = relationship(back_populates="policy", cascade="all, delete-orphan")

    @property
    def is_mock(self) -> bool:
        return self.is_demo or self.product_id is not None or bool(self.source_file and "mock-data" in self.source_file)



class PolicyCoverage(Base):
    __tablename__ = "policy_coverages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    policy_id: Mapped[str] = mapped_column(String(36), ForeignKey("policies.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    keywords: Mapped[List[str]] = mapped_column(JSON, default=list)
    covered: Mapped[str] = mapped_column(String(16))  # YES / NO / CONDITIONAL
    limit_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    limit_text: Mapped[str] = mapped_column(String(255), default="")
    condition_text: Mapped[str] = mapped_column(Text, default="")
    section_ref: Mapped[str] = mapped_column(String(128), default="")

    policy: Mapped["Policy"] = relationship(back_populates="coverages")


class PolicyCondition(Base):
    __tablename__ = "policy_conditions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    policy_id: Mapped[str] = mapped_column(String(36), ForeignKey("policies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # EXCLUSION / WAITING_PERIOD / LIMIT / DEDUCTIBLE / CONDITION / CLAIM_PROCEDURE / REQUIRED_DOCUMENT
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    value: Mapped[str] = mapped_column(String(255), default="")
    section_ref: Mapped[str] = mapped_column(String(128), default="")

    policy: Mapped["Policy"] = relationship(back_populates="conditions")


class Journey(Base, TimestampMixin):
    __tablename__ = "journeys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    policy_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("policies.id"), nullable=True, index=True)
    claim_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    journey_type: Mapped[str] = mapped_column(String(32), default="CLAIM")
    title: Mapped[str] = mapped_column(String(255))
    current_state: Mapped[str] = mapped_column(String(32), index=True)
    previous_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    health: Mapped[str] = mapped_column(String(32), default="HEALTHY")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    external_status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    outstanding_requirements: Mapped[List[str]] = mapped_column(JSON, default=list)
    recovery_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_investigation: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    events: Mapped[List["JourneyEvent"]] = relationship(back_populates="journey", cascade="all, delete-orphan", order_by="JourneyEvent.created_at")


class JourneyEvent(Base):
    __tablename__ = "journey_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    journey_id: Mapped[str] = mapped_column(String(36), ForeignKey("journeys.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    from_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    actor: Mapped[str] = mapped_column(String(32), default="SYSTEM")
    description: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[Dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    journey: Mapped["Journey"] = relationship(back_populates="events")


class Claim(Base, TimestampMixin):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    policy_id: Mapped[str] = mapped_column(String(36), ForeignKey("policies.id"), index=True)
    journey_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("journeys.id"), nullable=True, index=True)
    claim_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    claim_type: Mapped[str] = mapped_column(String(32))
    incident_type: Mapped[str] = mapped_column(String(64))
    incident_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    incident_time: Mapped[str] = mapped_column(String(16), default="")
    incident_description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    affected_asset: Mapped[str] = mapped_column(String(255), default="")
    people_involved: Mapped[str] = mapped_column(String(255), default="")
    claimed_amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)  # mirrors insurer status
    external_claim_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    external_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    settlement_status: Mapped[str] = mapped_column(String(32), default="NOT_STARTED")
    payment_status: Mapped[str] = mapped_column(String(32), default="NOT_STARTED")
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_external_update_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scenario: Mapped[str] = mapped_column(String(64), default="")  # demo scenario tag
    user_confirmations: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    documents: Mapped[List["ClaimDocument"]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    requirements: Mapped[List["DocumentRequirement"]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    queries: Mapped[List["InsurerQuery"]] = relationship(back_populates="claim", cascade="all, delete-orphan")


class ClaimDocument(Base):
    __tablename__ = "claim_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("claims.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(64), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512), default="")
    mime_type: Mapped[str] = mapped_column(String(128), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    extracted_fields: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    classification_confidence: Mapped[float] = mapped_column(Float, default=0)
    validation_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    issues: Mapped[List[str]] = mapped_column(JSON, default=list)
    attached_to_insurer: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    claim: Mapped["Claim"] = relationship(back_populates="documents")


class DocumentRequirement(Base):
    __tablename__ = "document_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("claims.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="MISSING", index=True)
    source: Mapped[str] = mapped_column(String(32), default="POLICY")
    fulfilled_by_document_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    claim: Mapped["Claim"] = relationship(back_populates="requirements")


class InsurerQuery(Base):
    __tablename__ = "insurer_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("claims.id"), index=True)
    external_query_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    requested_document_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    claim: Mapped["Claim"] = relationship(back_populates="queries")


class ActionRequest(Base, TimestampMixin):
    __tablename__ = "action_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    journey_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("journeys.id"), nullable=True, index=True)
    claim_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("claims.id"), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    proposed_by: Mapped[str] = mapped_column(String(16), default="AI")
    gate_decision: Mapped[str] = mapped_column(String(16), default="CONFIRM")
    gate_reasons: Mapped[List[str]] = mapped_column(JSON, default=list)
    gate_checks: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    risk_class: Mapped[str] = mapped_column(String(48), default="USER_CONFIRMATION_REQUIRED")
    prerequisites: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="PROPOSED", index=True)
    execution_result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    verification_result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class RecoveryAttempt(Base, TimestampMixin):
    __tablename__ = "recovery_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    journey_id: Mapped[str] = mapped_column(String(36), ForeignKey("journeys.id"), index=True)
    claim_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("claims.id"), nullable=True, index=True)
    action_request_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("action_requests.id"), nullable=True)
    blocker: Mapped[str] = mapped_column(String(64))
    plan: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="PLANNED", index=True)
    before_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    after_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    journey_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    claim_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="INFO")
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    link: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    journey_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    claim_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(32), default="SYSTEM")
    previous_state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    new_state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(64), default="OK")
    meta: Mapped[Dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Escalation(Base, TimestampMixin):
    __tablename__ = "escalations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    journey_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("journeys.id"), nullable=True, index=True)
    claim_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("claims.id"), nullable=True, index=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    problem: Mapped[str] = mapped_column(Text)
    evidence: Mapped[List[str]] = mapped_column(JSON, default=list)
    current_state: Mapped[str] = mapped_column(String(64), default="")
    actions_attempted: Mapped[List[str]] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(Text, default="")
    recommended_action: Mapped[Text] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(16), default="HIGH")
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    external_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class MockInsurerClaim(Base, TimestampMixin):
    """Persistent state store of the mock insurer (deterministic external system)."""

    __tablename__ = "mock_insurer_claims"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. INS-CLM-10284
    claim_number: Mapped[str] = mapped_column(String(32), index=True)
    policy_number: Mapped[str] = mapped_column(String(64), default="")
    product_type: Mapped[str] = mapped_column(String(32), default="HEALTH")
    claim_type: Mapped[str] = mapped_column(String(32), default="REIMBURSEMENT")
    status: Mapped[str] = mapped_column(String(32), default="SUBMITTED", index=True)
    settlement_status: Mapped[str] = mapped_column(String(32), default="NOT_STARTED")
    payment_status: Mapped[str] = mapped_column(String(32), default="NOT_STARTED")
    claimed_amount: Mapped[float] = mapped_column(Float, default=0)
    documents: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    queries: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    history: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    required_documents: Mapped[List[str]] = mapped_column(JSON, default=list)


Index("ix_claims_user_status", Claim.user_id, Claim.status)
Index("ix_journeys_user_state", Journey.user_id, Journey.current_state)
