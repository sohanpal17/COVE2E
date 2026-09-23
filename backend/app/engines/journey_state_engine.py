"""Deterministic journey state machine.

Every transition is validated against VALID_TRANSITIONS and produces a
JourneyEvent plus an AuditLog record. No LLM output ever reaches this module.
"""
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.enums import Actor, AuditAction, InsurerClaimStatus, JourneyHealth, JourneyState
from app.models import Journey, JourneyEvent
from app.services.audit_service import record_audit

S = JourneyState

VALID_TRANSITIONS: Dict[str, set] = {
    S.POLICY_ACTIVE: {S.INCIDENT_DETECTED, S.CLAIM_STARTED, S.ESCALATED},
    S.INCIDENT_DETECTED: {S.CLAIM_STARTED, S.POLICY_ACTIVE, S.ESCALATED},
    S.CLAIM_STARTED: {S.DOCUMENT_COLLECTION, S.ESCALATED},
    S.DOCUMENT_COLLECTION: {S.READINESS_CHECK, S.ESCALATED},
    S.READINESS_CHECK: {S.DOCUMENT_COLLECTION, S.SUBMISSION, S.ESCALATED},
    S.SUBMISSION: {S.UNDER_REVIEW, S.QUERY_RAISED, S.ESCALATED},
    S.UNDER_REVIEW: {S.QUERY_RAISED, S.CLAIM_RESOLUTION, S.RESOLVED, S.ESCALATED},
    S.QUERY_RAISED: {S.QUERY_RESOLUTION, S.ESCALATED},
    S.QUERY_RESOLUTION: {S.UNDER_REVIEW, S.QUERY_RAISED, S.ESCALATED},
    S.CLAIM_RESOLUTION: {S.RESOLVED, S.ESCALATED},
    S.RESOLVED: set(),
    S.ESCALATED: {S.UNDER_REVIEW, S.QUERY_RAISED, S.CLAIM_RESOLUTION, S.RESOLVED},
}

STATE_LABELS: Dict[str, str] = {
    S.POLICY_ACTIVE: "Policy active",
    S.INCIDENT_DETECTED: "Incident detected",
    S.CLAIM_STARTED: "Claim started",
    S.DOCUMENT_COLLECTION: "Document collection",
    S.READINESS_CHECK: "Readiness check",
    S.SUBMISSION: "Submission",
    S.UNDER_REVIEW: "Under review",
    S.QUERY_RAISED: "Document verification (insurer query raised)",
    S.QUERY_RESOLUTION: "Query resolution",
    S.CLAIM_RESOLUTION: "Claim resolution",
    S.RESOLVED: "Resolved",
    S.ESCALATED: "Escalated to human agent",
}

STATE_PROGRESS: Dict[str, int] = {
    S.POLICY_ACTIVE: 0,
    S.INCIDENT_DETECTED: 10,
    S.CLAIM_STARTED: 20,
    S.DOCUMENT_COLLECTION: 35,
    S.READINESS_CHECK: 50,
    S.SUBMISSION: 60,
    S.UNDER_REVIEW: 70,
    S.QUERY_RAISED: 65,
    S.QUERY_RESOLUTION: 68,
    S.CLAIM_RESOLUTION: 90,
    S.RESOLVED: 100,
    S.ESCALATED: 70,
}

INSURER_STATUS_TO_JOURNEY: Dict[str, str] = {
    InsurerClaimStatus.SUBMITTED: S.UNDER_REVIEW,
    InsurerClaimStatus.DOCUMENT_PENDING: S.QUERY_RAISED,
    InsurerClaimStatus.UNDER_REVIEW: S.UNDER_REVIEW,
    InsurerClaimStatus.APPROVED: S.CLAIM_RESOLUTION,
    InsurerClaimStatus.REJECTED: S.CLAIM_RESOLUTION,
    InsurerClaimStatus.SETTLED: S.RESOLVED,
}


class InvalidTransition(Exception):
    def __init__(self, from_state: str, to_state: str):
        super().__init__(f"Invalid journey transition {from_state} -> {to_state}")
        self.from_state = from_state
        self.to_state = to_state


def can_transition(from_state: str, to_state: str) -> bool:
    if from_state == to_state:
        return True
    return to_state in VALID_TRANSITIONS.get(from_state, set())


def health_for_state(state: str, has_blocker: bool = False) -> str:
    if state == S.RESOLVED:
        return JourneyHealth.COMPLETE
    if state == S.ESCALATED:
        return JourneyHealth.ESCALATED
    if state == S.QUERY_RAISED or has_blocker:
        return JourneyHealth.BLOCKED
    if state in {S.DOCUMENT_COLLECTION, S.READINESS_CHECK, S.QUERY_RESOLUTION}:
        return JourneyHealth.ATTENTION
    return JourneyHealth.HEALTHY


def add_event(
    db: Session,
    journey: Journey,
    event_type: str,
    *,
    description: str = "",
    actor: Actor | str = Actor.SYSTEM,
    from_state: Optional[str] = None,
    to_state: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> JourneyEvent:
    event = JourneyEvent(
        journey_id=journey.id,
        event_type=event_type,
        from_state=from_state,
        to_state=to_state,
        actor=str(actor),
        description=description,
        meta=metadata or {},
    )
    db.add(event)
    db.flush()
    return event


def transition(
    db: Session,
    journey: Journey,
    to_state: JourneyState | str,
    *,
    actor: Actor | str = Actor.SYSTEM,
    reason: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    external_status: Optional[str] = None,
    has_blocker: bool = False,
) -> Journey:
    to_state = str(to_state)
    from_state = journey.current_state
    if not can_transition(from_state, to_state):
        raise InvalidTransition(from_state, to_state)

    if from_state != to_state:
        journey.previous_state = from_state
        journey.current_state = to_state
        journey.progress_percent = STATE_PROGRESS.get(to_state, journey.progress_percent)
    if external_status is not None:
        journey.external_status = external_status
    journey.health = health_for_state(to_state, has_blocker)

    add_event(
        db,
        journey,
        "STATE_CHANGED" if from_state != to_state else "STATE_REAFFIRMED",
        description=reason or f"{STATE_LABELS.get(from_state, from_state)} → {STATE_LABELS.get(to_state, to_state)}",
        actor=actor,
        from_state=from_state,
        to_state=to_state,
        metadata=metadata,
    )
    record_audit(
        db,
        AuditAction.JOURNEY_UPDATED,
        actor=actor,
        user_id=journey.user_id,
        journey_id=journey.id,
        claim_id=journey.claim_id,
        previous_state=from_state,
        new_state=to_state,
        metadata={"reason": reason, **(metadata or {})},
    )
    db.flush()
    return journey


def sync_from_insurer_status(
    db: Session,
    journey: Journey,
    insurer_status: str,
    *,
    actor: Actor | str = Actor.INSURER,
    reason: str = "",
    has_open_query: bool = False,
) -> Journey:
    """Map an external insurer status onto the journey state, walking through
    intermediate states where the state machine requires it."""
    target = INSURER_STATUS_TO_JOURNEY.get(insurer_status)
    if not target:
        return journey
    current = journey.current_state
    if current == target:
        journey.external_status = insurer_status
        journey.health = health_for_state(target, has_open_query)
        db.flush()
        return journey

    # Walk through required intermediates.
    path = _path(current, target)
    for step in path:
        transition(db, journey, step, actor=actor, reason=reason or f"Insurer status {insurer_status}", external_status=insurer_status, has_blocker=has_open_query)
    return journey


def _path(from_state: str, to_state: str) -> list:
    """Breadth-first search over VALID_TRANSITIONS for the shortest legal path."""
    if can_transition(from_state, to_state):
        return [to_state]
    frontier = [[from_state]]
    seen = {from_state}
    while frontier:
        path = frontier.pop(0)
        for nxt in VALID_TRANSITIONS.get(path[-1], set()):
            if nxt in seen:
                continue
            new_path = path + [nxt]
            if nxt == to_state:
                return new_path[1:]
            seen.add(nxt)
            frontier.append(new_path)
    raise InvalidTransition(from_state, to_state)
