from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.agents import investigation_agent, recovery_agent
from app.core.database import get_db
from app.core.enums import ActionType, Actor
from app.core.security import get_current_user
from app.engines import action_gate
from app.models import Journey, User
from app.schemas.ai import ClaimReadiness, InvestigationResult, RecoveryPlan
from app.schemas.api import (
    ActionApproveResponse,
    ClaimCreateRequest,
    ClaimDetail,
    ClaimSummary,
    ClaimTracking,
    ConfirmDocumentValueRequest,
    DocumentAnalysis,
    DocumentOut,
    InvestigateRequest,
    RecoveryPlanRequest,
    SubmitClaimResponse,
    TimelineEvent,
)
from app.services import claim_service, journey_service, policy_service, workflow_executor
from app.services.document_intelligence import cross_document_issues
from app.services.readiness_service import compute_readiness

router = APIRouter(prefix="/api/claims", tags=["claims"])


def _detail(db: Session, claim) -> ClaimDetail:
    d = ClaimDetail.model_validate(claim)
    from app.models import Policy

    policy = db.get(Policy, claim.policy_id)
    d.policy = policy_service.to_summary(policy) if policy else None
    return d


@router.get("", response_model=List[ClaimSummary])
def list_claims(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return claim_service.list_claims(db, user)


@router.post("", response_model=ClaimDetail, status_code=201)
def create_claim(req: ClaimCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    claim = claim_service.create_claim(db, user, req)
    db.commit()
    db.refresh(claim)
    return _detail(db, claim)


@router.get("/{claim_id}", response_model=ClaimDetail)
def get_claim(claim_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _detail(db, claim_service.get_claim(db, user, claim_id))


@router.post("/{claim_id}/documents", response_model=DocumentAnalysis, status_code=201)
async def upload_document(claim_id: str, file: UploadFile = File(...), document_type: Optional[str] = Form(None), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    claim = claim_service.get_claim(db, user, claim_id)
    content = await file.read()
    doc = claim_service.add_document(db, user, claim, content, file.filename or "document", file.content_type or "application/octet-stream", document_type)
    db.commit()
    db.refresh(claim)
    issues = [c["message"] + " " + c["action"] for c in cross_document_issues(list(claim.documents)) if c["field"] not in (claim.user_confirmations or {})]
    return DocumentAnalysis(document=DocumentOut.model_validate(doc), cross_document_issues=issues, readiness=compute_readiness(claim))


@router.post("/{claim_id}/documents/sample", response_model=DocumentAnalysis, status_code=201)
def upload_sample_document(claim_id: str, document_type: str = Form(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Demo helper: attach a bundled sample document (e.g. the medical certificate) as if the user uploaded it."""
    from app.services.demo_service import MOCK

    path = MOCK / "documents" / f"{document_type}.txt"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No sample document for {document_type}")
    claim = claim_service.get_claim(db, user, claim_id)
    doc = claim_service.add_document(db, user, claim, path.read_bytes(), f"{document_type}.txt", "text/plain", document_type)
    db.commit()
    db.refresh(claim)
    issues = [c["message"] + " " + c["action"] for c in cross_document_issues(list(claim.documents)) if c["field"] not in (claim.user_confirmations or {})]
    return DocumentAnalysis(document=DocumentOut.model_validate(doc), cross_document_issues=issues, readiness=compute_readiness(claim))


@router.get("/{claim_id}/readiness", response_model=ClaimReadiness)
def readiness(claim_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return compute_readiness(claim_service.get_claim(db, user, claim_id))


@router.get("/{claim_id}/timeline", response_model=List[TimelineEvent])
def timeline(claim_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    claim = claim_service.get_claim(db, user, claim_id)
    journey = db.get(Journey, claim.journey_id) if claim.journey_id else None
    return journey_service.to_timeline(list(journey.events)) if journey else []


@router.get("/{claim_id}/tracking", response_model=ClaimTracking)
def tracking(claim_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    claim = claim_service.get_claim(db, user, claim_id)
    journey = db.get(Journey, claim.journey_id) if claim.journey_id else None
    return journey_service.tracking(db, claim, journey)


@router.post("/{claim_id}/submit", response_model=SubmitClaimResponse)
def prepare_submission(claim_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Proposes SUBMIT_CLAIM through the Action Gate. Execution requires /api/actions/{id}/approve + /execute."""
    claim = claim_service.get_claim(db, user, claim_id)
    if claim.external_claim_id:
        raise HTTPException(status_code=409, detail="Claim already submitted")
    action = claim_service.propose_submission(db, user, claim)
    db.commit()
    proposal = action_gate.to_proposal(action)
    r = compute_readiness(claim)
    msg = "I have prepared the submission. Confirm to send the claim to the insurer." if proposal.can_execute else ("Submission is not possible yet: " + "; ".join(p.hint for p in proposal.prerequisites if not p.satisfied and p.hint) + " " + "; ".join(proposal.gate_reasons))
    return SubmitClaimResponse(action=proposal, readiness=r, message=msg)


@router.post("/{claim_id}/investigate", response_model=InvestigationResult)
def investigate(claim_id: str, req: InvestigateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    claim = claim_service.get_claim(db, user, claim_id)
    journey = db.get(Journey, claim.journey_id)
    result = investigation_agent.run(db, user=user, journey=journey, claim=claim, message=req.message, language=req.language)
    db.commit()
    return result


@router.post("/{claim_id}/recovery-plan", response_model=RecoveryPlan)
def recovery_plan(claim_id: str, req: RecoveryPlanRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    claim = claim_service.get_claim(db, user, claim_id)
    journey = db.get(Journey, claim.journey_id)
    inv = investigation_agent.run(db, user=user, journey=journey, claim=claim, message=None, language=req.language)
    plan = recovery_agent.run(db, user=user, journey=journey, claim=claim, investigation=inv, language=req.language)
    db.commit()
    return plan


@router.post("/{claim_id}/confirm-value", response_model=ActionApproveResponse)
def confirm_value(claim_id: str, req: ConfirmDocumentValueRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Scenario B: the user confirms which document value is correct. Goes through the gate; no document is modified."""
    claim = claim_service.get_claim(db, user, claim_id)
    journey = db.get(Journey, claim.journey_id) if claim.journey_id else None
    action = action_gate.propose_action(db, user=user, journey=journey, claim=claim, action_type=ActionType.CONFIRM_DOCUMENT_VALUE, title=f"Confirm {req.field.replace('_', ' ')}", description=req.note or "User confirmed the correct value.", payload={"field": req.field, "value": req.value, "note": req.note}, proposed_by=Actor.USER)
    workflow_executor.approve(db, user=user, action=action)
    result = workflow_executor.execute(db, user=user, action=action)
    db.commit()
    return ActionApproveResponse(action=action_gate.to_proposal(action), message=result.final_message)
