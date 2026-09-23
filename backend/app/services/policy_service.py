"""Policy service: upload, parse, persist, index in the knowledge layer, query."""
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import Actor, AuditAction
from app.integrations.document_extractor import ALLOWED_EXT, extract_text
from app.models import Policy, PolicyCondition, PolicyCoverage, User
from app.schemas.api import PolicyDetail, PolicySummary
from app.services.audit_service import record_audit
from app.services.policy_knowledge import get_policy_knowledge_service
from app.services.policy_parser import parse_policy_text, to_datetime


def list_policies(db: Session, user: User) -> List[Policy]:
    return db.query(Policy).filter(Policy.user_id == user.id).order_by(Policy.created_at).all()


def get_policy(db: Session, user: User, policy_id: str) -> Policy:
    policy = db.get(Policy, policy_id)
    if not policy or policy.user_id != user.id:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


def days_to_expiry(policy: Policy) -> Optional[int]:
    if not policy.end_date:
        return None
    end = policy.end_date if policy.end_date.tzinfo else policy.end_date.replace(tzinfo=timezone.utc)
    return (end - datetime.now(timezone.utc)).days


def to_summary(policy: Policy) -> PolicySummary:
    s = PolicySummary.model_validate(policy)
    s.days_to_expiry = days_to_expiry(policy)
    return s


def to_detail(policy: Policy) -> PolicyDetail:
    d = PolicyDetail.model_validate(policy)
    d.days_to_expiry = days_to_expiry(policy)
    return d


def save_upload(content: bytes, file_name: str) -> str:
    settings = get_settings()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    safe = f"{uuid.uuid4().hex}_{os.path.basename(file_name)}"
    path = os.path.join(settings.UPLOAD_DIR, safe)
    with open(path, "wb") as fh:
        fh.write(content)
    return path


def validate_file(file_name: str, size: int) -> None:
    settings = get_settings()
    ext = os.path.splitext(file_name.lower())[1]
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type {ext}. Allowed: {', '.join(sorted(ALLOWED_EXT))}")
    if size > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.MAX_UPLOAD_MB} MB limit")
    if size == 0:
        raise HTTPException(status_code=400, detail="Empty file")


def create_policy_from_profile(db: Session, user: User, profile: Dict[str, Any], *, text: str = "", source_file: Optional[str] = None, product_id: Optional[str] = None) -> Policy:
    policy = Policy(
        user_id=user.id,
        product_id=product_id,
        policy_number=profile.get("policy_number") or f"POL-{uuid.uuid4().hex[:8].upper()}",
        insurer=profile.get("insurer") or "Unknown insurer",
        policy_type=profile.get("policy_type", "HEALTH"),
        plan_name=profile.get("plan_name", ""),
        holder_name=profile.get("holder_name") or user.name,
        insured_members=profile.get("insured_members", []),
        sum_insured=float(profile.get("sum_insured") or 0),
        premium=float(profile.get("premium") or 0),
        start_date=to_datetime(profile.get("start_date")),
        end_date=to_datetime(profile.get("end_date")),
        deductible=float(profile.get("deductible") or 0),
        waiting_period_days=int(profile.get("waiting_period_days") or 0),
        claim_types=profile.get("claim_types", []),
        status="ACTIVE",
        source_file=source_file,
        extracted_text=text,
        structured_profile=profile,
    )
    db.add(policy)
    db.flush()
    for cov in profile.get("coverages", []):
        db.add(PolicyCoverage(policy_id=policy.id, name=cov.get("name", ""), keywords=cov.get("keywords", []), covered=cov.get("covered", "CONDITIONAL"), limit_amount=cov.get("limit_amount"), limit_text=cov.get("limit_text", ""), condition_text=cov.get("condition_text", ""), section_ref=cov.get("section_ref", "")))
    for cond in profile.get("conditions", []):
        db.add(PolicyCondition(policy_id=policy.id, kind=cond.get("kind", "CONDITION"), title=cond.get("title", ""), description=cond.get("description", ""), value=cond.get("value", ""), section_ref=cond.get("section_ref", "")))
    db.flush()
    return policy


def index_policy(db: Session, policy: Policy) -> Policy:
    svc = get_policy_knowledge_service(db)
    ok = svc.ingest_policy(policy.id, policy.extracted_text or "", policy.structured_profile or {})
    policy.knowledge_indexed = bool(ok)
    policy.knowledge_backend = svc.name if ok else "local"
    record_audit(db, AuditAction.POLICY_INDEXED, actor=Actor.SYSTEM, user_id=policy.user_id, result="OK" if ok else "FALLBACK", metadata={"policy_id": policy.id, "backend": policy.knowledge_backend})
    db.flush()
    return policy


def upload_policy(db: Session, user: User, content: bytes, file_name: str, mime_type: str) -> Policy:
    validate_file(file_name, len(content))
    text, method = extract_text(content, mime_type, file_name)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from the policy document. Please upload a text-based PDF or a .txt file.")
    profile = parse_policy_text(text)
    profile["extraction_method"] = method
    path = save_upload(content, file_name)
    policy = create_policy_from_profile(db, user, profile, text=text, source_file=path)
    record_audit(db, AuditAction.POLICY_UPLOADED, actor=Actor.USER, user_id=user.id, metadata={"policy_id": policy.id, "file": file_name, "method": method})
    index_policy(db, policy)
    db.commit()
    db.refresh(policy)
    return policy
