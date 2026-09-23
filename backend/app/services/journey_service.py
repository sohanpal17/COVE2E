"""Journey service: tracking view, timeline, journey lookup."""
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.enums import JourneyState
from app.engines.journey_state_engine import STATE_LABELS
from app.models import Claim, Journey, JourneyEvent, User
from app.schemas.api import ClaimSummary, ClaimTracking, InsurerQueryOut, TimelineEvent, TrackingStage

S = JourneyState
STAGES = [
    ("initiated", "Claim initiated", {S.CLAIM_STARTED}),
    ("documents", "Documents submitted", {S.DOCUMENT_COLLECTION, S.READINESS_CHECK, S.SUBMISSION}),
    ("verification", "Documents verified", {S.QUERY_RAISED, S.QUERY_RESOLUTION}),
    ("review", "Under review", {S.UNDER_REVIEW}),
    ("decision", "Decision", {S.CLAIM_RESOLUTION}),
    ("resolution", "Resolution", {S.RESOLVED}),
]
ORDER = [S.POLICY_ACTIVE, S.INCIDENT_DETECTED, S.CLAIM_STARTED, S.DOCUMENT_COLLECTION, S.READINESS_CHECK, S.SUBMISSION, S.QUERY_RAISED, S.QUERY_RESOLUTION, S.UNDER_REVIEW, S.CLAIM_RESOLUTION, S.RESOLVED]


def get_journey(db: Session, user: User, journey_id: str) -> Journey:
    journey = db.get(Journey, journey_id)
    if not journey or journey.user_id != user.id:
        raise HTTPException(status_code=404, detail="Journey not found")
    return journey


def list_journeys(db: Session, user: User) -> List[Journey]:
    return db.query(Journey).filter(Journey.user_id == user.id).order_by(Journey.updated_at.desc()).all()


def to_timeline(events: List[JourneyEvent]) -> List[TimelineEvent]:
    return [TimelineEvent(id=e.id, event_type=e.event_type, from_state=e.from_state, to_state=e.to_state, actor=e.actor, description=e.description, metadata=e.meta or {}, created_at=e.created_at) for e in events]


def _stage_index(state: str) -> int:
    for i, (_, _, states) in enumerate(STAGES):
        if state in states:
            return i
    return 0


def tracking(db: Session, claim: Claim, journey: Optional[Journey]) -> ClaimTracking:
    state = journey.current_state if journey else S.CLAIM_STARTED
    open_queries = [q for q in claim.queries if q.status == "OPEN"]
    current_idx = _stage_index(state)
    stages: List[TrackingStage] = []
    for i, (key, label, _) in enumerate(STAGES):
        if state == S.ESCALATED:
            status = "DONE" if i < current_idx else ("BLOCKED" if i == current_idx else "PENDING")
        elif state == S.RESOLVED:
            status = "DONE"
        elif i < current_idx:
            status = "DONE"
        elif i == current_idx:
            status = "BLOCKED" if (state == S.QUERY_RAISED and open_queries) else "CURRENT"
        else:
            status = "PENDING"
        # Special-case: UNDER_REVIEW implies documents were verified
        if key == "verification" and state in {S.UNDER_REVIEW, S.CLAIM_RESOLUTION, S.RESOLVED}:
            status = "DONE"
        stages.append(TrackingStage(key=key, label=label, status=status))

    if state == S.QUERY_RAISED and open_queries:
        q = open_queries[0]
        what_happened = f"The insurer reviewed the submission and raised a query: \"{q.message}\""
        pending = "The insurer is waiting for the requested document."
        user_action = True
        next_step = "Upload the requested document and run recovery so it is sent to the insurer."
    elif state == S.UNDER_REVIEW:
        what_happened = "Documents were received and verified by the insurer."
        pending = "The insurer is assessing the claim."
        user_action = False
        next_step = "No action currently required. COVE2E will surface any insurer query."
    elif state == S.CLAIM_RESOLUTION:
        what_happened = f"The insurer has recorded a decision: {claim.status}."
        pending = f"Settlement: {claim.settlement_status}; payment: {claim.payment_status}."
        user_action = False
        next_step = "Wait for settlement to complete."
    elif state == S.RESOLVED:
        what_happened = "The claim has been resolved by the insurer."
        pending = "Nothing pending."
        user_action = False
        next_step = "None."
    elif state == S.ESCALATED:
        what_happened = "COVE2E detected a condition it must not resolve automatically and escalated it."
        pending = "A human agent is reviewing the escalation packet."
        user_action = False
        next_step = "Track the escalation for updates."
    elif state in {S.DOCUMENT_COLLECTION, S.READINESS_CHECK}:
        missing = [r.label for r in claim.requirements if r.required and r.status == "MISSING"]
        what_happened = "Claim created and document checklist generated."
        pending = ("Missing documents: " + ", ".join(missing)) if missing else "All required documents uploaded."
        user_action = bool(missing)
        next_step = "Upload the missing documents." if missing else "Review readiness and submit the claim."
    elif state == S.SUBMISSION:
        what_happened = "Readiness check passed and submission prepared."
        pending = "Your confirmation to submit."
        user_action = True
        next_step = "Confirm submission."
    else:
        what_happened = STATE_LABELS.get(state, state)
        pending = ""
        user_action = False
        next_step = ""

    return ClaimTracking(
        claim=ClaimSummary.model_validate(claim),
        stages=stages,
        current_state=state,
        current_state_label=STATE_LABELS.get(state, state),
        what_happened=what_happened,
        what_is_pending=pending,
        user_action_required=user_action,
        next_step=next_step,
        timeline=to_timeline(list(journey.events)) if journey else [],
        open_queries=[InsurerQueryOut.model_validate(q) for q in open_queries],
    )
