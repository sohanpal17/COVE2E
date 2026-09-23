"""Claim readiness = documentation/process completeness. Never a prediction of approval."""
from typing import List

from app.core.enums import DocValidation, RequirementStatus
from app.models import Claim
from app.schemas.ai import ClaimReadiness, ReadinessItem
from app.services.document_intelligence import cross_document_issues, label_for


def compute_readiness(claim: Claim) -> ClaimReadiness:
    items: List[ReadinessItem] = []
    total_points = 0
    earned = 0

    # Policy identified
    total_points += 1
    items.append(ReadinessItem(label="Policy identified", status="DONE", detail=f"Policy linked to claim {claim.claim_number}"))
    earned += 1

    # Incident details
    total_points += 1
    if claim.incident_date and claim.incident_description:
        items.append(ReadinessItem(label="Incident details recorded", status="DONE", detail=claim.incident_type.replace("_", " ").title()))
        earned += 1
    else:
        items.append(ReadinessItem(label="Incident details incomplete", status="WARNING", detail="Add the incident date and a short description."))

    docs_by_type = {d.document_type: d for d in claim.documents}
    for req in sorted(claim.requirements, key=lambda r: (not r.required, r.label)):
        weight = 1 if req.required else 0
        total_points += weight
        doc = docs_by_type.get(req.document_type)
        if doc is None:
            status = "MISSING" if req.required else "WARNING"
            src = " (requested by insurer)" if req.source == "INSURER_QUERY" else ""
            items.append(ReadinessItem(label=f"{req.label} missing{src}", status=status, detail=req.description, document_type=req.document_type))
            continue
        if doc.validation_status == DocValidation.VALID:
            items.append(ReadinessItem(label=f"{req.label} uploaded", status="DONE", detail=doc.file_name, document_type=req.document_type))
            earned += weight
        elif doc.validation_status == DocValidation.NEEDS_REVIEW:
            items.append(ReadinessItem(label=f"{req.label} needs review", status="WARNING", detail="; ".join(doc.issues[:2]) or doc.file_name, document_type=req.document_type))
            earned += weight * 0.6
        else:
            items.append(ReadinessItem(label=f"{req.label} invalid", status="WARNING", detail="; ".join(doc.issues[:2]), document_type=req.document_type))

    # Cross-document consistency
    conflicts = cross_document_issues(list(claim.documents))
    confirmations = claim.user_confirmations or {}
    for conflict in conflicts:
        total_points += 1
        if conflict["field"] in confirmations:
            items.append(ReadinessItem(label=f"{conflict['field'].replace('_', ' ').title()} confirmed by you", status="DONE", detail=f"Confirmed value: {confirmations[conflict['field']].get('value')}"))
            earned += 1
        else:
            items.append(ReadinessItem(label=f"{conflict['field'].replace('_', ' ').title()} mismatch", status="WARNING", detail=conflict["message"]))

    # Open insurer queries
    for q in claim.queries:
        if q.status == "OPEN":
            requested = q.requested_document_type
            if requested and requested in docs_by_type and not docs_by_type[requested].attached_to_insurer:
                items.append(ReadinessItem(label=f"Insurer query open: {label_for(requested)} uploaded but not yet sent", status="WARNING", detail=q.message, document_type=requested))
            elif requested and requested not in docs_by_type:
                pass  # already reported as missing requirement
            else:
                items.append(ReadinessItem(label="Insurer query open", status="WARNING", detail=q.message))

    percent = int(round(100 * earned / total_points)) if total_points else 0
    outstanding = [i for i in items if i.status != "DONE"]
    missing_required = [i for i in items if i.status == "MISSING"]
    ready = len(missing_required) == 0 and not any(c["field"] not in confirmations for c in conflicts)

    if outstanding:
        next_action = f"Resolve the {len(outstanding)} outstanding issue{'s' if len(outstanding) != 1 else ''}."
        if missing_required:
            first = missing_required[0]
            next_action = f"Upload the {first.label.replace(' missing', '').replace(' (requested by insurer)', '').lower()}." + (f" Then resolve {len(outstanding) - 1} more." if len(outstanding) > 1 else "")
    elif claim.status == "DRAFT":
        next_action = "Your claim appears ready for submission based on the available information."
    else:
        next_action = "No action required from you right now."

    return ClaimReadiness(
        claim_id=claim.id,
        percent=max(0, min(100, percent)),
        items=items,
        outstanding_count=len(outstanding),
        next_action=next_action,
        ready_to_submit=ready and claim.status == "DRAFT",
    )


def requirement_status_for(claim: Claim) -> None:
    """Recompute DocumentRequirement.status from uploaded documents (in place)."""
    docs_by_type = {d.document_type: d for d in claim.documents}
    for req in claim.requirements:
        doc = docs_by_type.get(req.document_type)
        if doc is None:
            req.status = RequirementStatus.MISSING
            req.fulfilled_by_document_id = None
        else:
            req.fulfilled_by_document_id = doc.id
            if doc.attached_to_insurer:
                req.status = RequirementStatus.SUBMITTED
            elif doc.validation_status == DocValidation.VALID:
                req.status = RequirementStatus.VALIDATED
            elif doc.validation_status == DocValidation.NEEDS_REVIEW:
                req.status = RequirementStatus.NEEDS_REVIEW
            else:
                req.status = RequirementStatus.UPLOADED
