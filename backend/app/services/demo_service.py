"""Demo data: products, demo user and the deterministic recovery demo scenario set.

The primary hackathon demo must not depend on random AI output, so every state
here is constructed explicitly and pushed through the real state engine, mock
insurer and document pipeline (no shortcuts that bypass business logic).
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.enums import Actor, AuditAction, JourneyState
from app.engines import journey_state_engine as jse
from app.models import (
    ActionRequest,
    AuditLog,
    Claim,
    Escalation,
    InsuranceProduct,
    Journey,
    MockInsurerClaim,
    Notification,
    Policy,
    RecoveryAttempt,
    User,
)
from app.schemas.api import ClaimCreateRequest
from app.services import claim_service, policy_service
from app.services.audit_service import record_audit
from app.services.mock_insurer_service import MockInsurerService
from app.services.policy_parser import parse_policy_text

ROOT = Path(__file__).resolve().parents[3]
MOCK = ROOT / "mock-data"


def _read(rel: str) -> str:
    path = MOCK / rel
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


PRODUCTS = [
    dict(code="HEALTH_A", name="Suraksha Family Health Plus", insurer="Suraksha General Insurance", product_type="HEALTH", description="Family floater with strong ICU and room-rent limits and a low waiting period.", sum_insured=1_000_000, premium_annual=18_450, deductible=10_000, waiting_period_days=30, limits={"room_rent_per_day": 5000, "icu_per_day": 10000, "ambulance": 2000, "cataract_per_eye": 40000}, exclusions=["Maternity and childbirth", "Dental treatment not arising from accident", "Cosmetic surgery"], conditions=["10% co-pay above 60 years", "Proportionate deduction on higher room category", "Intimation within 48 hours of emergency admission"], network_info="7,800 network hospitals", required_documents=["Claim form", "Policy copy", "ID proof", "Hospital bill", "Discharge summary", "Medical certificate"], suitability_tags=["family", "icu", "hospitalisation", "senior parents"], min_age=18, max_age=65),
    dict(code="HEALTH_B", name="Aarogya Secure Individual", insurer="Aarogya Health Insurance", product_type="HEALTH", description="Budget individual plan with no deductible but a 20% co-payment and tighter limits.", sum_insured=500_000, premium_annual=9_200, deductible=0, waiting_period_days=30, limits={"room_rent_per_day": 3000, "icu_per_day": 6000, "ambulance": 1500, "cataract_per_eye": 25000}, exclusions=["Maternity", "Dental treatment", "Obesity treatment"], conditions=["20% co-payment on all claims", "Claims within 15 days of discharge"], network_info="4,200 network hospitals", required_documents=["Claim form", "Policy copy", "ID proof", "Hospital bill", "Discharge summary", "Medical certificate"], suitability_tags=["individual", "budget", "no deductible"], min_age=18, max_age=60),
    dict(code="MOTOR_A", name="DriveSafe Comprehensive Motor", insurer="DriveSafe General Insurance", product_type="MOTOR", description="Comprehensive own-damage + third-party cover with zero depreciation and roadside assistance.", sum_insured=650_000, premium_annual=14_900, deductible=1_000, waiting_period_days=0, limits={"personal_accident": 1_500_000, "zero_dep_claims_per_year": 2}, exclusions=["Driving under influence", "Mechanical breakdown", "Commercial use"], conditions=["Survey before repairs", "Intimation within 48 hours"], network_info="3,100 cashless garages", required_documents=["Claim form", "Policy copy", "Driving licence", "RC", "Repair estimate", "Damage photos"], suitability_tags=["comprehensive", "zero depreciation", "roadside assistance", "new car"], min_age=18, max_age=75),
    dict(code="MOTOR_B", name="RoadGuard Basic Motor", insurer="RoadGuard Insurance", product_type="MOTOR", description="Lower-premium cover without zero depreciation or roadside assistance.", sum_insured=600_000, premium_annual=9_800, deductible=2_000, waiting_period_days=0, limits={"personal_accident": 1_500_000}, exclusions=["Driving under influence", "Mechanical breakdown", "Commercial use"], conditions=["Depreciation applies on parts", "Intimation within 24 hours"], network_info="1,400 cashless garages", required_documents=["Claim form", "Policy copy", "Driving licence", "RC", "Repair estimate", "Damage photos"], suitability_tags=["budget", "older car"], min_age=18, max_age=75),
]


def ensure_products(db: Session) -> None:
    for p in PRODUCTS:
        if not db.query(InsuranceProduct).filter(InsuranceProduct.code == p["code"]).first():
            db.add(InsuranceProduct(**p))
    db.flush()


DEMO_USERS = {
    "demo": dict(email="rohan.mehta@example.com", name="Rohan Mehta", phone="+91 98XXXXXX21", preferred_language="en"),
    "demo-hi": dict(email="rohan.mehta.hi@example.com", name="Rohan Mehta", phone="+91 98XXXXXX22", preferred_language="hi"),
    "demo-mr": dict(email="rohan.mehta.mr@example.com", name="Rohan Mehta", phone="+91 98XXXXXX23", preferred_language="mr"),
}


def ensure_demo_user(db: Session, code: str = "demo") -> Optional[User]:
    spec = DEMO_USERS.get(code)
    if not spec:
        return None
    user = db.query(User).filter(User.demo_code == code).first()
    if not user:
        user = User(demo_code=code, **spec)
        db.add(user)
        db.flush()
    return user


def _wipe_user_data(db: Session, user: User) -> None:
    claims = db.query(Claim).filter(Claim.user_id == user.id).all()
    for c in claims:
        if c.external_claim_id:
            ext = db.get(MockInsurerClaim, c.external_claim_id)
            if ext:
                db.delete(ext)
    for model in (RecoveryAttempt, ActionRequest, Escalation, Notification, AuditLog):
        db.query(model).filter(model.user_id == user.id).delete(synchronize_session=False) if hasattr(model, "user_id") else None
    db.query(RecoveryAttempt).filter(RecoveryAttempt.journey_id.in_([j.id for j in db.query(Journey).filter(Journey.user_id == user.id).all()] or [""])).delete(synchronize_session=False)
    for c in claims:
        db.delete(c)
    db.flush()
    for j in db.query(Journey).filter(Journey.user_id == user.id).all():
        db.delete(j)
    for p in db.query(Policy).filter(Policy.user_id == user.id).all():
        db.delete(p)
    db.flush()


def _backdate(obj, days: float, attr: str = "created_at") -> None:
    setattr(obj, attr, datetime.now(timezone.utc) - timedelta(days=days))


def _seed_policy(db: Session, user: User, rel: str, product_code: str) -> Policy:
    text = _read(f"policies/{rel}")
    profile = parse_policy_text(text)
    product = db.query(InsuranceProduct).filter(InsuranceProduct.code == product_code).first()
    policy = policy_service.create_policy_from_profile(db, user, profile, text=text, source_file=f"mock-data/policies/{rel}", product_id=product.id if product else None)
    policy_service.index_policy(db, policy)
    return policy


def _upload(db: Session, user: User, claim: Claim, rel: str, declared: str, file_name: Optional[str] = None) -> None:
    content = _read(f"documents/{rel}").encode("utf-8")
    claim_service.add_document(db, user, claim, content, file_name or rel, "text/plain", declared)
    db.refresh(claim)


def load_recovery_demo(db: Session, user: User) -> Dict[str, str]:
    ensure_products(db)
    _wipe_user_data(db, user)
    now = datetime.now(timezone.utc)
    insurer = MockInsurerService(db)

    health = _seed_policy(db, user, "health_a.txt", "HEALTH_A")
    motor = _seed_policy(db, user, "motor_a.txt", "MOTOR_A")
    # Backdate policy creation so it looks established
    _backdate(health, 120)
    _backdate(motor, 90)

    ids: Dict[str, str] = {}

    # ---- PRIMARY: Stuck claim CLM-10284 (DOCUMENT_PENDING, medical certificate requested 3 days ago) ----
    stuck = claim_service.create_claim(db, user, ClaimCreateRequest(policy_id=health.id, claim_type="REIMBURSEMENT", incident_type="hospitalization", incident_date=now - timedelta(days=13), incident_time="21:30", incident_description="My father was hospitalized with pneumonia and needed a day in the ICU.", location="City Care Multispeciality Hospital, Pune", affected_asset="Ramesh Mehta (father)", people_involved="Ramesh Mehta", claimed_amount=67_800), scenario="STUCK_CLAIM")
    stuck.claim_number = "CLM-10284"
    db.flush()
    for rel, declared in [("policy_copy.txt", "policy_copy"), ("id_proof.txt", "id_proof"), ("claim_form.txt", "claim_form"), ("hospital_bill.txt", "hospital_bill"), ("discharge_summary.txt", "discharge_summary")]:
        _upload(db, user, stuck, rel, declared)
    journey = db.get(Journey, stuck.journey_id)
    # Submit 8 days ago through the real mock insurer (deterministically lands in DOCUMENT_PENDING).
    docs = [{"document_id": d.id, "document_type": d.document_type, "file_name": d.file_name} for d in stuck.documents]
    ext = insurer.create_claim(claim_number=stuck.claim_number, policy_number=health.policy_number, product_type="HEALTH", claim_type="REIMBURSEMENT", claimed_amount=stuck.claimed_amount, documents=docs)
    for d in stuck.documents:
        d.attached_to_insurer = True
    stuck.external_claim_id = ext.id
    stuck.submitted_at = now - timedelta(days=8)
    stuck.status = ext.status
    stuck.external_status = ext.status
    stuck.last_external_update_at = now - timedelta(days=3)
    jse.transition(db, journey, JourneyState.READINESS_CHECK, actor=Actor.SYSTEM, reason="Readiness check (demo)")
    jse.transition(db, journey, JourneyState.SUBMISSION, actor=Actor.USER, reason="You confirmed submission")
    jse.transition(db, journey, JourneyState.UNDER_REVIEW, actor=Actor.N8N, reason="Claim submitted to insurer via n8n; insurer reference " + ext.id, external_status="SUBMITTED")
    record_audit(db, AuditAction.CLAIM_SUBMITTED, actor=Actor.N8N, user_id=user.id, journey_id=journey.id, claim_id=stuck.id, new_state="SUBMITTED", metadata={"external_claim_id": ext.id})
    q = ext.queries[0]
    claim_service.record_insurer_query(db, stuck, q["message"], q.get("requested_document_type"), external_query_id=q["id"], raised_at=now - timedelta(days=3))
    # Backdate the query on the insurer side too
    ext.queries = [{**qq, "raised_at": (now - timedelta(days=3)).isoformat()} for qq in ext.queries]
    _backdate(stuck, 13)
    _backdate(journey, 13)
    # Backdate events so the timeline reads naturally
    offsets = [13, 13, 13, 12.9, 12.5, 12.4, 12.3, 12.2, 12.1, 8.1, 8, 8, 3, 3]
    for ev, off in zip(journey.events, offsets):
        _backdate(ev, off)
    ids["stuck"] = stuck.id
    ids["primary_journey"] = journey.id

    # ---- Scenario 1: Normal claim (motor, UNDER_REVIEW, all documents) ----
    normal = claim_service.create_claim(db, user, ClaimCreateRequest(policy_id=motor.id, claim_type="OWN_DAMAGE", incident_type="accident", incident_date=now - timedelta(days=20), incident_description="Car was hit while parked outside the office.", location="Baner Road, Pune", affected_asset="MH 12 AB 4321", claimed_amount=42_500), scenario="NORMAL")
    normal.claim_number = "CLM-10301"
    db.flush()
    motor_docs = {
        "claim_form": "MOTOR CLAIM FORM\nPolicy Number: DSG-MTR-2026-88213\nClaimant details: Rohan Mehta\nVehicle Number: MH 12 AB 4321\nDate of accident: 03/09/2026",
        "policy_copy": "POLICY SCHEDULE\nPolicy Number: DSG-MTR-2026-88213\nVehicle Number: MH 12 AB 4321\nInsured Declared Value: Rs. 6,50,000",
        "driving_license": "DRIVING LICENCE\nDL No: MH12 20100012345\nName: Rohan Mehta\nValid till: 13/06/2030",
        "rc_copy": "REGISTRATION CERTIFICATE\nRegn No: MH 12 AB 4321\nChassis No: MA3EYD32S00123456\nEngine No: K12MN1234567\nOwner: Rohan Mehta",
        "repair_estimate": "AUTOFIX WORKSHOP\nEstimate for MH 12 AB 4321\nRear bumper replacement - spare parts Rs. 18,500\nLabour Rs. 9,000\nPaint Rs. 15,000\nEstimate Total: Rs. 42,500",
        "damage_photos": "Damage photos: rear bumper and tail lamp (3 images)",
    }
    for dtype, text in motor_docs.items():
        claim_service.add_document(db, user, normal, text.encode("utf-8"), f"{dtype}.txt", "text/plain", dtype)
        db.refresh(normal)
    nj = db.get(Journey, normal.journey_id)
    ndocs = [{"document_id": d.id, "document_type": d.document_type, "file_name": d.file_name} for d in normal.documents]
    next_ = insurer.create_claim(claim_number=normal.claim_number, policy_number=motor.policy_number, product_type="MOTOR", claim_type="OWN_DAMAGE", claimed_amount=normal.claimed_amount, documents=ndocs)
    for d in normal.documents:
        d.attached_to_insurer = True
    normal.external_claim_id = next_.id
    normal.submitted_at = now - timedelta(days=15)
    normal.status = next_.status
    normal.external_status = next_.status
    normal.last_external_update_at = now - timedelta(days=2)
    if nj.current_state == JourneyState.DOCUMENT_COLLECTION:
        jse.transition(db, nj, JourneyState.READINESS_CHECK, actor=Actor.SYSTEM, reason="All documents uploaded")
    jse.transition(db, nj, JourneyState.SUBMISSION, actor=Actor.USER, reason="You confirmed submission")
    jse.transition(db, nj, JourneyState.UNDER_REVIEW, actor=Actor.N8N, reason="Submitted to insurer via n8n", external_status=next_.status)
    _backdate(normal, 20)
    _backdate(nj, 20)
    ids["normal"] = normal.id

    # ---- Scenario 2: Missing documents (health DRAFT) ----
    missing = claim_service.create_claim(db, user, ClaimCreateRequest(policy_id=health.id, claim_type="REIMBURSEMENT", incident_type="hospitalization", incident_date=now - timedelta(days=4), incident_description="Priya was admitted for two days for a dengue fever episode.", location="Sahyadri Hospital, Pune", affected_asset="Priya Mehta (spouse)", claimed_amount=38_200), scenario="MISSING_DOCUMENT")
    missing.claim_number = "CLM-10322"
    db.flush()
    for rel, declared in [("policy_copy.txt", "policy_copy"), ("id_proof.txt", "id_proof")]:
        _upload(db, user, missing, rel, declared)
    _backdate(missing, 4)
    ids["missing_document"] = missing.id

    # ---- Scenario 3: Document inconsistency (health DRAFT, admission dates differ) ----
    incons = claim_service.create_claim(db, user, ClaimCreateRequest(policy_id=health.id, claim_type="REIMBURSEMENT", incident_type="hospitalization", incident_date=now - timedelta(days=11), incident_description="Follow-up hospitalisation for my father; second set of documents.", location="City Care Multispeciality Hospital, Pune", affected_asset="Ramesh Mehta (father)", claimed_amount=67_800), scenario="DOCUMENT_INCONSISTENCY")
    incons.claim_number = "CLM-10345"
    db.flush()
    for rel, declared, fname in [("policy_copy.txt", "policy_copy", None), ("id_proof.txt", "id_proof", None), ("claim_form.txt", "claim_form", None), ("hospital_bill.txt", "hospital_bill", None), ("discharge_summary_mismatch.txt", "discharge_summary", "discharge_summary.txt"), ("medical_certificate.txt", "medical_certificate", None)]:
        _upload(db, user, incons, rel, declared, fname)
    _backdate(incons, 5)
    ids["document_inconsistency"] = incons.id

    # ---- Scenario 4: Conflicting external state (APPROVED / settlement PENDING / payment COMPLETED) ----
    conflict = claim_service.create_claim(db, user, ClaimCreateRequest(policy_id=health.id, claim_type="CASHLESS", incident_type="hospitalization", incident_date=now - timedelta(days=45), incident_description="Cashless cataract surgery for my father.", location="Netra Eye Hospital, Pune", affected_asset="Ramesh Mehta (father)", claimed_amount=39_500), scenario="CONFLICTING_STATE")
    conflict.claim_number = "CLM-10367"
    db.flush()
    for rel, declared in [("policy_copy.txt", "policy_copy"), ("id_proof.txt", "id_proof"), ("claim_form.txt", "claim_form"), ("medical_certificate.txt", "medical_certificate")]:
        _upload(db, user, conflict, rel, declared)
    cj = db.get(Journey, conflict.journey_id)
    cdocs = [{"document_id": d.id, "document_type": d.document_type, "file_name": d.file_name} for d in conflict.documents]
    cext = insurer.create_claim(claim_number=conflict.claim_number, policy_number=health.policy_number, product_type="HEALTH", claim_type="CASHLESS", claimed_amount=conflict.claimed_amount, documents=cdocs)
    insurer.transition(cext.id, status="APPROVED", settlement_status="PENDING", payment_status="COMPLETED", note="Demo: inconsistent downstream systems")
    for d in conflict.documents:
        d.attached_to_insurer = True
    conflict.external_claim_id = cext.id
    conflict.submitted_at = now - timedelta(days=40)
    conflict.status = "APPROVED"
    conflict.external_status = "APPROVED"
    conflict.settlement_status = "PENDING"
    conflict.payment_status = "COMPLETED"
    conflict.last_external_update_at = now - timedelta(days=1)
    if cj.current_state == JourneyState.DOCUMENT_COLLECTION:
        jse.transition(db, cj, JourneyState.READINESS_CHECK, actor=Actor.SYSTEM, reason="All documents uploaded")
    jse.transition(db, cj, JourneyState.SUBMISSION, actor=Actor.USER, reason="You confirmed submission")
    jse.transition(db, cj, JourneyState.UNDER_REVIEW, actor=Actor.N8N, reason="Submitted to insurer via n8n", external_status="UNDER_REVIEW")
    jse.transition(db, cj, JourneyState.CLAIM_RESOLUTION, actor=Actor.INSURER, reason="Insurer decision recorded: APPROVED", external_status="APPROVED")
    _backdate(conflict, 45)
    _backdate(cj, 45)
    ids["conflicting_state"] = conflict.id

    record_audit(db, AuditAction.DEMO_LOADED, actor=Actor.SYSTEM, user_id=user.id, metadata={"claims": ids})
    db.commit()
    return {
        "policy_id": health.id,
        "claim_id": stuck.id,
        "journey_id": journey.id,
        "claim_number": stuck.claim_number,
        **ids,
    }


def scenario_index(db: Session, user: User) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for c in db.query(Claim).filter(Claim.user_id == user.id).all():
        if c.scenario:
            out[c.scenario] = {"claim_id": c.id, "journey_id": c.journey_id or "", "claim_number": c.claim_number}
    return out
