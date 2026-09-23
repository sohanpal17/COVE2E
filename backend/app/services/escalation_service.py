"""Human escalation packets."""
import random
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.enums import Actor, AuditAction, JourneyState, NotificationKind
from app.engines import journey_state_engine as jse
from app.models import Escalation, Journey
from app.schemas.ai import EscalationPacket
from app.services.audit_service import record_audit
from app.services.notification_service import notify


def _reference(db: Session) -> str:
    while True:
        ref = f"ESC-{random.randint(1000, 9999)}"
        if not db.query(Escalation).filter(Escalation.reference == ref).first():
            return ref


def create_escalation(
    db: Session,
    *,
    user_id: str,
    problem: str,
    evidence: List[str],
    current_state: str,
    actions_attempted: List[str],
    reason: str,
    recommended_action: str,
    journey: Optional[Journey] = None,
    claim_id: Optional[str] = None,
    priority: str = "HIGH",
    external_snapshot: Optional[Dict[str, Any]] = None,
    actor: Actor | str = Actor.SYSTEM,
) -> Escalation:
    esc = Escalation(
        user_id=user_id,
        journey_id=journey.id if journey else None,
        claim_id=claim_id or (journey.claim_id if journey else None),
        reference=_reference(db),
        problem=problem,
        evidence=evidence,
        current_state=current_state,
        actions_attempted=actions_attempted,
        reason=reason,
        recommended_action=recommended_action,
        priority=priority,
        external_snapshot=external_snapshot or {},
    )
    db.add(esc)
    db.flush()

    if journey and journey.current_state != JourneyState.ESCALATED:
        jse.transition(db, journey, JourneyState.ESCALATED, actor=actor, reason=f"Escalated to human agent ({esc.reference}): {reason}", metadata={"escalation_id": esc.id})
    elif journey:
        jse.add_event(db, journey, "ESCALATION_CREATED", description=f"Escalation {esc.reference} created", actor=actor, metadata={"escalation_id": esc.id})

    record_audit(
        db,
        AuditAction.ESCALATION_CREATED,
        actor=actor,
        user_id=user_id,
        journey_id=journey.id if journey else None,
        claim_id=esc.claim_id,
        new_state=JourneyState.ESCALATED if journey else None,
        metadata={"escalation_id": esc.id, "reference": esc.reference, "reason": reason},
    )
    notify(
        db,
        user_id,
        f"Escalated to a human agent ({esc.reference})",
        f"{problem} A human agent will review this. Reason: {reason}",
        kind=NotificationKind.WARNING,
        journey_id=journey.id if journey else None,
        claim_id=esc.claim_id,
        link=f"/escalations/{esc.id}",
    )
    return esc


def to_packet(esc: Escalation) -> EscalationPacket:
    return EscalationPacket(
        id=esc.id,
        reference=esc.reference,
        problem=esc.problem,
        evidence=list(esc.evidence or []),
        current_state=esc.current_state,
        actions_attempted=list(esc.actions_attempted or []),
        reason=esc.reason,
        recommended_action=esc.recommended_action,
        priority=esc.priority,
        status=esc.status,
        journey_id=esc.journey_id,
        claim_id=esc.claim_id,
        external_snapshot=esc.external_snapshot or {},
        created_at=esc.created_at.isoformat() if esc.created_at else None,
    )
