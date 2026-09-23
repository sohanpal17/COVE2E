"""Mock insurer HTTP API (called by n8n workflows and available for demo control).

Mutating endpoints require the X-COVE2E-Secret header unless DEMO_MODE is on.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import verify_n8n_secret
from app.models import Claim, Journey
from app.services import claim_service
from app.services.mock_insurer_service import MockInsurerService

router = APIRouter(prefix="/mock-insurer", tags=["mock-insurer"])


def _auth(secret: Optional[str]) -> None:
    settings = get_settings()
    if settings.DEMO_MODE and not settings.is_production:
        return
    if not verify_n8n_secret(secret):
        raise HTTPException(status_code=401, detail="Invalid workflow secret")


class CreateClaimBody(BaseModel):
    claim_number: str
    policy_number: str = ""
    product_type: str = "HEALTH"
    claim_type: str = "REIMBURSEMENT"
    claimed_amount: float = 0
    documents: List[Dict[str, Any]] = Field(default_factory=list)
    external_claim_id: Optional[str] = None


class DocumentBody(BaseModel):
    document_type: str
    file_name: str = ""
    document_id: Optional[str] = None


class QueryBody(BaseModel):
    message: str
    requested_document_type: Optional[str] = None
    direction: str = "INSURER"  # INSURER = insurer asks the customer; USER = customer follow-up


class TransitionBody(BaseModel):
    status: Optional[str] = None
    settlement_status: Optional[str] = None
    payment_status: Optional[str] = None
    note: str = ""


@router.get("/claims/{claim_id}")
def get_claim(claim_id: str, db: Session = Depends(get_db)):
    svc = MockInsurerService(db)
    ext = svc.get(claim_id)
    if not ext:
        raise HTTPException(status_code=404, detail="Claim not found at insurer")
    snap = svc.snapshot(ext)
    snap["conflict"] = svc.has_conflict(ext)
    return snap


@router.post("/claims", status_code=201)
def create_claim(body: CreateClaimBody, db: Session = Depends(get_db), x_cove2e_secret: Optional[str] = Header(None)):
    _auth(x_cove2e_secret)
    svc = MockInsurerService(db)
    ext = svc.create_claim(claim_number=body.claim_number, policy_number=body.policy_number, product_type=body.product_type, claim_type=body.claim_type, claimed_amount=body.claimed_amount, documents=body.documents, external_id=body.external_claim_id)
    # Mirror the external reference into the COVE2E claim (n8n path)
    claim = db.query(Claim).filter(Claim.claim_number == body.claim_number).first()
    if claim and not claim.external_claim_id:
        from datetime import datetime, timezone

        claim.external_claim_id = ext.id
        claim.submitted_at = datetime.now(timezone.utc)
        for d in claim.documents:
            d.attached_to_insurer = True
    db.commit()
    return svc.snapshot(ext)


@router.post("/claims/{claim_id}/documents")
def attach_document(claim_id: str, body: DocumentBody, db: Session = Depends(get_db), x_cove2e_secret: Optional[str] = Header(None)):
    _auth(x_cove2e_secret)
    svc = MockInsurerService(db)
    try:
        ext = svc.attach_document(claim_id, body.model_dump())
    except KeyError:
        raise HTTPException(status_code=404, detail="Claim not found at insurer")
    db.commit()
    return svc.snapshot(ext)


@router.post("/claims/{claim_id}/resubmit")
def resubmit(claim_id: str, db: Session = Depends(get_db), x_cove2e_secret: Optional[str] = Header(None)):
    _auth(x_cove2e_secret)
    svc = MockInsurerService(db)
    try:
        ext = svc.resubmit(claim_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Claim not found at insurer")
    db.commit()
    return svc.snapshot(ext)


@router.post("/claims/{claim_id}/query")
def query(claim_id: str, body: QueryBody, db: Session = Depends(get_db), x_cove2e_secret: Optional[str] = Header(None)):
    _auth(x_cove2e_secret)
    svc = MockInsurerService(db)
    try:
        if body.direction.upper() == "USER":
            ext = svc.record_follow_up(claim_id, body.message)
        else:
            ext = svc.raise_query(claim_id, body.message, body.requested_document_type)
            # Mirror the insurer query into the COVE2E claim and journey
            claim = db.query(Claim).filter(Claim.external_claim_id == claim_id).first()
            if claim:
                claim.status = ext.status
                claim.external_status = ext.status
                claim_service.record_insurer_query(db, claim, body.message, body.requested_document_type, external_query_id=ext.queries[-1]["id"])
    except KeyError:
        raise HTTPException(status_code=404, detail="Claim not found at insurer")
    db.commit()
    return svc.snapshot(ext)


@router.post("/claims/{claim_id}/transition")
def transition(claim_id: str, body: TransitionBody, db: Session = Depends(get_db), x_cove2e_secret: Optional[str] = Header(None)):
    """Demo control: put the insurer-side claim into any deterministic state (e.g. the conflicting-state scenario)."""
    _auth(x_cove2e_secret)
    svc = MockInsurerService(db)
    try:
        ext = svc.transition(claim_id, body.status, body.settlement_status, body.payment_status, body.note)
    except KeyError:
        raise HTTPException(status_code=404, detail="Claim not found at insurer")
    claim = db.query(Claim).filter(Claim.external_claim_id == claim_id).first()
    if claim:
        claim.status = ext.status
        claim.external_status = ext.status
        claim.settlement_status = ext.settlement_status
        claim.payment_status = ext.payment_status
        journey = db.get(Journey, claim.journey_id) if claim.journey_id else None
        if journey:
            from app.core.enums import Actor
            from app.engines import journey_state_engine as jse

            jse.add_event(db, journey, "INSURER_STATUS_CHANGED", description=f"Insurer status: {ext.status} (settlement {ext.settlement_status}, payment {ext.payment_status})", actor=Actor.INSURER)
            if not svc.has_conflict(ext):
                jse.sync_from_insurer_status(db, journey, ext.status, actor=Actor.INSURER, reason=body.note or "Insurer status update", has_open_query=bool([q for q in ext.queries if q.get("status") == "OPEN"]))
    db.commit()
    snap = svc.snapshot(ext)
    snap["conflict"] = svc.has_conflict(ext)
    return snap
