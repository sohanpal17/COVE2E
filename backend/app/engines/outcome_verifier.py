"""Outcome Verifier.

n8n reporting success is never treated as proof. After every external action we
re-query the insurer, compare before/after state against the expectation, and
only then update the journey. Unchanged → REINVESTIGATE/ESCALATE. Conflict → ESCALATE.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.enums import Actor, AuditAction, JourneyState
from app.engines import journey_state_engine as jse
from app.models import Claim, Journey
from app.schemas.ai import VerificationResult
from app.services.audit_service import record_audit
from app.services.mock_insurer_service import MockInsurerService


def verify(
    db: Session,
    *,
    journey: Journey,
    claim: Claim,
    before: Optional[Dict[str, Any]],
    expectation: Dict[str, Any],
    actor: Actor | str = Actor.SYSTEM,
) -> VerificationResult:
    svc = MockInsurerService(db)
    ext = svc.get(claim.external_claim_id) if claim.external_claim_id else None
    journey_before = journey.current_state

    record_audit(db, AuditAction.EXTERNAL_STATE_CHECKED, actor=actor, user_id=journey.user_id, journey_id=journey.id, claim_id=claim.id, previous_state=(before or {}).get("status"), new_state=ext.status if ext else None)

    if ext is None:
        return VerificationResult(outcome="ERROR", before_state=(before or {}).get("status"), after_state=None, expected_state=expectation.get("status"), message="Insurer did not return a claim record. Nothing was changed.", journey_state_before=journey_before, journey_state_after=journey.current_state)

    after = svc.snapshot(ext)
    conflict = svc.has_conflict(ext)
    before_status = (before or {}).get("status")
    expected_status = expectation.get("status")

    if conflict:
        return VerificationResult(outcome="CONFLICT", before_state=before_status, after_state=after["status"], expected_state=expected_status, external_snapshot=after, message=f"Insurer state is inconsistent: {conflict}", journey_state_before=journey_before, journey_state_after=journey.current_state)

    met = _expectation_met(after, expectation, before)
    if not met:
        return VerificationResult(outcome="UNCHANGED", before_state=before_status, after_state=after["status"], expected_state=expected_status, external_snapshot=after, message=f"Insurer state is still {after['status']}; the action did not produce the expected change.", journey_state_before=journey_before, journey_state_after=journey.current_state)

    # Apply verified external state to our records.
    _sync_claim(db, claim, after)
    open_types = {q.get("requested_document_type") for q in after.get("open_queries", [])}
    for q in claim.queries:
        if q.status == "OPEN" and (q.external_query_id not in {oq.get("id") for oq in after.get("open_queries", [])}):
            q.status = "RESOLVED"
            q.resolved_at = datetime.now(timezone.utc)
    for d in claim.documents:
        if any(sd.get("document_type") == d.document_type for sd in after.get("documents", [])):
            d.attached_to_insurer = True
    from app.services.readiness_service import requirement_status_for

    requirement_status_for(claim)

    if journey.current_state == JourneyState.QUERY_RAISED and after["status"] == "UNDER_REVIEW":
        jse.transition(db, journey, JourneyState.QUERY_RESOLUTION, actor=actor, reason="Requested document delivered to insurer", external_status=after["status"])
    jse.sync_from_insurer_status(db, journey, after["status"], actor=Actor.INSURER, reason=f"Insurer state verified: {after['status']}", has_open_query=bool(open_types))

    record_audit(db, AuditAction.RECOVERY_VERIFIED, actor=actor, user_id=journey.user_id, journey_id=journey.id, claim_id=claim.id, previous_state=before_status, new_state=after["status"], metadata={"expectation": expectation})
    return VerificationResult(
        outcome="VERIFIED",
        before_state=before_status,
        after_state=after["status"],
        expected_state=expected_status,
        external_snapshot=after,
        message=f"Insurer state changed from {before_status} to {after['status']}." if before_status != after["status"] else f"Insurer confirmed the action; state remains {after['status']} as expected.",
        journey_state_before=journey_before,
        journey_state_after=journey.current_state,
    )


def _expectation_met(after: Dict[str, Any], expectation: Dict[str, Any], before: Optional[Dict[str, Any]]) -> bool:
    if "status" in expectation and after.get("status") != expectation["status"]:
        return False
    if "status_in" in expectation and after.get("status") not in expectation["status_in"]:
        return False
    if "document_type" in expectation:
        if not any(d.get("document_type") == expectation["document_type"] for d in after.get("documents", [])):
            return False
    if "history_event" in expectation:
        before_count = sum(1 for h in (before or {}).get("history", []) if h.get("event") == expectation["history_event"])
        after_count = sum(1 for h in after.get("history", []) if h.get("event") == expectation["history_event"])
        if after_count <= before_count:
            return False
    if expectation.get("exists") and not after.get("external_claim_id"):
        return False
    return True


def _sync_claim(db: Session, claim: Claim, snapshot: Dict[str, Any]) -> None:
    claim.status = snapshot["status"]
    claim.external_status = snapshot["status"]
    claim.settlement_status = snapshot.get("settlement_status", claim.settlement_status)
    claim.payment_status = snapshot.get("payment_status", claim.payment_status)
    claim.last_external_update_at = datetime.now(timezone.utc)
    db.flush()
