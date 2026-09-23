from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.lang import localize
from app.core.database import get_db
from app.core.security import get_current_user
from app.engines import action_gate
from app.models import ActionRequest, User
from app.schemas.ai import ActionProposal, ExecutionResult
from app.schemas.api import ActionApproveResponse, ActionExecuteRequest
from app.services import workflow_executor

router = APIRouter(prefix="/api/actions", tags=["actions"])


def _get(db: Session, user: User, action_id: str) -> ActionRequest:
    action = db.get(ActionRequest, action_id)
    if not action or action.user_id != user.id:
        raise HTTPException(status_code=404, detail="Action not found")
    return action


@router.get("", response_model=List[ActionProposal])
def list_actions(journey_id: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(ActionRequest).filter(ActionRequest.user_id == user.id)
    if journey_id:
        q = q.filter(ActionRequest.journey_id == journey_id)
    return [action_gate.to_proposal(a) for a in q.order_by(ActionRequest.created_at.desc()).limit(50).all()]


@router.get("/{action_id}", response_model=ActionProposal)
def get_action(action_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    action = _get(db, user, action_id)
    from app.models import Claim, Journey

    action_gate.re_evaluate(db, action, claim=db.get(Claim, action.claim_id) if action.claim_id else None, journey=db.get(Journey, action.journey_id) if action.journey_id else None)
    db.commit()
    return action_gate.to_proposal(action)


@router.post("/{action_id}/approve", response_model=ActionApproveResponse)
def approve(action_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """User confirmation (the [Confirm Recovery] button)."""
    action = _get(db, user, action_id)
    try:
        workflow_executor.approve(db, user=user, action=action)
    except workflow_executor.ExecutionError as exc:
        db.commit()
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return ActionApproveResponse(action=action_gate.to_proposal(action), message="Confirmed. The action is approved for execution.")


@router.post("/{action_id}/execute", response_model=ExecutionResult)
def execute(action_id: str, req: ActionExecuteRequest | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Executes an APPROVED (or SAFE) action via n8n, then verifies the outcome against the insurer."""
    action = _get(db, user, action_id)
    try:
        result = workflow_executor.execute(db, user=user, action=action)
    except workflow_executor.ExecutionError as exc:
        db.commit()
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    lang = (req.language if req else None) or "en"
    if lang != "en":
        result.final_message = localize(result.final_message, lang)
    return result
