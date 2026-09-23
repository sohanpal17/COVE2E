from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents import investigation_agent, recovery_agent
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Claim, RecoveryAttempt, User
from app.schemas.ai import InvestigationResult, RecoveryPlan
from app.schemas.api import ClaimSummary, InvestigateRequest, JourneyDetail, JourneyOut, RecoveryAttemptOut, RecoveryPlanRequest
from app.services import journey_service

router = APIRouter(prefix="/api/journeys", tags=["journeys"])


@router.get("", response_model=List[JourneyOut])
def list_journeys(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return journey_service.list_journeys(db, user)


@router.get("/{journey_id}", response_model=JourneyDetail)
def get_journey(journey_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    journey = journey_service.get_journey(db, user, journey_id)
    detail = JourneyDetail.model_validate(journey)
    detail.timeline = journey_service.to_timeline(list(journey.events))
    if journey.claim_id:
        claim = db.get(Claim, journey.claim_id)
        detail.claim = ClaimSummary.model_validate(claim) if claim else None
    return detail


@router.get("/{journey_id}/investigation", response_model=InvestigationResult)
def get_investigation(journey_id: str, language: str = "en", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Runs (or re-runs) the investigation for this journey."""
    journey = journey_service.get_journey(db, user, journey_id)
    claim = db.get(Claim, journey.claim_id) if journey.claim_id else None
    result = investigation_agent.run(db, user=user, journey=journey, claim=claim, message=None, language=language)
    db.commit()
    return result


@router.post("/{journey_id}/investigation", response_model=InvestigationResult)
def investigate(journey_id: str, req: InvestigateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    journey = journey_service.get_journey(db, user, journey_id)
    claim = db.get(Claim, journey.claim_id) if journey.claim_id else None
    result = investigation_agent.run(db, user=user, journey=journey, claim=claim, message=req.message, language=req.language)
    db.commit()
    return result


@router.get("/{journey_id}/recovery", response_model=RecoveryPlan)
def get_recovery(journey_id: str, language: str = "en", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Investigates and builds a fresh recovery plan (idempotent with respect to the insurer)."""
    journey = journey_service.get_journey(db, user, journey_id)
    claim = db.get(Claim, journey.claim_id) if journey.claim_id else None
    inv = investigation_agent.run(db, user=user, journey=journey, claim=claim, message=None, language=language)
    plan = recovery_agent.run(db, user=user, journey=journey, claim=claim, investigation=inv, language=language)
    db.commit()
    return plan


@router.post("/{journey_id}/recovery", response_model=RecoveryPlan)
def build_recovery(journey_id: str, req: RecoveryPlanRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_recovery(journey_id, req.language, user, db)


@router.get("/{journey_id}/recovery-attempts", response_model=List[RecoveryAttemptOut])
def recovery_attempts(journey_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    journey_service.get_journey(db, user, journey_id)
    return db.query(RecoveryAttempt).filter(RecoveryAttempt.journey_id == journey_id).order_by(RecoveryAttempt.created_at.desc()).all()
