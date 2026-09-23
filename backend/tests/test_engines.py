"""Engine-level tests: state machine, action gate, investigation, recovery, verification, escalation."""
import pytest

from app.core.enums import ActionType, Blocker, GateDecision, JourneyState, RiskClass
from app.engines import action_gate, investigation_engine, journey_state_engine as jse, recovery_engine
from app.models import Claim, Journey
from app.services import workflow_executor
from app.services.mock_insurer_service import MockInsurerService


# ---- Journey state engine ----
def test_valid_and_invalid_transitions(db, demo_user):
    j = Journey(user_id=demo_user.id, title="t", current_state=JourneyState.POLICY_ACTIVE)
    db.add(j)
    db.flush()
    jse.transition(db, j, JourneyState.INCIDENT_DETECTED, reason="test")
    jse.transition(db, j, JourneyState.CLAIM_STARTED, reason="test")
    assert j.current_state == JourneyState.CLAIM_STARTED
    assert len(j.events) == 2
    with pytest.raises(jse.InvalidTransition):
        jse.transition(db, j, JourneyState.RESOLVED)
    db.rollback()


def test_sync_from_insurer_walks_path(db, demo_user):
    j = Journey(user_id=demo_user.id, title="t", current_state=JourneyState.SUBMISSION)
    db.add(j)
    db.flush()
    jse.sync_from_insurer_status(db, j, "DOCUMENT_PENDING", has_open_query=True)
    assert j.current_state == JourneyState.QUERY_RAISED
    assert j.health == "BLOCKED"
    jse.sync_from_insurer_status(db, j, "UNDER_REVIEW")
    assert j.current_state == JourneyState.UNDER_REVIEW
    db.rollback()


# ---- Action gate ----
def test_gate_unsupported_action_denied():
    r = action_gate.evaluate(ActionType.MODIFY_DOCUMENT, claim=None, journey=None, payload={})
    assert r.decision == GateDecision.DENY


def test_gate_insurer_authority_escalates():
    r = action_gate.evaluate(ActionType.RESOLVE_EXTERNAL_CONFLICT, claim=None, journey=None, payload={})
    assert r.decision == GateDecision.ESCALATE
    assert r.risk_class == RiskClass.HUMAN_ESCALATION_REQUIRED


def test_gate_read_only_is_safe():
    r = action_gate.evaluate(ActionType.POLL_STATUS, claim=None, journey=None, payload={})
    assert r.decision == GateDecision.SAFE
    assert r.risk_class == RiskClass.AUTO_RECOVERABLE


def test_gate_attach_requires_document(db, demo_data):
    claim = db.get(Claim, demo_data["claim_id"])
    journey = db.get(Journey, claim.journey_id)
    r = action_gate.evaluate(ActionType.ATTACH_AND_RESUBMIT, claim=claim, journey=journey, payload={"document_type": "medical_certificate"})
    assert r.decision == GateDecision.CONFIRM
    assert not r.can_execute  # certificate not uploaded yet
    assert any(p.key == "document_uploaded" and not p.satisfied for p in r.prerequisites)


# ---- Investigation ----
def test_investigation_finds_missing_requested_document(db, demo_data):
    claim = db.get(Claim, demo_data["claim_id"])
    journey = db.get(Journey, claim.journey_id)
    result = investigation_engine.investigate(db, journey, claim)
    assert result.blocker == Blocker.MISSING_REQUESTED_DOCUMENT
    assert result.external_status == "DOCUMENT_PENDING"
    assert result.requires_confirmation and not result.requires_escalation
    assert any("Medical certificate" in e for e in result.evidence)
    names = {c.name for c in result.checks}
    assert {"policy", "claim_state", "documents", "insurer_query", "timeline", "previous_actions", "external_state"} <= names


def test_investigation_detects_conflicting_state(db, demo_data):
    claim = db.get(Claim, demo_data["conflicting_state"])
    journey = db.get(Journey, claim.journey_id)
    result = investigation_engine.investigate(db, journey, claim)
    assert result.blocker == Blocker.CONFLICTING_EXTERNAL_STATE
    assert result.requires_escalation


def test_investigation_detects_document_inconsistency(db, demo_data):
    claim = db.get(Claim, demo_data["document_inconsistency"])
    journey = db.get(Journey, claim.journey_id)
    result = investigation_engine.investigate(db, journey, claim)
    assert result.blocker == Blocker.DOCUMENT_INCONSISTENCY
    assert any("admission date" in e.lower() for e in result.evidence)


def test_investigation_normal_claim_has_no_blocker(db, demo_data):
    claim = db.get(Claim, demo_data["normal"])
    journey = db.get(Journey, claim.journey_id)
    result = investigation_engine.investigate(db, journey, claim)
    assert result.blocker == Blocker.AWAITING_INSURER


# ---- CRITICAL: DOCUMENT_PENDING → recovery → UNDER_REVIEW ----
def test_recovery_document_pending_to_under_review(db, demo_user, demo_data):
    from app.services import claim_service
    from app.services.demo_service import MOCK

    claim = db.get(Claim, demo_data["claim_id"])
    journey = db.get(Journey, claim.journey_id)
    assert claim.status == "DOCUMENT_PENDING"

    # 1. Investigate → blocker
    inv = investigation_engine.investigate(db, journey, claim)
    assert inv.blocker == Blocker.MISSING_REQUESTED_DOCUMENT

    # 2. Plan → action gated CONFIRM but not executable (document missing)
    plan = recovery_engine.build_plan(db, user=demo_user, journey=journey, claim=claim, investigation=inv)
    assert plan.action and plan.action.gate_decision == GateDecision.CONFIRM
    assert not plan.action.can_execute
    assert plan.risk_class == RiskClass.USER_CONFIRMATION_REQUIRED

    # 3. User uploads the certificate → prerequisites satisfied
    claim_service.add_document(db, demo_user, claim, (MOCK / "documents" / "medical_certificate.txt").read_bytes(), "medical_certificate.txt", "text/plain", "medical_certificate")
    db.refresh(claim)
    inv2 = investigation_engine.investigate(db, journey, claim)
    assert inv2.blocker == Blocker.REQUESTED_DOCUMENT_NOT_ATTACHED
    plan2 = recovery_engine.build_plan(db, user=demo_user, journey=journey, claim=claim, investigation=inv2)
    assert plan2.action.can_execute

    # 4. Confirm + execute (n8n unreachable in tests → labelled demo fallback) + verify
    from app.models import ActionRequest

    action = db.get(ActionRequest, plan2.action.id)
    workflow_executor.approve(db, user=demo_user, action=action)
    result = workflow_executor.execute(db, user=demo_user, action=action)
    assert result.executor == "demo-fallback"
    assert result.verification is not None
    assert result.verification.outcome == "VERIFIED"
    assert result.verification.before_state == "DOCUMENT_PENDING"
    assert result.verification.after_state == "UNDER_REVIEW"
    assert result.recovery_status == "SUCCEEDED"

    db.refresh(claim)
    db.refresh(journey)
    assert claim.status == "UNDER_REVIEW"
    assert journey.current_state == JourneyState.UNDER_REVIEW
    assert all(q.status == "RESOLVED" for q in claim.queries)
    assert "medical certificate" in result.final_message.lower()
    assert "approved" not in result.final_message.lower()
    db.commit()


# ---- CRITICAL: CONFLICTING_STATE → ESCALATED ----
def test_conflicting_state_escalates(db, demo_user, demo_data):
    claim = db.get(Claim, demo_data["conflicting_state"])
    journey = db.get(Journey, claim.journey_id)
    inv = investigation_engine.investigate(db, journey, claim)
    plan = recovery_engine.build_plan(db, user=demo_user, journey=journey, claim=claim, investigation=inv)
    assert plan.risk_class == RiskClass.HUMAN_ESCALATION_REQUIRED
    assert plan.escalation_id is not None
    assert plan.action.gate_decision == GateDecision.ESCALATE
    db.refresh(journey)
    assert journey.current_state == JourneyState.ESCALATED
    from app.models import Escalation

    esc = db.get(Escalation, plan.escalation_id)
    assert esc.problem and esc.evidence and esc.recommended_action
    # Insurer state must be untouched
    ext = MockInsurerService(db).get(claim.external_claim_id)
    assert ext.status == "APPROVED" and ext.payment_status == "COMPLETED" and ext.settlement_status == "PENDING"
    db.commit()


# ---- Scenario B: inconsistency requires user confirmation, no autonomous change ----
def test_document_inconsistency_requires_user_confirmation(db, demo_user, demo_data):
    from app.services.readiness_service import compute_readiness

    claim = db.get(Claim, demo_data["document_inconsistency"])
    journey = db.get(Journey, claim.journey_id)
    inv = investigation_engine.investigate(db, journey, claim)
    plan = recovery_engine.build_plan(db, user=demo_user, journey=journey, claim=claim, investigation=inv)
    assert plan.action.action_type == ActionType.CONFIRM_DOCUMENT_VALUE
    assert not plan.action.can_execute
    before = compute_readiness(claim)
    assert any("mismatch" in i.label.lower() for i in before.items)
    # Documents untouched
    docs = {d.document_type: d.extracted_fields.get("admission_date") for d in claim.documents}
    assert docs["hospital_bill"] != docs["discharge_summary"]
    db.commit()
