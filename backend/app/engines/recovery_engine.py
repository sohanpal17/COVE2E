"""Recovery Engine: converts an investigation blocker into a concrete recovery plan,
proposes the required action through the Action Gate, and classifies risk.

AUTO_RECOVERABLE | USER_CONFIRMATION_REQUIRED | HUMAN_ESCALATION_REQUIRED
"""
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.enums import ActionStatus, ActionType, Actor, AuditAction, Blocker, DocValidation, GateDecision, RecoveryStatus, RiskClass
from app.engines import action_gate
from app.engines.investigation_engine import BLOCKER_LABELS
from app.models import Claim, Journey, RecoveryAttempt, User
from app.schemas.ai import InvestigationResult, RecoveryPlan, RecoveryStep
from app.services import escalation_service
from app.services.audit_service import record_audit
from app.services.document_intelligence import cross_document_issues, label_for


def build_plan(db: Session, *, user: User, journey: Journey, claim: Optional[Claim], investigation: InvestigationResult) -> RecoveryPlan:
    blocker = investigation.blocker
    steps: List[RecoveryStep]
    action = None
    escalation_id: Optional[str] = None
    risk = RiskClass.USER_CONFIRMATION_REQUIRED
    status = RecoveryStatus.PLANNED
    summary = ""
    message = ""

    open_q = next((q for q in (claim.queries if claim else []) if q.status == "OPEN"), None)
    requested_type = open_q.requested_document_type if open_q else None

    if blocker in {Blocker.MISSING_REQUESTED_DOCUMENT, Blocker.REQUESTED_DOCUMENT_NOT_ATTACHED} and claim and requested_type:
        label = label_for(requested_type)
        doc = next((d for d in claim.documents if d.document_type == requested_type), None)
        uploaded = doc is not None
        valid = uploaded and doc.validation_status in {DocValidation.VALID, DocValidation.NEEDS_REVIEW}
        steps = [
            RecoveryStep(order=1, key="obtain", label=f"Obtain {label.lower()}", description=f"Upload the {label.lower()} requested by the insurer.", status="DONE" if uploaded else "PENDING_USER", actor="USER"),
            RecoveryStep(order=2, key="validate", label="Validate document", description="Check the document type, key fields and consistency with other documents.", status="DONE" if valid else ("FAILED" if uploaded else "PENDING"), actor="SYSTEM"),
            RecoveryStep(order=3, key="attach", label="Attach document to claim", description="Send the document to the insurer via the recovery workflow.", status="READY" if valid else "PENDING", actor="N8N"),
            RecoveryStep(order=4, key="resubmit", label="Resubmit claim", description="Ask the insurer to resume review.", status="PENDING", actor="N8N"),
            RecoveryStep(order=5, key="verify", label="Verify claim state", description="Re-query the insurer and confirm DOCUMENT_PENDING → UNDER_REVIEW.", status="PENDING", actor="SYSTEM"),
        ]
        payload = {"document_type": requested_type, "document_id": doc.id if doc else None, "expected_status": "UNDER_REVIEW", "query_id": open_q.external_query_id}
        action = action_gate.propose_action(db, user=user, journey=journey, claim=claim, action_type=ActionType.ATTACH_AND_RESUBMIT, title=f"Submit {label.lower()} and resubmit claim", description=f"Attach the {label.lower()} to claim {claim.claim_number} at the insurer and resubmit it for review.", payload=payload)
        risk = action.risk_class
        summary = f"The insurer is waiting for your {label.lower()}. Once it is attached and the claim is resubmitted, review should resume."
        status = RecoveryStatus.AWAITING_USER if not uploaded else RecoveryStatus.PLANNED
        message = (
            f"I found the blocker. The insurer is waiting for your {label.lower()}. I have prepared the recovery action — confirm to submit the document."
            if uploaded
            else f"I found the blocker. The insurer is waiting for your {label.lower()}. Upload it and I will prepare the recovery action for your confirmation."
        )

    elif blocker == Blocker.DOCUMENT_INCONSISTENCY and claim:
        conflicts = [c for c in cross_document_issues(list(claim.documents)) if c["field"] not in (claim.user_confirmations or {})]
        first = conflicts[0] if conflicts else {"field": "value", "values": {}, "message": ""}
        steps = [
            RecoveryStep(order=1, key="detect", label="Detect inconsistency", description=first.get("message", ""), status="DONE", actor="SYSTEM"),
            RecoveryStep(order=2, key="review", label="Review conflicting values", description="; ".join(f"{k}: {v}" for k, v in first.get("values", {}).items()), status="PENDING_USER", actor="USER"),
            RecoveryStep(order=3, key="confirm", label="Confirm the correct value", description="COVE2E will not change any document or the claim on its own.", status="PENDING_USER", actor="USER"),
            RecoveryStep(order=4, key="readiness", label="Update readiness", description="Recompute readiness with the confirmed value.", status="PENDING", actor="SYSTEM"),
        ]
        payload = {"field": first["field"], "options": first.get("values", {}), "value": None}
        action = action_gate.propose_action(db, user=user, journey=journey, claim=claim, action_type=ActionType.CONFIRM_DOCUMENT_VALUE, title=f"Confirm the correct {first['field'].replace('_', ' ')}", description="Choose which value is correct. Nothing is sent to the insurer until you confirm.", payload=payload)
        risk = RiskClass.USER_CONFIRMATION_REQUIRED
        status = RecoveryStatus.AWAITING_USER
        summary = f"Your documents disagree on the {first['field'].replace('_', ' ')}. Please confirm which is correct."
        message = f"I found a potential inconsistency: {first.get('message', '')} Please verify the correct {first['field'].replace('_', ' ')} before submission. I will not change anything on my own."

    elif blocker in {Blocker.CONFLICTING_EXTERNAL_STATE, Blocker.UNSUPPORTED_STATE}:
        steps = [
            RecoveryStep(order=1, key="detect", label="Detect conflicting state", description="; ".join(investigation.evidence[:3]), status="DONE", actor="SYSTEM"),
            RecoveryStep(order=2, key="freeze", label="Pause automated actions", description="No automated action may change decision, settlement or payment states.", status="DONE", actor="SYSTEM"),
            RecoveryStep(order=3, key="packet", label="Create escalation packet", description="Problem, evidence, state, actions attempted and recommended human action.", status="RUNNING", actor="SYSTEM"),
            RecoveryStep(order=4, key="human", label="Human agent review", description="An insurer/ops agent reconciles the systems.", status="PENDING", actor="HUMAN_AGENT"),
        ]
        payload = {"snapshot_evidence": investigation.evidence}
        action = action_gate.propose_action(db, user=user, journey=journey, claim=claim, action_type=ActionType.RESOLVE_EXTERNAL_CONFLICT, title="Reconcile conflicting insurer states", description="Requires insurer authority; cannot be executed by COVE2E.", payload=payload)
        risk = RiskClass.HUMAN_ESCALATION_REQUIRED
        existing = _open_escalation(db, journey)
        if existing is None:
            snapshot = _snapshot(db, claim)
            esc = escalation_service.create_escalation(
                db,
                user_id=user.id,
                journey=journey,
                claim_id=claim.id if claim else None,
                problem=f"Conflicting external claim state for {claim.claim_number if claim else 'journey'}: {investigation.blocker_label}.",
                evidence=investigation.evidence,
                current_state=f"Journey {journey.current_state}; insurer {investigation.external_status}",
                actions_attempted=_actions_attempted(db, journey) + ["Investigation completed", "Automated actions paused by Action Gate"],
                reason="Backend states conflict and the resolution requires insurer authority." if blocker == Blocker.CONFLICTING_EXTERNAL_STATE else "Repeated recovery attempts failed / unsupported state.",
                recommended_action="Verify payment ledger against settlement record; correct the erroneous status; confirm the final claim decision to the customer.",
                external_snapshot=snapshot or {},
            )
            escalation_id = esc.id
        else:
            escalation_id = existing.id
        steps[2].status = "DONE"
        status = RecoveryStatus.ESCALATED
        summary = "The insurer systems disagree with each other. This needs a human to reconcile; COVE2E will not guess."
        message = "The available state indicates the claim is currently blocked because the insurer's systems report conflicting states. I have created an escalation packet for a human agent instead of changing anything automatically."

    elif blocker == Blocker.MISSING_REQUIRED_DOCUMENTS and claim:
        missing = [r for r in claim.requirements if r.required and not any(d.document_type == r.document_type for d in claim.documents)]
        steps = [RecoveryStep(order=i + 1, key=f"upload_{r.document_type}", label=f"Upload {r.label.lower()}", description=r.description, status="PENDING_USER", actor="USER") for i, r in enumerate(missing)]
        steps.append(RecoveryStep(order=len(steps) + 1, key="readiness", label="Re-check readiness", description="Readiness is recomputed after every upload.", status="PENDING", actor="SYSTEM"))
        payload = {"document_types": [r.document_type for r in missing]}
        action = action_gate.propose_action(db, user=user, journey=journey, claim=claim, action_type=ActionType.REQUEST_DOCUMENT_FROM_USER, title="Request missing documents", description="Notify you about the missing documents.", payload=payload)
        risk = action.risk_class
        status = RecoveryStatus.AWAITING_USER
        summary = f"{len(missing)} required document(s) are missing before this claim can be submitted."
        message = "Your claim is not blocked by the insurer yet — it needs " + ", ".join(r.label.lower() for r in missing) + " before submission."

    elif blocker == Blocker.READY_TO_SUBMIT and claim:
        steps = [
            RecoveryStep(order=1, key="readiness", label="Final readiness check", description="All required documents present.", status="DONE", actor="SYSTEM"),
            RecoveryStep(order=2, key="submit", label="Submit claim to insurer", description="Send the claim and documents through the submission workflow.", status="READY", actor="N8N"),
            RecoveryStep(order=3, key="verify", label="Verify insurer acknowledgement", description="Confirm the insurer created the claim.", status="PENDING", actor="SYSTEM"),
        ]
        action = action_gate.propose_action(db, user=user, journey=journey, claim=claim, action_type=ActionType.SUBMIT_CLAIM, title=f"Submit claim {claim.claim_number}", description="Submit the claim to the insurer.", payload={"expected": "exists"})
        risk = action.risk_class
        summary = "Your claim appears ready for submission based on the available information."
        message = "Your claim appears ready for the next stage. Confirm to submit it to the insurer."

    elif blocker == Blocker.INSURER_DELAY and claim:
        steps = [
            RecoveryStep(order=1, key="poll", label="Check insurer status", description="Re-query the insurer for the latest state.", status="READY", actor="N8N"),
            RecoveryStep(order=2, key="follow_up", label="Raise follow-up with insurer", description="Register a follow-up request on the claim.", status="READY", actor="N8N"),
            RecoveryStep(order=3, key="verify", label="Verify acknowledgement", description="Confirm the insurer recorded the follow-up.", status="PENDING", actor="SYSTEM"),
        ]
        action = action_gate.propose_action(db, user=user, journey=journey, claim=claim, action_type=ActionType.RAISE_FOLLOW_UP, title="Raise a follow-up with the insurer", description="Ask the insurer for a status update on the delayed review.", payload={"message": f"Follow-up: claim {claim.claim_number} has had no update for {investigation.days_stuck} days.", "history_event": "FOLLOW_UP"})
        risk = action.risk_class
        summary = "The insurer has been quiet longer than expected. A follow-up can be raised."
        message = f"Your claim has had no insurer update for {investigation.days_stuck} days. I can raise a follow-up with the insurer — confirm to proceed."

    elif blocker == Blocker.AWAITING_INSURER and claim:
        steps = [
            RecoveryStep(order=1, key="poll", label="Check insurer status", description="Read-only status poll.", status="READY", actor="N8N"),
            RecoveryStep(order=2, key="update", label="Update journey", description="Sync the journey with the insurer state.", status="PENDING", actor="SYSTEM"),
        ]
        action = action_gate.propose_action(db, user=user, journey=journey, claim=claim, action_type=ActionType.POLL_STATUS, title="Check claim status with insurer", description="Read-only check; safe to run automatically.", payload={"expected": "exists"})
        risk = RiskClass.AUTO_RECOVERABLE
        summary = "No blocker. The claim is with the insurer for review."
        message = "Your claim is not stuck: it is under review with the insurer and no action is required from you right now."

    elif blocker == Blocker.ESCALATED:
        existing = _open_escalation(db, journey)
        escalation_id = existing.id if existing else None
        steps = [RecoveryStep(order=1, key="human", label="Human agent review in progress", description="Automated recovery paused.", status="RUNNING", actor="HUMAN_AGENT")]
        risk = RiskClass.HUMAN_ESCALATION_REQUIRED
        status = RecoveryStatus.ESCALATED
        summary = "A human agent is handling this journey."
        message = "This journey is already with a human agent. I will not run automated actions while they review it."

    else:  # RESOLVED / NONE
        steps = [RecoveryStep(order=1, key="none", label="No recovery needed", description=investigation.blocker_label, status="DONE", actor="SYSTEM")]
        risk = RiskClass.AUTO_RECOVERABLE
        status = RecoveryStatus.SUCCEEDED
        summary = investigation.blocker_label
        message = "No recovery is needed for this journey."

    attempt = RecoveryAttempt(
        journey_id=journey.id,
        claim_id=claim.id if claim else None,
        action_request_id=action.id if action else None,
        blocker=blocker,
        plan={"steps": [s.model_dump() for s in steps], "summary": summary, "risk_class": risk},
        status=status,
        before_state=investigation.external_status,
    )
    db.add(attempt)
    db.flush()
    record_audit(db, AuditAction.RECOVERY_PLAN_CREATED, actor=Actor.SYSTEM, user_id=user.id, journey_id=journey.id, claim_id=claim.id if claim else None, metadata={"blocker": blocker, "risk_class": risk, "recovery_attempt_id": attempt.id, "action_id": action.id if action else None})

    return RecoveryPlan(
        journey_id=journey.id,
        claim_id=claim.id if claim else None,
        recovery_attempt_id=attempt.id,
        blocker=blocker,
        blocker_label=BLOCKER_LABELS.get(blocker, blocker),
        summary=summary,
        steps=steps,
        risk_class=risk,
        action=action_gate.to_proposal(action) if action else None,
        escalation_id=escalation_id,
        status=status,
        message=message,
    )


def _open_escalation(db: Session, journey: Journey):
    from app.models import Escalation

    return db.query(Escalation).filter(Escalation.journey_id == journey.id, Escalation.status == "OPEN").first()


def _snapshot(db: Session, claim: Optional[Claim]) -> Optional[Dict[str, Any]]:
    from app.engines.investigation_engine import fetch_external_snapshot

    return fetch_external_snapshot(db, claim)


def _actions_attempted(db: Session, journey: Journey) -> List[str]:
    from app.models import ActionRequest

    actions = db.query(ActionRequest).filter(ActionRequest.journey_id == journey.id).order_by(ActionRequest.created_at).all()
    return [f"{a.title} — {a.status}" for a in actions if a.status in {ActionStatus.EXECUTED, ActionStatus.VERIFIED, ActionStatus.FAILED}]
