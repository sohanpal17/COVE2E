"""Policy / Action Gate.

Sits between AI reasoning and execution. The AI (or the recovery engine)
PROPOSES an action; this module DECIDES: SAFE / CONFIRM / ESCALATE / DENY.
Fully deterministic. Every decision is audited.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.enums import ActionStatus, ActionType, Actor, AuditAction, DocValidation, GateDecision, JourneyState, RiskClass
from app.models import ActionRequest, Claim, Journey, User
from app.schemas.ai import ActionProposal, Prerequisite
from app.services.audit_service import record_audit
from app.services.document_intelligence import label_for
from app.services.readiness_service import compute_readiness

# Static action policy table: (supported, modifies_external, reversible, needs_insurer_authority, sensitive)
ACTION_POLICY: Dict[str, Dict[str, Any]] = {
    ActionType.POLL_STATUS: dict(supported=True, modifies_external=False, reversible=True, insurer_authority=False, sensitive=False),
    ActionType.NOTIFY_USER: dict(supported=True, modifies_external=False, reversible=True, insurer_authority=False, sensitive=False),
    ActionType.REQUEST_DOCUMENT_FROM_USER: dict(supported=True, modifies_external=False, reversible=True, insurer_authority=False, sensitive=False),
    ActionType.ESCALATE: dict(supported=True, modifies_external=False, reversible=True, insurer_authority=False, sensitive=False),
    ActionType.CONFIRM_DOCUMENT_VALUE: dict(supported=True, modifies_external=False, reversible=True, insurer_authority=False, sensitive=True),
    ActionType.SUBMIT_CLAIM: dict(supported=True, modifies_external=True, reversible=False, insurer_authority=False, sensitive=True),
    ActionType.ATTACH_DOCUMENT: dict(supported=True, modifies_external=True, reversible=False, insurer_authority=False, sensitive=True),
    ActionType.RESUBMIT_CLAIM: dict(supported=True, modifies_external=True, reversible=False, insurer_authority=False, sensitive=True),
    ActionType.ATTACH_AND_RESUBMIT: dict(supported=True, modifies_external=True, reversible=False, insurer_authority=False, sensitive=True),
    ActionType.RAISE_FOLLOW_UP: dict(supported=True, modifies_external=True, reversible=True, insurer_authority=False, sensitive=False),
    ActionType.RESOLVE_EXTERNAL_CONFLICT: dict(supported=True, modifies_external=True, reversible=False, insurer_authority=True, sensitive=True),
    ActionType.MODIFY_DOCUMENT: dict(supported=False, modifies_external=False, reversible=False, insurer_authority=False, sensitive=True),
}


@dataclass
class GateResult:
    decision: str
    risk_class: str
    reasons: List[str] = field(default_factory=list)
    checks: List[Dict[str, Any]] = field(default_factory=list)
    prerequisites: List[Prerequisite] = field(default_factory=list)

    @property
    def can_execute(self) -> bool:
        return self.decision in {GateDecision.SAFE, GateDecision.CONFIRM} and all(p.satisfied for p in self.prerequisites)


def _check(name: str, passed: bool, detail: str) -> Dict[str, Any]:
    return {"name": name, "passed": passed, "detail": detail}


def evaluate(action_type: str, *, claim: Optional[Claim], journey: Optional[Journey], payload: Dict[str, Any]) -> GateResult:
    policy = ACTION_POLICY.get(action_type)
    checks: List[Dict[str, Any]] = []
    reasons: List[str] = []
    prerequisites: List[Prerequisite] = []

    # 1. Supported?
    if not policy or not policy["supported"]:
        checks.append(_check("supported", False, f"Action {action_type} is not supported by COVE2E."))
        return GateResult(GateDecision.DENY, RiskClass.HUMAN_ESCALATION_REQUIRED, ["Unsupported action type."], checks)
    checks.append(_check("supported", True, "Action type is supported."))

    # 2. Insurer authority?
    if policy["insurer_authority"]:
        checks.append(_check("insurer_authority", False, "This action requires a decision only the insurer can make."))
        reasons.append("Only the insurer can change decision, settlement or payment states.")
        return GateResult(GateDecision.ESCALATE, RiskClass.HUMAN_ESCALATION_REQUIRED, reasons, checks)
    checks.append(_check("insurer_authority", True, "No insurer authority required."))

    # 3. System state consistency
    if journey and journey.current_state == JourneyState.ESCALATED and action_type not in {ActionType.POLL_STATUS, ActionType.NOTIFY_USER, ActionType.ESCALATE}:
        checks.append(_check("state_consistent", False, "Journey is escalated; automated actions are paused."))
        return GateResult(GateDecision.ESCALATE, RiskClass.HUMAN_ESCALATION_REQUIRED, ["Journey is under human review."], checks)
    if claim and _external_conflict(claim) and policy["modifies_external"]:
        checks.append(_check("state_consistent", False, "External claim state is internally inconsistent."))
        return GateResult(GateDecision.ESCALATE, RiskClass.HUMAN_ESCALATION_REQUIRED, ["Conflicting external state must be resolved by a human."], checks)
    checks.append(_check("state_consistent", True, "Journey and claim state are consistent."))

    # 4. Required information available? (action-specific prerequisites)
    if action_type in {ActionType.ATTACH_DOCUMENT, ActionType.ATTACH_AND_RESUBMIT}:
        doc_type = payload.get("document_type")
        doc = _find_doc(claim, doc_type) if claim else None
        label = label_for(doc_type) if doc_type else "document"
        prerequisites.append(Prerequisite(key="document_uploaded", label=f"{label} uploaded", satisfied=doc is not None, hint=f"Upload the {label.lower()} to continue.", document_type=doc_type))
        if doc is not None:
            valid = doc.validation_status in {DocValidation.VALID, DocValidation.NEEDS_REVIEW}
            prerequisites.append(Prerequisite(key="document_valid", label=f"{label} validated", satisfied=valid, hint="; ".join(doc.issues[:2]) if not valid else "", document_type=doc_type))
            if doc.attached_to_insurer:
                checks.append(_check("not_duplicate", False, f"{label} was already sent to the insurer."))
                reasons.append(f"{label} is already attached to the external claim.")
        if claim and not claim.external_claim_id:
            checks.append(_check("external_claim_exists", False, "Claim has not been submitted to the insurer yet."))
            return GateResult(GateDecision.DENY, RiskClass.USER_CONFIRMATION_REQUIRED, ["Claim must be submitted before documents can be attached externally."], checks, prerequisites)
    elif action_type == ActionType.SUBMIT_CLAIM and claim is not None:
        readiness = compute_readiness(claim)
        missing = [i for i in readiness.items if i.status == "MISSING"]
        prerequisites.append(Prerequisite(key="required_documents", label="All required documents uploaded", satisfied=not missing, hint=("Missing: " + ", ".join(i.label.replace(" missing", "") for i in missing)) if missing else ""))
        warnings = [i for i in readiness.items if i.status == "WARNING"]
        checks.append(_check("readiness", not missing, f"Readiness {readiness.percent}% — {len(missing)} missing, {len(warnings)} warnings."))
        if claim.external_claim_id:
            checks.append(_check("not_duplicate", False, "Claim is already submitted."))
            return GateResult(GateDecision.DENY, RiskClass.USER_CONFIRMATION_REQUIRED, ["Claim has already been submitted to the insurer."], checks, prerequisites)
        if any(i.label.lower().endswith("mismatch") for i in warnings):
            prerequisites.append(Prerequisite(key="inconsistency_confirmed", label="Document inconsistencies confirmed by you", satisfied=False, hint="Confirm the correct values before submitting."))
    elif action_type == ActionType.RESUBMIT_CLAIM and claim is not None:
        open_q = [q for q in claim.queries if q.status == "OPEN"]
        unmet = [q for q in open_q if q.requested_document_type and _find_doc(claim, q.requested_document_type) is None]
        prerequisites.append(Prerequisite(key="queries_addressed", label="Insurer queries addressed", satisfied=not unmet, hint=("Upload: " + ", ".join(label_for(q.requested_document_type) for q in unmet)) if unmet else ""))
    elif action_type == ActionType.CONFIRM_DOCUMENT_VALUE:
        has_value = bool(payload.get("field")) and bool(payload.get("value"))
        prerequisites.append(Prerequisite(key="value_provided", label="Correct value provided by you", satisfied=has_value, hint="Choose which admission date is correct."))

    checks.append(_check("information_available", all(p.satisfied for p in prerequisites), "All prerequisites satisfied." if all(p.satisfied for p in prerequisites) else "Some prerequisites are not yet satisfied."))

    # 5. Reversibility / sensitivity → decision
    if not policy["modifies_external"] and not policy["sensitive"]:
        checks.append(_check("reversible", True, "Read-only or internal action; reversible."))
        return GateResult(GateDecision.SAFE, RiskClass.AUTO_RECOVERABLE, ["Read-only / internal action. Safe to execute automatically."], checks, prerequisites)

    checks.append(_check("reversible", policy["reversible"], "Reversible." if policy["reversible"] else "This action is not reversible."))
    if policy["modifies_external"]:
        reasons.append("This action modifies the external claim held by the insurer.")
    if policy["sensitive"]:
        reasons.append("This action involves your personal or medical documents.")
    if not policy["reversible"]:
        reasons.append("The action cannot be undone automatically.")
    reasons.append("Your explicit confirmation is required.")
    return GateResult(GateDecision.CONFIRM, RiskClass.USER_CONFIRMATION_REQUIRED, reasons, checks, prerequisites)


def _external_conflict(claim: Claim) -> bool:
    return claim.payment_status == "COMPLETED" and claim.settlement_status != "COMPLETED"


def _find_doc(claim: Optional[Claim], doc_type: Optional[str]):
    if not claim or not doc_type:
        return None
    for d in claim.documents:
        if d.document_type == doc_type:
            return d
    return None


def propose_action(
    db: Session,
    *,
    user: User,
    action_type: str,
    title: str,
    description: str,
    payload: Dict[str, Any],
    journey: Optional[Journey] = None,
    claim: Optional[Claim] = None,
    proposed_by: Actor | str = Actor.AI,
) -> ActionRequest:
    """Evaluate the proposal through the gate and persist it as an ActionRequest."""
    result = evaluate(action_type, claim=claim, journey=journey, payload=payload)
    status = ActionStatus.PROPOSED
    if result.decision == GateDecision.DENY:
        status = ActionStatus.DENIED
    elif result.decision == GateDecision.ESCALATE:
        status = ActionStatus.ESCALATED

    action = ActionRequest(
        user_id=user.id,
        journey_id=journey.id if journey else None,
        claim_id=claim.id if claim else None,
        action_type=action_type,
        title=title,
        description=description,
        payload=payload,
        proposed_by=str(proposed_by),
        gate_decision=result.decision,
        gate_reasons=result.reasons,
        gate_checks=result.checks,
        risk_class=result.risk_class,
        prerequisites=[p.model_dump() for p in result.prerequisites],
        status=status,
    )
    db.add(action)
    db.flush()

    record_audit(db, AuditAction.ACTION_PROPOSED, actor=proposed_by, user_id=user.id, journey_id=action.journey_id, claim_id=action.claim_id, metadata={"action_id": action.id, "action_type": action_type})
    audit_map = {
        GateDecision.SAFE: AuditAction.ACTION_GATE_APPROVED,
        GateDecision.CONFIRM: AuditAction.ACTION_GATE_APPROVED,
        GateDecision.DENY: AuditAction.ACTION_GATE_DENIED,
        GateDecision.ESCALATE: AuditAction.ACTION_GATE_ESCALATED,
    }
    record_audit(db, audit_map[result.decision], actor=Actor.SYSTEM, user_id=user.id, journey_id=action.journey_id, claim_id=action.claim_id, result=result.decision, metadata={"action_id": action.id, "risk_class": result.risk_class, "reasons": result.reasons})
    return action


def re_evaluate(db: Session, action: ActionRequest, *, claim: Optional[Claim], journey: Optional[Journey]) -> ActionRequest:
    """Re-run the gate (e.g. after the user uploads the missing document)."""
    if action.status in {ActionStatus.EXECUTED, ActionStatus.VERIFIED, ActionStatus.EXECUTING}:
        return action
    result = evaluate(action.action_type, claim=claim, journey=journey, payload=action.payload)
    action.gate_decision = result.decision
    action.gate_reasons = result.reasons
    action.gate_checks = result.checks
    action.risk_class = result.risk_class
    action.prerequisites = [p.model_dump() for p in result.prerequisites]
    if result.decision == GateDecision.DENY:
        action.status = ActionStatus.DENIED
    elif result.decision == GateDecision.ESCALATE:
        action.status = ActionStatus.ESCALATED
    elif action.status in {ActionStatus.DENIED, ActionStatus.ESCALATED}:
        action.status = ActionStatus.PROPOSED
    db.flush()
    return action


def to_proposal(action: ActionRequest) -> ActionProposal:
    prereqs = [Prerequisite(**p) for p in (action.prerequisites or [])]
    can = action.gate_decision in {GateDecision.SAFE, GateDecision.CONFIRM} and all(p.satisfied for p in prereqs) and action.status in {ActionStatus.PROPOSED, ActionStatus.APPROVED}
    return ActionProposal(
        id=action.id,
        action_type=action.action_type,
        title=action.title,
        description=action.description,
        risk_class=action.risk_class,
        gate_decision=action.gate_decision,
        gate_reasons=list(action.gate_reasons or []),
        gate_checks=list(action.gate_checks or []),
        prerequisites=prereqs,
        can_execute=can,
        status=action.status,
        payload=action.payload or {},
    )
