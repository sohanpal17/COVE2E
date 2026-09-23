"""Journey Investigation Engine.

Deterministically inspects policy, claim state, documents, insurer queries,
timeline, previous actions and external insurer state, then identifies the
root-cause blocker with evidence. The LLM may later *explain* this result in
natural language but never changes it.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.enums import ActionType, Blocker, DocValidation, InsurerClaimStatus, JourneyState
from app.engines.journey_state_engine import STATE_LABELS
from app.models import ActionRequest, Claim, Journey, Policy, RecoveryAttempt
from app.schemas.ai import InvestigationCheck, InvestigationResult
from app.services.document_intelligence import cross_document_issues, label_for
from app.services.mock_insurer_service import MockInsurerService

BLOCKER_LABELS: Dict[str, str] = {
    Blocker.NONE: "No blocker",
    Blocker.MISSING_REQUESTED_DOCUMENT: "Required document requested by insurer is missing",
    Blocker.REQUESTED_DOCUMENT_NOT_ATTACHED: "Requested document uploaded but not yet sent to insurer",
    Blocker.MISSING_REQUIRED_DOCUMENTS: "Required documents missing before submission",
    Blocker.DOCUMENT_INCONSISTENCY: "Documents contain inconsistent information",
    Blocker.CONFLICTING_EXTERNAL_STATE: "Insurer systems report conflicting claim states",
    Blocker.INSURER_DELAY: "No update from insurer beyond the expected review window",
    Blocker.READY_TO_SUBMIT: "Claim is ready but has not been submitted",
    Blocker.AWAITING_INSURER: "Waiting for insurer review (no action required)",
    Blocker.ESCALATED: "Journey is with a human agent",
    Blocker.RESOLVED: "Journey is resolved",
    Blocker.UNSUPPORTED_STATE: "Unsupported journey state",
}

NEXT_ACTION_LABELS: Dict[str, str] = {
    "collect_document": "Obtain and upload the requested document, then submit it to the insurer.",
    "attach_and_resubmit": "Send the uploaded document to the insurer and resubmit the claim.",
    "upload_missing_documents": "Upload the missing required documents.",
    "confirm_correct_value": "Confirm which value is correct before anything is sent to the insurer.",
    "escalate_to_human": "A human agent must reconcile the conflicting insurer states.",
    "raise_follow_up": "Raise a follow-up with the insurer and poll the status.",
    "submit_claim": "Submit the claim to the insurer.",
    "wait": "No action needed right now; COVE2E will keep checking.",
    "none": "No action needed.",
}

REVIEW_SLA_DAYS = 7


def _days_between(a: Optional[datetime], b: Optional[datetime]) -> Optional[int]:
    if not a or not b:
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return max(0, (b - a).days)


def _ok(name: str, label: str, finding: str) -> InvestigationCheck:
    return InvestigationCheck(name=name, label=label, status="OK", finding=finding)


def _issue(name: str, label: str, finding: str) -> InvestigationCheck:
    return InvestigationCheck(name=name, label=label, status="ISSUE", finding=finding)


def _info(name: str, label: str, finding: str) -> InvestigationCheck:
    return InvestigationCheck(name=name, label=label, status="INFO", finding=finding)


def fetch_external_snapshot(db: Session, claim: Optional[Claim]) -> Optional[Dict[str, Any]]:
    if not claim or not claim.external_claim_id:
        return None
    svc = MockInsurerService(db)
    ext = svc.get(claim.external_claim_id)
    if not ext:
        return None
    snap = svc.snapshot(ext)
    snap["conflict"] = svc.has_conflict(ext)
    return snap


def investigate(db: Session, journey: Journey, claim: Optional[Claim], *, user_message: Optional[str] = None) -> InvestigationResult:
    now = datetime.now(timezone.utc)
    checks: List[InvestigationCheck] = []
    evidence: List[str] = []

    # 1. Policy
    policy: Optional[Policy] = db.get(Policy, journey.policy_id) if journey.policy_id else None
    if policy:
        checks.append(_ok("policy", "Policy", f"{policy.policy_type.title()} policy {policy.policy_number} ({policy.insurer}) is {policy.status.lower()}."))
    else:
        checks.append(_issue("policy", "Policy", "No policy linked to this journey."))

    # 2. Claim state + external
    snapshot = fetch_external_snapshot(db, claim)
    external_status = snapshot["status"] if snapshot else (claim.external_status if claim else None)
    if claim:
        state_text = f"Internal status {claim.status}"
        if external_status:
            state_text += f"; insurer reports {external_status}"
        if claim.status != (external_status or claim.status):
            checks.append(_issue("claim_state", "Claim state", state_text + " (mismatch — synchronising)."))
            claim.status = external_status
            claim.external_status = external_status
        else:
            checks.append(_ok("claim_state", "Claim state", state_text + "."))
    else:
        checks.append(_info("claim_state", "Claim state", "No claim has been created for this journey yet."))

    # 3. Documents
    conflicts: List[Dict[str, Any]] = []
    missing_required: List[str] = []
    needs_review: List[str] = []
    if claim:
        docs_by_type = {d.document_type: d for d in claim.documents}
        for req in claim.requirements:
            if req.required and req.document_type not in docs_by_type:
                missing_required.append(req.document_type)
        for d in claim.documents:
            if d.validation_status == DocValidation.NEEDS_REVIEW:
                needs_review.append(d.document_type)
        conflicts = [c for c in cross_document_issues(list(claim.documents)) if c["field"] not in (claim.user_confirmations or {})]
        parts = [f"{len(claim.documents)} uploaded"]
        if missing_required:
            parts.append(f"missing: {', '.join(label_for(m) for m in missing_required)}")
        if conflicts:
            parts.append(f"{len(conflicts)} cross-document inconsistenc{'y' if len(conflicts) == 1 else 'ies'}")
        finding = "; ".join(parts) + "."
        checks.append(_issue("documents", "Documents", finding) if (missing_required or conflicts) else _ok("documents", "Documents", finding))

    # 4. Insurer query
    open_queries = [q for q in claim.queries if q.status == "OPEN"] if claim else []
    if snapshot:
        # Reconcile: insurer-side open queries not yet mirrored locally
        local_ids = {q.external_query_id for q in claim.queries}
        for q in snapshot.get("open_queries", []):
            if q.get("id") not in local_ids:
                from app.models import InsurerQuery

                iq = InsurerQuery(claim_id=claim.id, external_query_id=q.get("id"), message=q.get("message", ""), requested_document_type=q.get("requested_document_type"), status="OPEN")
                db.add(iq)
                claim.queries.append(iq)
                open_queries.append(iq)
    if open_queries:
        q = open_queries[0]
        days_ago = _days_between(q.raised_at, now)
        when = f"{days_ago} day{'s' if days_ago != 1 else ''} ago" if days_ago is not None else "recently"
        checks.append(_issue("insurer_query", "Insurer query", f"Insurer raised a query {when}: \"{q.message}\""))
        evidence.append(f"Insurer requested {label_for(q.requested_document_type) if q.requested_document_type else 'additional information'} {when}.")
    elif claim and claim.external_claim_id:
        checks.append(_ok("insurer_query", "Insurer query", "No open insurer queries."))
    else:
        checks.append(_info("insurer_query", "Insurer query", "Claim not yet with insurer."))

    # 5. Timeline
    events = list(journey.events)
    last_event = events[-1] if events else None
    last_external = claim.last_external_update_at if claim else None
    days_since_external = _days_between(last_external, now) if last_external else None
    days_since_event = _days_between(last_event.created_at, now) if last_event else None
    days_stuck = days_since_external if days_since_external is not None else days_since_event
    tl_text = f"{len(events)} events. Current state: {STATE_LABELS.get(journey.current_state, journey.current_state)}."
    if days_since_external is not None:
        tl_text += f" Last insurer update {days_since_external} day{'s' if days_since_external != 1 else ''} ago."
    checks.append(_info("timeline", "Timeline", tl_text))

    # 6. Previous actions
    prior_actions = db.query(ActionRequest).filter(ActionRequest.journey_id == journey.id).order_by(ActionRequest.created_at.desc()).all()
    prior_recoveries = db.query(RecoveryAttempt).filter(RecoveryAttempt.journey_id == journey.id).order_by(RecoveryAttempt.created_at.desc()).all()
    executed = [a for a in prior_actions if a.status in {"EXECUTED", "VERIFIED"}]
    failed = [r for r in prior_recoveries if r.status in {"FAILED", "ESCALATED"}]
    pa_text = f"{len(prior_actions)} proposed action(s), {len(executed)} executed, {len(failed)} failed recovery attempt(s)."
    checks.append(_issue("previous_actions", "Previous actions", pa_text) if failed else _info("previous_actions", "Previous actions", pa_text))
    if failed:
        evidence.append(f"{len(failed)} earlier recovery attempt(s) did not change the insurer state.")

    # 7. External state consistency
    conflict_msg = snapshot.get("conflict") if snapshot else None
    if snapshot:
        ext_text = f"status={snapshot['status']}, settlement={snapshot['settlement_status']}, payment={snapshot['payment_status']}."
        checks.append(_issue("external_state", "External insurer state", ext_text + f" Conflict: {conflict_msg}") if conflict_msg else _ok("external_state", "External insurer state", ext_text))
    else:
        checks.append(_info("external_state", "External insurer state", "Not available (claim not submitted)."))

    # ---- Decide the blocker (priority order) ----
    blocker, next_action, affected, confidence, needs_confirm, needs_escalate = _decide(
        journey, claim, open_queries, missing_required, conflicts, conflict_msg, days_stuck, failed, external_status
    )

    # Evidence enrichment
    if blocker in {Blocker.MISSING_REQUESTED_DOCUMENT, Blocker.REQUESTED_DOCUMENT_NOT_ATTACHED} and open_queries:
        doc_type = open_queries[0].requested_document_type
        if doc_type:
            has_doc = claim and any(d.document_type == doc_type for d in claim.documents)
            if has_doc:
                evidence.append(f"{label_for(doc_type)} is uploaded in COVE2E but has not been sent to the insurer.")
            else:
                evidence.append(f"{label_for(doc_type)} not found in uploaded documents.")
        evidence.append(f"Insurer status is {external_status}; the claim cannot progress until the query is answered.")
    elif blocker == Blocker.DOCUMENT_INCONSISTENCY:
        for c in conflicts:
            evidence.append(c["message"])
    elif blocker == Blocker.CONFLICTING_EXTERNAL_STATE and snapshot:
        evidence.append(f"Claim status: {snapshot['status']}.")
        evidence.append(f"Settlement status: {snapshot['settlement_status']}.")
        evidence.append(f"Payment status: {snapshot['payment_status']}.")
        evidence.append(str(conflict_msg))
    elif blocker == Blocker.MISSING_REQUIRED_DOCUMENTS:
        evidence.append("Missing required documents: " + ", ".join(label_for(m) for m in missing_required) + ".")
    elif blocker == Blocker.INSURER_DELAY:
        evidence.append(f"No insurer update for {days_stuck} days (expected review window {REVIEW_SLA_DAYS} days).")
    elif blocker == Blocker.AWAITING_INSURER:
        evidence.append(f"Claim is under review with the insurer; last update {days_stuck if days_stuck is not None else 0} day(s) ago, within the expected window.")
    elif blocker == Blocker.READY_TO_SUBMIT:
        evidence.append("All required documents are uploaded and validated; the claim has not been sent to the insurer.")
    elif blocker == Blocker.ESCALATED:
        evidence.append("A human agent is reviewing this journey. Automated recovery is paused.")
    elif blocker == Blocker.RESOLVED:
        evidence.append("The insurer has closed this claim.")
    if not evidence:
        evidence.append("No blocking condition detected from the available data.")

    return InvestigationResult(
        journey_id=journey.id,
        claim_id=claim.id if claim else None,
        current_state=journey.current_state,
        current_state_label=STATE_LABELS.get(journey.current_state, journey.current_state),
        external_status=external_status,
        blocker=blocker,
        blocker_label=BLOCKER_LABELS[blocker],
        evidence=evidence,
        affected_step=affected,
        next_action=next_action,
        next_action_label=NEXT_ACTION_LABELS[next_action],
        confidence=confidence,
        requires_confirmation=needs_confirm,
        requires_escalation=needs_escalate,
        checks=checks,
        days_stuck=days_stuck,
    )


def _decide(
    journey: Journey,
    claim: Optional[Claim],
    open_queries: list,
    missing_required: List[str],
    conflicts: List[Dict[str, Any]],
    conflict_msg: Optional[str],
    days_stuck: Optional[int],
    failed: list,
    external_status: Optional[str],
) -> Tuple[str, str, str, float, bool, bool]:
    """Returns (blocker, next_action, affected_step, confidence, requires_confirmation, requires_escalation)."""
    if conflict_msg:
        return Blocker.CONFLICTING_EXTERNAL_STATE, "escalate_to_human", "Claim resolution", 0.97, False, True
    if journey.current_state == JourneyState.ESCALATED:
        return Blocker.ESCALATED, "none", "Human review", 0.99, False, False
    if journey.current_state == JourneyState.RESOLVED or external_status == InsurerClaimStatus.SETTLED:
        return Blocker.RESOLVED, "none", "Resolution", 0.99, False, False
    if len(failed) >= 2:
        return Blocker.UNSUPPORTED_STATE, "escalate_to_human", "Recovery", 0.9, False, True

    if open_queries and claim:
        q = open_queries[0]
        doc_type = q.requested_document_type
        if doc_type:
            doc = next((d for d in claim.documents if d.document_type == doc_type), None)
            if doc is None:
                return Blocker.MISSING_REQUESTED_DOCUMENT, "collect_document", "Document verification", 0.94, True, False
            if not doc.attached_to_insurer:
                return Blocker.REQUESTED_DOCUMENT_NOT_ATTACHED, "attach_and_resubmit", "Document verification", 0.95, True, False
        return Blocker.INSURER_DELAY, "raise_follow_up", "Query resolution", 0.8, True, False

    if claim and claim.status == "DRAFT":
        if conflicts:
            return Blocker.DOCUMENT_INCONSISTENCY, "confirm_correct_value", "Document collection", 0.92, True, False
        if missing_required:
            return Blocker.MISSING_REQUIRED_DOCUMENTS, "upload_missing_documents", "Document collection", 0.93, False, False
        return Blocker.READY_TO_SUBMIT, "submit_claim", "Submission", 0.9, True, False

    if claim and claim.external_claim_id:
        if conflicts:
            return Blocker.DOCUMENT_INCONSISTENCY, "confirm_correct_value", "Document verification", 0.88, True, False
        if external_status in {InsurerClaimStatus.APPROVED, InsurerClaimStatus.REJECTED}:
            return Blocker.AWAITING_INSURER, "wait", "Claim resolution", 0.9, False, False
        if days_stuck is not None and days_stuck > REVIEW_SLA_DAYS:
            return Blocker.INSURER_DELAY, "raise_follow_up", "Under review", 0.82, True, False
        return Blocker.AWAITING_INSURER, "wait", "Under review", 0.9, False, False

    if not claim:
        return Blocker.NONE, "none", "Policy", 0.7, False, False
    return Blocker.UNSUPPORTED_STATE, "escalate_to_human", journey.current_state, 0.5, False, True
