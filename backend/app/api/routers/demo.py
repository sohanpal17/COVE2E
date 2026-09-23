from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User
from app.schemas.api import DemoLoadResponse, UserOut
from app.services import demo_service

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/load-recovery-demo", response_model=DemoLoadResponse)
def load_recovery_demo(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[Load Recovery Demo] — resets this user's data and populates the deterministic scenario set."""
    if not get_settings().DEMO_MODE:
        raise HTTPException(status_code=403, detail="Demo loading is disabled (DEMO_MODE=false)")
    ids = demo_service.load_recovery_demo(db, user)
    return DemoLoadResponse(
        message="Demo loaded: health + motor policies, stuck claim CLM-10284 (insurer waiting for medical certificate), and four secondary scenarios.",
        user=UserOut.model_validate(user),
        policy_id=ids["policy_id"],
        claim_id=ids["claim_id"],
        journey_id=ids["journey_id"],
        claim_number=ids["claim_number"],
        scenarios=demo_service.scenario_index(db, user),
    )


@router.get("/scenarios")
def scenarios(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return demo_service.scenario_index(db, user)
