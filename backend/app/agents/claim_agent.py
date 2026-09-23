"""Claim Agent: incident understanding → incident type, relevant policy, urgency,
required information and next actions. Deterministic rules first, Sarvam second."""
import re
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.agents.lang import SYSTEM_STYLE, language_instruction, localize, normalise
from app.core.enums import Actor, AuditAction
from app.integrations.sarvam_client import get_sarvam
from app.models import Policy, User
from app.schemas.ai import IncidentClassification
from app.services.audit_service import record_audit

RULES: List[Tuple[str, str, str, str, str, str]] = [
    # pattern, incident_type, label, policy_type, urgency, suggested claim type
    (r"hospital|admitted|icu|surgery|operation|fever|accident.*injur|injur|fracture|dengue|pneumonia|treatment|doctor", "hospitalization", "Hospitalisation", "HEALTH", "HIGH", "REIMBURSEMENT"),
    (r"stolen|theft|robbed|missing", "theft", "Theft", "MOTOR", "HIGH", "THIRD_PARTY"),
    (r"car|bike|vehicle|scooter|parked|hit|collision|dent|bumper|accident|crash", "accident", "Motor accident", "MOTOR", "MEDIUM", "OWN_DAMAGE"),
    (r"phone|laptop|gadget|screen|mobile", "gadget_damage", "Gadget damage / theft", "GADGET", "LOW", "GADGET"),
]

REQUIRED_INFO = {
    "hospitalization": ["Patient name and relationship", "Hospital name", "Admission date", "Discharge date (or expected)", "Diagnosis", "Cashless or reimbursement"],
    "accident": ["Date and time", "Location", "Vehicle number", "Description of damage", "Third party involved?", "FIR filed (if third party)?"],
    "theft": ["Date discovered", "Location", "FIR number", "Asset details"],
    "gadget_damage": ["Device model and IMEI", "Date of incident", "Purchase invoice", "FIR if stolen"],
}
NEXT_ACTIONS = {
    "hospitalization": ["Confirm whether the hospital is in the insurer network (cashless) or plan a reimbursement claim", "Record incident details", "Check policy coverage, waiting period and room-rent limit", "Collect discharge summary, bills and medical certificate", "Initiate the claim"],
    "accident": ["Capture photos of the damage before moving the vehicle", "Record incident details", "Check policy coverage and deductible", "Obtain a repair estimate", "Initiate the claim"],
    "theft": ["File an FIR immediately", "Record incident details", "Check policy coverage", "Prepare RC, keys and FIR copy", "Initiate the claim"],
    "gadget_damage": ["Record incident details", "Check gadget cover", "Prepare purchase invoice", "Initiate the claim"],
}


def _rule_classify(description: str) -> Tuple[str, str, str, str, str]:
    d = description.lower()
    if re.search(r"stolen|theft|robbed", d) and re.search(r"car|bike|vehicle|scooter", d):
        return "theft", "Vehicle theft", "MOTOR", "HIGH", "THIRD_PARTY"
    if re.search(r"stolen|theft", d) and re.search(r"phone|laptop|mobile", d):
        return "gadget_damage", "Gadget theft", "GADGET", "LOW", "GADGET"
    for pattern, itype, label, ptype, urgency, ctype in RULES:
        if re.search(pattern, d):
            return itype, label, ptype, urgency, ctype
    return "unknown", "Incident", "UNKNOWN", "MEDIUM", None  # type: ignore[return-value]


def _match_policy(policies: List[Policy], policy_type: str) -> Optional[Policy]:
    for p in policies:
        if p.policy_type == policy_type and p.status == "ACTIVE":
            return p
    return None


def classify_incident(db: Session, user: User, description: str, policies: List[Policy], language: str = "en") -> IncidentClassification:
    lang = normalise(language)
    itype, label, ptype, urgency, ctype = _rule_classify(description)
    policy = _match_policy(policies, ptype) if ptype != "UNKNOWN" else None
    coverage_note = ""
    if policy:
        coverage_note = f"Your {policy.policy_type.lower()} policy {policy.policy_number} ({policy.insurer}) appears relevant. Coverage will be checked against its terms before the claim is submitted."
        if policy.waiting_period_days and itype == "hospitalization":
            coverage_note += f" Note the {policy.waiting_period_days}-day initial waiting period (not applicable to accidents)."
    elif ptype != "UNKNOWN":
        coverage_note = f"No active {ptype.lower()} policy is on file. You can compare options in Insurance Discovery."

    base = IncidentClassification(
        incident_type=itype,
        incident_label=label,
        policy_type=ptype,  # type: ignore[arg-type]
        matched_policy_id=policy.id if policy else None,
        matched_policy_label=f"{policy.plan_name or policy.insurer} ({policy.policy_number})" if policy else None,
        urgency=urgency,  # type: ignore[arg-type]
        journey="CLAIM" if ptype != "UNKNOWN" else "UNDERSTAND",
        suggested_claim_type=ctype,
        required_information=REQUIRED_INFO.get(itype, ["Date", "Location", "What happened", "Asset or person affected"]),
        next_actions=NEXT_ACTIONS.get(itype, ["Record incident details", "Check policy coverage", "Prepare documents", "Initiate claim"]),
        coverage_note=coverage_note,
        confidence=0.88 if itype != "unknown" else 0.4,
        summary=f"Incident: {label}. Policy: {ptype.title() if ptype != 'UNKNOWN' else 'not determined'}. Journey: {'Claim' if ptype != 'UNKNOWN' else 'Understanding'}.",
    )

    sarvam = get_sarvam()
    if sarvam.enabled:
        system = SYSTEM_STYLE + "\nClassify the incident. Use the deterministic pre-classification unless the description clearly contradicts it. Keep matched_policy_id exactly as given. " + language_instruction(lang)
        pol_text = "\n".join(f"- id={p.id} type={p.policy_type} insurer={p.insurer} number={p.policy_number} waiting_period={p.waiting_period_days}d" for p in policies) or "(none)"
        ai = sarvam.structured(system, f"USER POLICIES:\n{pol_text}\n\nPRE-CLASSIFICATION: {base.model_dump_json()}\n\nINCIDENT: {description}", IncidentClassification)
        if ai:
            ai.matched_policy_id = base.matched_policy_id
            ai.matched_policy_label = base.matched_policy_label
            if base.confidence >= 0.85:
                ai.incident_type, ai.policy_type, ai.suggested_claim_type = base.incident_type, base.policy_type, base.suggested_claim_type
            record_audit(db, AuditAction.INCIDENT_ANALYZED, actor=Actor.AI, user_id=user.id, metadata={"incident_type": ai.incident_type, "policy_type": ai.policy_type, "source": "sarvam"})
            return ai

    if lang != "en":
        base.summary = localize(base.summary, lang)
        base.coverage_note = localize(base.coverage_note, lang)
        base.next_actions = [localize(a, lang) for a in base.next_actions]
        base.required_information = [localize(a, lang) for a in base.required_information]
    record_audit(db, AuditAction.INCIDENT_ANALYZED, actor=Actor.SYSTEM, user_id=user.id, metadata={"incident_type": base.incident_type, "policy_type": base.policy_type, "source": "deterministic"})
    return base
