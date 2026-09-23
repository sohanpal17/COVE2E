from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.enums import Actor
from app.core.security import get_current_user
from app.engines.investigation_engine import fetch_external_snapshot
from app.models import Claim, Escalation, Journey, User
from app.schemas.ai import EscalationPacket
from app.schemas.api import EscalationCreateRequest
from app.services import escalation_service

router = APIRouter(prefix="/api/escalations", tags=["escalations"])


@router.get("", response_model=List[EscalationPacket])
def list_escalations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Escalation).filter(Escalation.user_id == user.id).order_by(Escalation.created_at.desc()).all()
    return [escalation_service.to_packet(e) for e in rows]


@router.get("/{escalation_id}", response_model=EscalationPacket)
def get_escalation(escalation_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    esc = db.get(Escalation, escalation_id)
    if not esc or esc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return escalation_service.to_packet(esc)


@router.post("", response_model=EscalationPacket, status_code=201)
def create_escalation(req: EscalationCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    journey = None
    claim = None
    if req.journey_id:
        journey = db.get(Journey, req.journey_id)
        if not journey or journey.user_id != user.id:
            raise HTTPException(status_code=404, detail="Journey not found")
        claim = db.get(Claim, journey.claim_id) if journey.claim_id else None
    elif req.claim_id:
        claim = db.get(Claim, req.claim_id)
        if not claim or claim.user_id != user.id:
            raise HTTPException(status_code=404, detail="Claim not found")
        journey = db.get(Journey, claim.journey_id) if claim.journey_id else None

    evidence: List[str] = []
    snapshot = fetch_external_snapshot(db, claim) if claim else None
    if snapshot:
        evidence.append(f"Insurer status {snapshot['status']}, settlement {snapshot['settlement_status']}, payment {snapshot['payment_status']}.")
    if journey and journey.last_investigation:
        evidence.extend(journey.last_investigation.get("evidence", [])[:3])
    if claim:
        open_q = [q.message for q in claim.queries if q.status == "OPEN"]
        evidence.extend(f"Open insurer query: {m}" for m in open_q)

    esc = escalation_service.create_escalation(
        db,
        user_id=user.id,
        journey=journey,
        claim_id=claim.id if claim else None,
        problem=req.problem,
        evidence=evidence or ["Raised by the user."],
        current_state=f"Journey {journey.current_state}" + (f"; insurer {claim.status}" if claim else "") if journey else "No journey",
        actions_attempted=[a for a in ([journey.last_investigation.get("next_action_label")] if journey and journey.last_investigation else []) if a],
        reason=req.reason or "User requested human review.",
        recommended_action="Review the journey, contact the insurer if needed, and respond to the customer.",
        external_snapshot=snapshot or {},
        actor=Actor.USER,
    )
    db.commit()
    return escalation_service.to_packet(esc)
