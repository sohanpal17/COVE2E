"""Claim service: creation, document checklist, uploads, readiness, submission proposal."""
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.enums import ActionType, Actor, AuditAction, DocumentType, JourneyState, NotificationKind, RequirementSource
from app.engines import action_gate, journey_state_engine as jse
from app.integrations.document_extractor import extract_text
from app.models import ActionRequest, Claim, ClaimDocument, DocumentRequirement, Journey, Policy, User
from app.schemas.api import ClaimCreateRequest
from app.services import document_intelligence as di
from app.services.audit_service import record_audit
from app.services.notification_service import notify
from app.services.policy_service import save_upload, validate_file
from app.services.readiness_service import compute_readiness, requirement_status_for

CHECKLIST: Dict[str, Dict[str, List[str]]] = {
    "HEALTH": {
        "REIMBURSEMENT": [DocumentType.CLAIM_FORM, DocumentType.POLICY_COPY, DocumentType.ID_PROOF, DocumentType.HOSPITAL_BILL, DocumentType.DISCHARGE_SUMMARY, DocumentType.MEDICAL_CERTIFICATE],
        "CASHLESS": [DocumentType.CLAIM_FORM, DocumentType.POLICY_COPY, DocumentType.ID_PROOF, DocumentType.MEDICAL_CERTIFICATE],
    },
    "MOTOR": {
        "OWN_DAMAGE": [DocumentType.CLAIM_FORM, DocumentType.POLICY_COPY, DocumentType.DRIVING_LICENSE, DocumentType.RC_COPY, DocumentType.REPAIR_ESTIMATE, DocumentType.DAMAGE_PHOTOS],
        "THIRD_PARTY": [DocumentType.CLAIM_FORM, DocumentType.POLICY_COPY, DocumentType.DRIVING_LICENSE, DocumentType.RC_COPY, DocumentType.FIR_COPY],
    },
    "GADGET": {"GADGET": [DocumentType.CLAIM_FORM, DocumentType.POLICY_COPY, DocumentType.PURCHASE_INVOICE, DocumentType.FIR_COPY]},
}
OPTIONAL_BY_INCIDENT: Dict[str, List[str]] = {
    "hospitalization": [DocumentType.PRESCRIPTION, DocumentType.DIAGNOSTIC_REPORT],
    "accident": [DocumentType.FIR_COPY],
    "theft": [DocumentType.FIR_COPY],
}


def next_claim_number(db: Session) -> str:
    while True:
        number = f"CLM-{random.randint(10000, 99999)}"
        if not db.query(Claim).filter(Claim.claim_number == number).first():
            return number


def get_claim(db: Session, user: User, claim_id: str) -> Claim:
    claim = db.get(Claim, claim_id)
    if not claim or claim.user_id != user.id:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


def list_claims(db: Session, user: User) -> List[Claim]:
    return db.query(Claim).filter(Claim.user_id == user.id).order_by(Claim.created_at.desc()).all()


def build_checklist(db: Session, claim: Claim, policy: Policy) -> None:
    required = CHECKLIST.get(policy.policy_type, {}).get(claim.claim_type)
    if required is None:
        required = next(iter(CHECKLIST.get(policy.policy_type, {"_": [DocumentType.CLAIM_FORM, DocumentType.POLICY_COPY]}).values()))
    existing = {r.document_type for r in claim.requirements}
    for doc_type in required:
        if doc_type in existing:
            continue
        db.add(DocumentRequirement(claim_id=claim.id, document_type=doc_type, label=di.label_for(doc_type), description=di.DOC_DESCRIPTIONS.get(doc_type, ""), required=True, source=RequirementSource.CLAIM_TYPE))
        existing.add(doc_type)
    for doc_type in OPTIONAL_BY_INCIDENT.get(claim.incident_type, []):
        if doc_type in existing:
            continue
        db.add(DocumentRequirement(claim_id=claim.id, document_type=doc_type, label=di.label_for(doc_type), description=di.DOC_DESCRIPTIONS.get(doc_type, ""), required=False, source=RequirementSource.INCIDENT))
        existing.add(doc_type)
    # Policy-specific required documents from the knowledge profile
    for title in (policy.structured_profile or {}).get("required_documents", []):
        mapped = _map_policy_doc(title)
        if mapped and mapped not in existing:
            db.add(DocumentRequirement(claim_id=claim.id, document_type=mapped, label=di.label_for(mapped), description=title, required=True, source=RequirementSource.POLICY))
            existing.add(mapped)
    db.flush()


def _map_policy_doc(title: str) -> Optional[str]:
    t = title.lower()
    for doc_type, hints in di._FILENAME_HINTS:
        if any(h.strip("._") in t for h in hints if len(h.strip("._")) > 2):
            return doc_type
    return None


def create_claim(db: Session, user: User, req: ClaimCreateRequest, *, scenario: str = "") -> Claim:
    policy = db.get(Policy, req.policy_id)
    if not policy or policy.user_id != user.id:
        raise HTTPException(status_code=404, detail="Policy not found")
    journey = Journey(user_id=user.id, policy_id=policy.id, journey_type="CLAIM", title=f"{policy.policy_type.title()} claim", current_state=JourneyState.POLICY_ACTIVE, health="HEALTHY", progress_percent=0)
    db.add(journey)
    db.flush()
    claim = Claim(
        user_id=user.id,
        policy_id=policy.id,
        journey_id=journey.id,
        claim_number=next_claim_number(db),
        claim_type=req.claim_type,
        incident_type=req.incident_type,
        incident_date=req.incident_date,
        incident_time=req.incident_time,
        incident_description=req.incident_description,
        location=req.location,
        affected_asset=req.affected_asset,
        people_involved=req.people_involved,
        claimed_amount=req.claimed_amount,
        status="DRAFT",
        scenario=scenario,
    )
    db.add(claim)
    db.flush()
    journey.claim_id = claim.id
    journey.title = f"{policy.policy_type.title()} claim {claim.claim_number}"
    jse.add_event(db, journey, "JOURNEY_CREATED", description="Journey created from policy", actor=Actor.SYSTEM)
    jse.transition(db, journey, JourneyState.INCIDENT_DETECTED, actor=Actor.USER, reason=f"Incident reported: {req.incident_type.replace('_', ' ')}")
    jse.transition(db, journey, JourneyState.CLAIM_STARTED, actor=Actor.SYSTEM, reason=f"Claim {claim.claim_number} created ({req.claim_type})")
    build_checklist(db, claim, policy)
    db.refresh(claim)
    jse.transition(db, journey, JourneyState.DOCUMENT_COLLECTION, actor=Actor.SYSTEM, reason=f"Checklist generated: {len(claim.requirements)} documents")
    journey.outstanding_requirements = [r.label for r in claim.requirements if r.required]
    record_audit(db, AuditAction.CLAIM_CREATED, actor=Actor.USER, user_id=user.id, journey_id=journey.id, claim_id=claim.id, new_state=claim.status, metadata={"claim_number": claim.claim_number})
    db.flush()
    return claim


def add_document(db: Session, user: User, claim: Claim, content: bytes, file_name: str, mime_type: str, declared_type: Optional[str]) -> ClaimDocument:
    validate_file(file_name, len(content))
    text, method = extract_text(content, mime_type, file_name)
    analysis = di.analyse(text, file_name, declared_type, method)
    path = save_upload(content, file_name)
    doc_type = analysis["document_type"]
    # Replace an existing document of the same type
    for existing in list(claim.documents):
        if existing.document_type == doc_type:
            db.delete(existing)
    db.flush()
    doc = ClaimDocument(
        claim_id=claim.id,
        user_id=user.id,
        document_type=doc_type,
        file_name=file_name,
        file_path=path,
        mime_type=mime_type,
        size_bytes=len(content),
        extracted_text=text[:20000],
        extracted_fields=analysis["fields"],
        classification_confidence=analysis["confidence"],
        validation_status=analysis["validation_status"],
        issues=analysis["issues"],
    )
    db.add(doc)
    db.flush()
    db.refresh(claim)
    requirement_status_for(claim)
    record_audit(db, AuditAction.DOCUMENT_UPLOADED, actor=Actor.USER, user_id=user.id, journey_id=claim.journey_id, claim_id=claim.id, metadata={"document_type": doc_type, "file": file_name})
    record_audit(db, AuditAction.DOCUMENT_VALIDATED, actor=Actor.SYSTEM, user_id=user.id, journey_id=claim.journey_id, claim_id=claim.id, result=doc.validation_status, metadata={"issues": doc.issues})

    journey = db.get(Journey, claim.journey_id) if claim.journey_id else None
    if journey:
        jse.add_event(db, journey, "DOCUMENT_UPLOADED", description=f"{di.label_for(doc_type)} uploaded ({doc.validation_status.lower().replace('_', ' ')})", actor=Actor.USER, metadata={"document_id": doc.id, "document_type": doc_type})
        readiness = compute_readiness(claim)
        journey.outstanding_requirements = [i.label for i in readiness.items if i.status != "DONE"]
        if journey.current_state == JourneyState.DOCUMENT_COLLECTION and not any(i.status == "MISSING" for i in readiness.items):
            jse.transition(db, journey, JourneyState.READINESS_CHECK, actor=Actor.SYSTEM, reason="All required documents uploaded")
        elif journey.current_state == JourneyState.READINESS_CHECK and any(i.status == "MISSING" for i in readiness.items):
            jse.transition(db, journey, JourneyState.DOCUMENT_COLLECTION, actor=Actor.SYSTEM, reason="A required document is missing again")
        # Re-evaluate pending actions that were waiting for this document
        for action in db.query(ActionRequest).filter(ActionRequest.claim_id == claim.id, ActionRequest.status.in_(["PROPOSED", "DENIED"])).all():
            action_gate.re_evaluate(db, action, claim=claim, journey=journey)
    db.flush()
    return doc


def propose_submission(db: Session, user: User, claim: Claim) -> ActionRequest:
    journey = db.get(Journey, claim.journey_id)
    action = action_gate.propose_action(db, user=user, journey=journey, claim=claim, action_type=ActionType.SUBMIT_CLAIM, title=f"Submit claim {claim.claim_number} to insurer", description="Send the claim and all uploaded documents to the insurer through the submission workflow.", payload={"expected": "exists"}, proposed_by=Actor.USER)
    if journey and journey.current_state in {JourneyState.DOCUMENT_COLLECTION, JourneyState.READINESS_CHECK} and action.gate_decision in {"SAFE", "CONFIRM"} and action_gate.to_proposal(action).can_execute:
        if journey.current_state == JourneyState.DOCUMENT_COLLECTION:
            jse.transition(db, journey, JourneyState.READINESS_CHECK, actor=Actor.SYSTEM, reason="Readiness check passed")
        jse.transition(db, journey, JourneyState.SUBMISSION, actor=Actor.SYSTEM, reason="Submission prepared; awaiting your confirmation")
    record_audit(db, AuditAction.READINESS_COMPUTED, actor=Actor.SYSTEM, user_id=user.id, journey_id=claim.journey_id, claim_id=claim.id, metadata={"percent": compute_readiness(claim).percent})
    db.flush()
    return action


def record_insurer_query(db: Session, claim: Claim, message: str, requested_document_type: Optional[str], external_query_id: Optional[str] = None, raised_at: Optional[datetime] = None) -> None:
    from app.models import InsurerQuery

    q = InsurerQuery(claim_id=claim.id, external_query_id=external_query_id, message=message, requested_document_type=requested_document_type, status="OPEN", raised_at=raised_at or datetime.now(timezone.utc))
    db.add(q)
    if requested_document_type and not any(r.document_type == requested_document_type for r in claim.requirements):
        db.add(DocumentRequirement(claim_id=claim.id, document_type=requested_document_type, label=di.label_for(requested_document_type), description=message, required=True, source=RequirementSource.INSURER_QUERY))
    db.flush()
    db.refresh(claim)
    requirement_status_for(claim)
    journey = db.get(Journey, claim.journey_id) if claim.journey_id else None
    if journey:
        jse.add_event(db, journey, "INSURER_QUERY_RAISED", description=f"Insurer query: {message}", actor=Actor.INSURER, metadata={"requested_document_type": requested_document_type})
        if journey.current_state != JourneyState.QUERY_RAISED:
            jse.sync_from_insurer_status(db, journey, "DOCUMENT_PENDING", actor=Actor.INSURER, reason="Insurer requested additional document", has_open_query=True)
    record_audit(db, AuditAction.INSURER_QUERY_RECEIVED, actor=Actor.INSURER, user_id=claim.user_id, journey_id=claim.journey_id, claim_id=claim.id, metadata={"message": message, "document_type": requested_document_type})
    notify(db, claim.user_id, "Insurer requested a document", message, kind=NotificationKind.ACTION_REQUIRED, journey_id=claim.journey_id, claim_id=claim.id, link=f"/claims/{claim.id}/documents")
