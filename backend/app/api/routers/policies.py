from typing import List

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.agents import policy_agent
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User
from app.schemas.api import PolicyAskRequest, PolicyAskResponse, PolicyDetail, PolicySummary
from app.services import policy_service

router = APIRouter(prefix="/api/policies", tags=["policies"])


@router.get("", response_model=List[PolicySummary])
def list_policies(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [policy_service.to_summary(p) for p in policy_service.list_policies(db, user)]


@router.post("/upload", response_model=PolicyDetail)
async def upload_policy(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    content = await file.read()
    policy = policy_service.upload_policy(db, user, content, file.filename or "policy.pdf", file.content_type or "application/octet-stream")
    return policy_service.to_detail(policy)


@router.get("/{policy_id}", response_model=PolicyDetail)
def get_policy(policy_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return policy_service.to_detail(policy_service.get_policy(db, user, policy_id))


@router.post("/{policy_id}/ask", response_model=PolicyAskResponse)
def ask_policy(policy_id: str, req: PolicyAskRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    policy = policy_service.get_policy(db, user, policy_id)
    answer = policy_agent.answer_question(db, policy, req.question, req.language)
    db.commit()
    return PolicyAskResponse(question=req.question, answer=answer, language=req.language)


@router.post("/{policy_id}/reindex", response_model=PolicySummary)
def reindex(policy_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    policy = policy_service.get_policy(db, user, policy_id)
    policy_service.index_policy(db, policy)
    db.commit()
    return policy_service.to_summary(policy)
