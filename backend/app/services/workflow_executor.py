"""Workflow Executor.

FastAPI (Action Gate) → n8n webhook → mock insurer → result → Outcome Verifier.

If n8n is unreachable and DEMO_MODE is enabled, the same steps run in-process
against the mock insurer and the result is clearly labelled `demo-fallback`.
In production mode the failure is returned as FAILED, never hidden.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import ActionStatus, ActionType, Actor, AuditAction, GateDecision, JourneyState, NotificationKind, RecoveryStatus
from app.engines import action_gate, journey_state_engine as jse, outcome_verifier
from app.engines.investigation_engine import fetch_external_snapshot
from app.integrations.n8n_client import N8nUnavailable, get_n8n
from app.models import ActionRequest, Claim, Journey, RecoveryAttempt, User
from app.schemas.ai import ExecutionResult, ExecutionStep, VerificationResult
from app.services import escalation_service
from app.services.audit_service import record_audit
from app.services.document_intelligence import label_for
from app.services.mock_insurer_service import MockInsurerService
from app.services.notification_service import notify

logger = logging.getLogger(__name__)

WORKFLOW_FOR_ACTION = {
    ActionType.SUBMIT_CLAIM: "claim_submission",
    ActionType.ATTACH_DOCUMENT: "document",
    ActionType.ATTACH_AND_RESUBMIT: "recovery",
    ActionType.RESUBMIT_CLAIM: "recovery",
    ActionType.POLL_STATUS: "status_polling",
    ActionType.RAISE_FOLLOW_UP: "status_polling",
    ActionType.REQUEST_DOCUMENT_FROM_USER: "notification",
    ActionType.NOTIFY_USER: "notification",
    ActionType.ESCALATE: "escalation",
}


class ExecutionError(Exception):
    pass


def approve(db: Session, *, user: User, action: ActionRequest) -> ActionRequest:
    """User confirmation. Records USER_CONFIRMED and moves the action to APPROVED."""
    claim = db.get(Claim, action.claim_id) if action.claim_id else None
    journey = db.get(Journey, action.journey_id) if action.journey_id else None
    action_gate.re_evaluate(db, action, claim=claim, journey=journey)
    if action.gate_decision not in {GateDecision.SAFE, GateDecision.CONFIRM}:
        raise ExecutionError(f"Action Gate decision is {action.gate_decision}; this action cannot be approved.")
    proposal = action_gate.to_proposal(action)
    if not proposal.can_execute:
        unmet = [p.label for p in proposal.prerequisites if not p.satisfied]
        raise ExecutionError("Prerequisites not satisfied: " + ", ".join(unmet))
    action.status = ActionStatus.APPROVED
    action.approved_at = datetime.now(timezone.utc)
    record_audit(db, AuditAction.USER_CONFIRMED, actor=Actor.USER, user_id=user.id, journey_id=action.journey_id, claim_id=action.claim_id, metadata={"action_id": action.id, "action_type": action.action_type})
    if journey:
        jse.add_event(db, journey, "USER_CONFIRMED_ACTION", description=f"You confirmed: {action.title}", actor=Actor.USER, metadata={"action_id": action.id})
    db.flush()
    return action


def execute(db: Session, *, user: User, action: ActionRequest) -> ExecutionResult:
    settings = get_settings()
    claim = db.get(Claim, action.claim_id) if action.claim_id else None
    journey = db.get(Journey, action.journey_id) if action.journey_id else None

    if action.status == ActionStatus.PROPOSED and action.gate_decision == GateDecision.SAFE:
        action.status = ActionStatus.APPROVED  # SAFE actions need no confirmation
    if action.status != ActionStatus.APPROVED:
        raise ExecutionError(f"Action is {action.status}; it must be APPROVED before execution.")

    action.status = ActionStatus.EXECUTING
    db.flush()
    before = fetch_external_snapshot(db, claim)
    payload = _build_payload(db, action, claim, journey)
    workflow = WORKFLOW_FOR_ACTION.get(action.action_type)

    steps: List[ExecutionStep] = []
    executor = "internal"
    run_id: Optional[str] = None

    try:
        if action.action_type == ActionType.CONFIRM_DOCUMENT_VALUE:
            steps = _execute_confirm_value(db, action, claim)
        elif workflow is None:
            raise ExecutionError(f"No workflow mapped for {action.action_type}")
        else:
            n8n = get_n8n()
            try:
                response = n8n.trigger(workflow, payload)
                executor = "n8n"
                run_id = response.get("run_id") or response.get("executionId")
                steps = _steps_from_n8n(response, action)
                record_audit(db, AuditAction.N8N_EXECUTED, actor=Actor.N8N, user_id=user.id, journey_id=action.journey_id, claim_id=action.claim_id, metadata={"workflow": workflow, "run_id": run_id})
            except N8nUnavailable as exc:
                if not settings.DEMO_MODE or settings.is_production:
                    raise ExecutionError(f"n8n is unavailable: {exc}") from exc
                executor = "demo-fallback"
                steps = _execute_fallback(db, action, claim, payload)
                record_audit(db, AuditAction.N8N_FALLBACK_EXECUTED, actor=Actor.SYSTEM, user_id=user.id, journey_id=action.journey_id, claim_id=action.claim_id, result="DEMO_FALLBACK", metadata={"workflow": workflow, "n8n_error": str(exc)})
    except ExecutionError as exc:
        action.status = ActionStatus.FAILED
        action.execution_result = {"error": str(exc), "executor": executor}
        _mark_recovery(db, action, RecoveryStatus.FAILED, {"error": str(exc)})
        db.flush()
        return ExecutionResult(action_id=action.id, status=action.status, executor=executor, steps=steps or [ExecutionStep(key="execute", label="Execute workflow", status="FAILED", detail=str(exc))], final_message=f"The action could not be executed: {exc}", recovery_status=RecoveryStatus.FAILED)

    action.status = ActionStatus.EXECUTED
    action.executed_at = datetime.now(timezone.utc)
    action.execution_result = {"executor": executor, "steps": [s.model_dump() for s in steps], "workflow": workflow, "run_id": run_id}
    if journey:
        jse.add_event(db, journey, "ACTION_EXECUTED", description=f"{action.title} executed via {executor}", actor=Actor.N8N if executor == "n8n" else Actor.SYSTEM, metadata={"action_id": action.id, "executor": executor})

    # ---- Post-execution handling per action type ----
    verification: Optional[VerificationResult] = None
    recovery_status: Optional[str] = None
    escalation_id: Optional[str] = None
    final_message = ""

    if claim and journey and action.action_type in {ActionType.SUBMIT_CLAIM, ActionType.ATTACH_AND_RESUBMIT, ActionType.ATTACH_DOCUMENT, ActionType.RESUBMIT_CLAIM, ActionType.POLL_STATUS, ActionType.RAISE_FOLLOW_UP}:
        if action.action_type == ActionType.SUBMIT_CLAIM:
            expectation: Dict[str, Any] = {"exists": True, "status_in": ["SUBMITTED", "DOCUMENT_PENDING", "UNDER_REVIEW"]}
        elif action.action_type in {ActionType.ATTACH_AND_RESUBMIT, ActionType.RESUBMIT_CLAIM}:
            expectation = {"status": action.payload.get("expected_status", "UNDER_REVIEW")}
        elif action.action_type == ActionType.ATTACH_DOCUMENT:
            expectation = {"document_type": action.payload.get("document_type")}
        elif action.action_type == ActionType.RAISE_FOLLOW_UP:
            expectation = {"history_event": "FOLLOW_UP"}
        else:
            expectation = {"exists": True}

        verification = outcome_verifier.verify(db, journey=journey, claim=claim, before=before, expectation=expectation, actor=Actor.SYSTEM)
        action.verification_result = verification.model_dump()

        if verification.outcome == "VERIFIED":
            action.status = ActionStatus.VERIFIED
            recovery_status = RecoveryStatus.SUCCEEDED
            _mark_recovery(db, action, RecoveryStatus.SUCCEEDED, verification.model_dump(), after_state=verification.after_state)
            final_message = _success_message(action, claim, verification)
            notify(db, user.id, "Recovery successful" if action.action_type != ActionType.SUBMIT_CLAIM else "Claim submitted", final_message, kind=NotificationKind.SUCCESS, journey_id=journey.id, claim_id=claim.id, link=f"/claims/{claim.id}/tracking")
        elif verification.outcome == "CONFLICT":
            action.status = ActionStatus.ESCALATED
            recovery_status = RecoveryStatus.ESCALATED
            esc = escalation_service.create_escalation(db, user_id=user.id, journey=journey, claim_id=claim.id, problem=f"Conflicting insurer state after executing '{action.title}'.", evidence=[verification.message], current_state=f"Insurer {verification.after_state}", actions_attempted=[action.title], reason="Outcome verification found conflicting external state.", recommended_action="Reconcile insurer systems manually.", external_snapshot=verification.external_snapshot)
            escalation_id = esc.id
            _mark_recovery(db, action, RecoveryStatus.ESCALATED, verification.model_dump(), after_state=verification.after_state)
            final_message = "The action was executed, but the insurer now reports conflicting states. I have escalated this to a human agent."
        else:
            action.status = ActionStatus.FAILED
            journey.recovery_attempt_count += 1
            if journey.recovery_attempt_count >= 2:
                recovery_status = RecoveryStatus.ESCALATED
                esc = escalation_service.create_escalation(db, user_id=user.id, journey=journey, claim_id=claim.id, problem=f"Recovery action '{action.title}' did not change the insurer state after {journey.recovery_attempt_count} attempts.", evidence=[verification.message] + (verification.external_snapshot.get("history", [])[-1:] and [str(verification.external_snapshot.get('history', [])[-1])]), current_state=f"Insurer {verification.after_state}", actions_attempted=[action.title] * journey.recovery_attempt_count, reason="Repeated recovery attempts failed.", recommended_action="Contact insurer operations to confirm receipt of documents and resume review.", external_snapshot=verification.external_snapshot)
                escalation_id = esc.id
                _mark_recovery(db, action, RecoveryStatus.ESCALATED, verification.model_dump(), after_state=verification.after_state)
                final_message = "The action ran, but the insurer state did not change. After repeated attempts I have escalated this to a human agent."
            else:
                recovery_status = RecoveryStatus.FAILED
                _mark_recovery(db, action, RecoveryStatus.FAILED, verification.model_dump(), after_state=verification.after_state)
                record_audit(db, AuditAction.RECOVERY_FAILED, actor=Actor.SYSTEM, user_id=user.id, journey_id=journey.id, claim_id=claim.id, previous_state=verification.before_state, new_state=verification.after_state)
                final_message = "The action ran, but the insurer state did not change as expected. I recommend re-investigating the journey."
    elif action.action_type == ActionType.CONFIRM_DOCUMENT_VALUE and claim:
        action.status = ActionStatus.VERIFIED
        recovery_status = RecoveryStatus.SUCCEEDED
        _mark_recovery(db, action, RecoveryStatus.SUCCEEDED, {"confirmed": action.payload})
        final_message = f"Thanks. I recorded {action.payload.get('field', 'the value').replace('_', ' ')} = {action.payload.get('value')} as confirmed by you. No document was modified and nothing was sent to the insurer."
    elif action.action_type in {ActionType.REQUEST_DOCUMENT_FROM_USER, ActionType.NOTIFY_USER} and claim:
        types = action.payload.get("document_types", [])
        msg = "Please upload: " + ", ".join(label_for(t) for t in types) if types else action.description
        notify(db, user.id, "Documents required", msg, kind=NotificationKind.ACTION_REQUIRED, journey_id=action.journey_id, claim_id=claim.id, link=f"/claims/{claim.id}/documents")
        action.status = ActionStatus.VERIFIED
        recovery_status = RecoveryStatus.AWAITING_USER
        final_message = msg
    else:
        action.status = ActionStatus.VERIFIED
        final_message = f"{action.title} completed."

    db.flush()
    return ExecutionResult(action_id=action.id, status=action.status, executor=executor, steps=steps, verification=verification, final_message=final_message, recovery_status=recovery_status, escalation_id=escalation_id, workflow_run_id=run_id)


# ---------------------------------------------------------------------------
def _build_payload(db: Session, action: ActionRequest, claim: Optional[Claim], journey: Optional[Journey]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "action_id": action.id,
        "action_type": action.action_type,
        "journey_id": journey.id if journey else None,
        "claim_id": claim.id if claim else None,
        "claim_number": claim.claim_number if claim else None,
        "external_claim_id": claim.external_claim_id if claim else None,
        **(action.payload or {}),
    }
    if claim:
        from app.models import Policy

        policy = db.get(Policy, claim.policy_id)
        payload["policy_number"] = policy.policy_number if policy else ""
        payload["product_type"] = policy.policy_type if policy else "HEALTH"
        payload["claim_type"] = claim.claim_type
        payload["claimed_amount"] = claim.claimed_amount
        docs = [{"document_id": d.id, "document_type": d.document_type, "file_name": d.file_name, "validation_status": d.validation_status} for d in claim.documents]
        if action.action_type in {ActionType.ATTACH_AND_RESUBMIT, ActionType.ATTACH_DOCUMENT}:
            docs = [d for d in docs if d["document_type"] == action.payload.get("document_type")]
        payload["documents"] = docs
    return payload


def _steps_from_n8n(response: Dict[str, Any], action: ActionRequest) -> List[ExecutionStep]:
    raw = response.get("steps")
    if isinstance(raw, list) and raw:
        out = []
        for s in raw:
            out.append(ExecutionStep(key=str(s.get("key", "step")), label=str(s.get("label", s.get("key", "Step"))), status="DONE" if s.get("status", "DONE") in {"DONE", "ok", "success", True} else "FAILED", detail=str(s.get("detail", ""))))
        return out
    return [ExecutionStep(key="n8n", label=f"n8n workflow executed ({action.action_type})", status="DONE", detail=str(response)[:200])]


def _execute_fallback(db: Session, action: ActionRequest, claim: Optional[Claim], payload: Dict[str, Any]) -> List[ExecutionStep]:
    """Runs the same deterministic steps the n8n workflow performs, in-process."""
    svc = MockInsurerService(db)
    steps: List[ExecutionStep] = []
    at = action.action_type

    if at == ActionType.SUBMIT_CLAIM and claim:
        steps.append(ExecutionStep(key="prepare", label="Preparing claim package", status="DONE", detail=f"{len(payload.get('documents', []))} documents"))
        ext = svc.create_claim(claim_number=claim.claim_number, policy_number=payload.get("policy_number", ""), product_type=payload.get("product_type", "HEALTH"), claim_type=claim.claim_type, claimed_amount=claim.claimed_amount, documents=payload.get("documents", []))
        claim.external_claim_id = ext.id
        claim.submitted_at = datetime.now(timezone.utc)
        for d in claim.documents:
            d.attached_to_insurer = True
        steps.append(ExecutionStep(key="submit", label="Submitting claim to insurer", status="DONE", detail=f"Insurer reference {ext.id}"))
        steps.append(ExecutionStep(key="status", label="Fetching insurer acknowledgement", status="DONE", detail=f"Status {ext.status}"))
    elif at in {ActionType.ATTACH_AND_RESUBMIT, ActionType.ATTACH_DOCUMENT, ActionType.RESUBMIT_CLAIM} and claim and claim.external_claim_id:
        steps.append(ExecutionStep(key="prepare", label="Preparing recovery", status="DONE"))
        docs = payload.get("documents", [])
        if at != ActionType.RESUBMIT_CLAIM:
            if not docs:
                raise ExecutionError("Document to attach was not found.")
            steps.append(ExecutionStep(key="validate", label="Validating document", status="DONE", detail=", ".join(d["file_name"] for d in docs)))
            for d in docs:
                svc.attach_document(claim.external_claim_id, {"document_type": d["document_type"], "file_name": d["file_name"], "document_id": d["document_id"]})
            steps.append(ExecutionStep(key="attach", label="Attaching document", status="DONE", detail=", ".join(label_for(d["document_type"]) for d in docs)))
        if at != ActionType.ATTACH_DOCUMENT:
            ext = svc.resubmit(claim.external_claim_id)
            steps.append(ExecutionStep(key="resubmit", label="Resubmitting claim", status="DONE", detail=f"Insurer status {ext.status}"))
    elif at == ActionType.POLL_STATUS and claim and claim.external_claim_id:
        ext = svc.get(claim.external_claim_id)
        steps.append(ExecutionStep(key="poll", label="Polling insurer status", status="DONE", detail=f"Status {ext.status if ext else 'unknown'}"))
    elif at == ActionType.RAISE_FOLLOW_UP and claim and claim.external_claim_id:
        svc.record_follow_up(claim.external_claim_id, payload.get("message", "Follow-up requested"))
        steps.append(ExecutionStep(key="follow_up", label="Raising follow-up with insurer", status="DONE"))
        ext = svc.get(claim.external_claim_id)
        steps.append(ExecutionStep(key="poll", label="Polling insurer status", status="DONE", detail=f"Status {ext.status if ext else 'unknown'}"))
    elif at in {ActionType.REQUEST_DOCUMENT_FROM_USER, ActionType.NOTIFY_USER}:
        steps.append(ExecutionStep(key="notify", label="Sending notification", status="DONE"))
    elif at == ActionType.ESCALATE:
        steps.append(ExecutionStep(key="escalate", label="Creating escalation ticket", status="DONE"))
    else:
        raise ExecutionError(f"Fallback executor does not support {at}")
    db.flush()
    return steps


def _execute_confirm_value(db: Session, action: ActionRequest, claim: Optional[Claim]) -> List[ExecutionStep]:
    if not claim:
        raise ExecutionError("Claim not found")
    field = action.payload.get("field")
    value = action.payload.get("value")
    if not field or value in (None, ""):
        raise ExecutionError("A confirmed value is required.")
    confirmations = dict(claim.user_confirmations or {})
    confirmations[field] = {"value": value, "note": action.payload.get("note", ""), "confirmed_at": datetime.now(timezone.utc).isoformat()}
    claim.user_confirmations = confirmations
    record_audit(db, AuditAction.USER_CONFIRMED_DOCUMENT_VALUE, actor=Actor.USER, user_id=claim.user_id, journey_id=claim.journey_id, claim_id=claim.id, metadata={"field": field, "value": value})
    db.flush()
    return [
        ExecutionStep(key="record", label="Recording your confirmation", status="DONE", detail=f"{field} = {value}"),
        ExecutionStep(key="readiness", label="Updating readiness", status="DONE"),
    ]


def _mark_recovery(db: Session, action: ActionRequest, status: str, result: Dict[str, Any], after_state: Optional[str] = None) -> None:
    attempt = db.query(RecoveryAttempt).filter(RecoveryAttempt.action_request_id == action.id).order_by(RecoveryAttempt.created_at.desc()).first()
    if not attempt:
        return
    attempt.status = status
    attempt.result = result
    attempt.after_state = after_state
    attempt.completed_at = datetime.now(timezone.utc)
    plan = dict(attempt.plan or {})
    steps = plan.get("steps", [])
    for s in steps:
        if s.get("status") in {"READY", "PENDING", "RUNNING"}:
            s["status"] = "DONE" if status == RecoveryStatus.SUCCEEDED else ("FAILED" if status == RecoveryStatus.FAILED else s["status"])
    plan["steps"] = steps
    attempt.plan = plan
    db.flush()


def _success_message(action: ActionRequest, claim: Claim, v: VerificationResult) -> str:
    if action.action_type == ActionType.SUBMIT_CLAIM:
        if v.after_state == "DOCUMENT_PENDING":
            return f"Claim {claim.claim_number} was submitted. The insurer has acknowledged it and raised a query for additional documents."
        return f"Claim {claim.claim_number} was submitted and the insurer has acknowledged it. Current status: {v.after_state}."
    if action.action_type in {ActionType.ATTACH_AND_RESUBMIT, ActionType.RESUBMIT_CLAIM, ActionType.ATTACH_DOCUMENT}:
        label = label_for(action.payload.get("document_type", "document")).lower()
        return f"Your claim was waiting for the {label}. The document has been submitted and the claim is now {v.after_state.replace('_', ' ').lower()}."
    if action.action_type == ActionType.RAISE_FOLLOW_UP:
        return f"A follow-up has been registered with the insurer. Current status: {v.after_state}."
    return f"Insurer status confirmed: {v.after_state}."
