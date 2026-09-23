from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents import claim_agent
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User
from app.schemas.api import IncidentAnalyzeRequest, IncidentAnalyzeResponse
from app.services import policy_service

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.post("/analyze", response_model=IncidentAnalyzeResponse)
def analyze(req: IncidentAnalyzeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    policies = policy_service.list_policies(db, user)
    classification = claim_agent.classify_incident(db, user, req.description, policies, req.language)
    db.commit()
    return IncidentAnalyzeResponse(classification=classification, policies=[policy_service.to_summary(p) for p in policies])
