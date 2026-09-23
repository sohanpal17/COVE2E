"""Document Intelligence: classification, key-value extraction, validation and
cross-document consistency checks. Deterministic (regex + keyword rules) so the
demo never depends on random model output. Never concludes a claim is invalid —
only surfaces issues for the user to verify."""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.core.enums import DocValidation, DocumentType
from app.models import ClaimDocument

DOC_LABELS: Dict[str, str] = {
    DocumentType.POLICY_COPY: "Policy copy",
    DocumentType.ID_PROOF: "Identity proof",
    DocumentType.CLAIM_FORM: "Claim form",
    DocumentType.HOSPITAL_BILL: "Hospital bill",
    DocumentType.DISCHARGE_SUMMARY: "Discharge summary",
    DocumentType.MEDICAL_CERTIFICATE: "Medical certificate",
    DocumentType.PRESCRIPTION: "Prescription",
    DocumentType.DIAGNOSTIC_REPORT: "Diagnostic report",
    DocumentType.DRIVING_LICENSE: "Driving license",
    DocumentType.RC_COPY: "Registration certificate (RC)",
    DocumentType.FIR_COPY: "FIR / police report",
    DocumentType.REPAIR_ESTIMATE: "Repair estimate",
    DocumentType.DAMAGE_PHOTOS: "Damage photos",
    DocumentType.PURCHASE_INVOICE: "Purchase invoice",
    DocumentType.OTHER: "Other document",
}

DOC_DESCRIPTIONS: Dict[str, str] = {
    DocumentType.POLICY_COPY: "Copy of the policy schedule showing policy number and insured members.",
    DocumentType.ID_PROOF: "Government identity proof of the policyholder (Aadhaar, PAN or passport).",
    DocumentType.CLAIM_FORM: "Signed insurer claim form (Part A by insured, Part B by hospital where applicable).",
    DocumentType.HOSPITAL_BILL: "Itemised final hospital bill with payment receipts.",
    DocumentType.DISCHARGE_SUMMARY: "Discharge summary issued by the hospital with admission and discharge dates.",
    DocumentType.MEDICAL_CERTIFICATE: "Certificate from the treating doctor confirming diagnosis and treatment.",
    DocumentType.PRESCRIPTION: "Doctor's prescription for medicines and investigations.",
    DocumentType.DIAGNOSTIC_REPORT: "Lab / imaging reports supporting the diagnosis.",
    DocumentType.DRIVING_LICENSE: "Valid driving license of the driver at the time of the incident.",
    DocumentType.RC_COPY: "Vehicle registration certificate.",
    DocumentType.FIR_COPY: "FIR or police report (required for theft and third-party incidents).",
    DocumentType.REPAIR_ESTIMATE: "Repair estimate from the garage / workshop.",
    DocumentType.DAMAGE_PHOTOS: "Photographs of the damaged vehicle or asset.",
    DocumentType.PURCHASE_INVOICE: "Original purchase invoice of the gadget.",
    DocumentType.OTHER: "Any other supporting document.",
}

_KEYWORDS: List[Tuple[str, List[str]]] = [
    (DocumentType.DISCHARGE_SUMMARY, ["discharge summary", "date of discharge", "discharge date", "discharged on"]),
    (DocumentType.MEDICAL_CERTIFICATE, ["medical certificate", "certify that", "treating doctor", "fitness certificate", "hereby certify"]),
    (DocumentType.HOSPITAL_BILL, ["final bill", "hospital bill", "invoice", "bill no", "total amount", "room charges", "grand total"]),
    (DocumentType.CLAIM_FORM, ["claim form", "part a", "part b", "claimant details"]),
    (DocumentType.POLICY_COPY, ["policy schedule", "policy number", "sum insured", "policy period"]),
    (DocumentType.ID_PROOF, ["aadhaar", "aadhar", "pan card", "passport", "identity", "government of india"]),
    (DocumentType.PRESCRIPTION, ["prescription", "rx", "tablet", "mg", "twice daily"]),
    (DocumentType.DIAGNOSTIC_REPORT, ["lab report", "pathology", "radiology", "mri", "ct scan", "x-ray", "test result"]),
    (DocumentType.DRIVING_LICENSE, ["driving licence", "driving license", "dl no", "licence no"]),
    (DocumentType.RC_COPY, ["registration certificate", "regn", "chassis", "engine no"]),
    (DocumentType.FIR_COPY, ["first information report", "fir", "police station", "complainant"]),
    (DocumentType.REPAIR_ESTIMATE, ["estimate", "labour", "spare parts", "workshop", "garage"]),
    (DocumentType.DAMAGE_PHOTOS, ["photo", "image", "damage"]),
    (DocumentType.PURCHASE_INVOICE, ["purchase invoice", "imei", "serial no", "tax invoice"]),
]

_FILENAME_HINTS: List[Tuple[str, List[str]]] = [
    (DocumentType.DISCHARGE_SUMMARY, ["discharge"]),
    (DocumentType.MEDICAL_CERTIFICATE, ["certificate", "medical_cert", "doctor"]),
    (DocumentType.HOSPITAL_BILL, ["bill", "invoice"]),
    (DocumentType.CLAIM_FORM, ["claim_form", "claimform"]),
    (DocumentType.POLICY_COPY, ["policy"]),
    (DocumentType.ID_PROOF, ["aadhaar", "aadhar", "pan", "passport", "id_proof", "idproof"]),
    (DocumentType.DRIVING_LICENSE, ["license", "licence", "dl"]),
    (DocumentType.RC_COPY, ["rc_", "rc.", "registration"]),
    (DocumentType.FIR_COPY, ["fir"]),
    (DocumentType.REPAIR_ESTIMATE, ["estimate", "repair"]),
    (DocumentType.DAMAGE_PHOTOS, ["photo", "damage", ".jpg", ".png", ".jpeg"]),
    (DocumentType.PURCHASE_INVOICE, ["purchase"]),
]

_DATE_PATTERNS = [
    (r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", "dmy"),
    (r"(\d{4})-(\d{2})-(\d{2})", "ymd"),
    (r"(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?,?\s+(\d{4})", "dMy"),
    (r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", "Mdy"),
]
_MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

_FIELD_PATTERNS: Dict[str, List[str]] = {
    "patient_name": [r"patient(?:'s)?\s*name\s*[:\-]\s*([A-Za-z .]+)", r"name of (?:the )?patient\s*[:\-]\s*([A-Za-z .]+)", r"insured(?:'s)? name\s*[:\-]\s*([A-Za-z .]+)"],
    "hospital_name": [r"hospital(?:\s*name)?\s*[:\-]\s*([A-Za-z0-9 .&,]+)"],
    "admission_date": [r"(?:date of )?admission(?: date)?\s*[:\-]\s*([^\n]+)", r"admitted on\s*[:\-]?\s*([^\n]+)"],
    "discharge_date": [r"(?:date of )?discharge(?: date)?\s*[:\-]\s*([^\n]+)", r"discharged on\s*[:\-]?\s*([^\n]+)"],
    "diagnosis": [r"diagnosis\s*[:\-]\s*([^\n]+)"],
    "total_amount": [r"(?:grand total|total amount|net payable|total)\s*[:\-]?\s*(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d{1,2})?)"],
    "policy_number": [r"policy (?:no|number)\.?\s*[:\-]\s*([A-Z0-9\-/]+)"],
    "doctor_name": [r"(?:dr\.?|doctor)\s*[:\-]?\s*([A-Z][A-Za-z .]+)"],
    "certificate_date": [r"(?:date|dated)\s*[:\-]\s*([^\n]+)"],
    "vehicle_number": [r"(?:vehicle|registration) (?:no|number)\.?\s*[:\-]\s*([A-Z]{2}[ -]?\d{1,2}[ -]?[A-Z]{1,3}[ -]?\d{1,4})"],
    "fir_number": [r"fir (?:no|number)\.?\s*[:\-]\s*([A-Z0-9/\-]+)"],
    "estimate_amount": [r"estimate(?:d)? (?:amount|total)\s*[:\-]?\s*(?:rs\.?|inr|₹)?\s*([\d,]+)"],
}

_REQUIRED_FIELDS: Dict[str, List[str]] = {
    DocumentType.DISCHARGE_SUMMARY: ["patient_name", "admission_date", "discharge_date", "diagnosis"],
    DocumentType.HOSPITAL_BILL: ["patient_name", "total_amount"],
    DocumentType.MEDICAL_CERTIFICATE: ["patient_name", "diagnosis", "doctor_name"],
    DocumentType.CLAIM_FORM: ["policy_number"],
    DocumentType.POLICY_COPY: ["policy_number"],
    DocumentType.REPAIR_ESTIMATE: ["estimate_amount"],
    DocumentType.FIR_COPY: ["fir_number"],
}


def parse_date(raw: str) -> Optional[datetime]:
    raw = raw.strip().lower()
    for pattern, kind in _DATE_PATTERNS:
        m = re.search(pattern, raw)
        if not m:
            continue
        try:
            if kind == "dmy":
                return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if kind == "ymd":
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if kind == "dMy":
                return datetime(int(m.group(3)), _MONTHS[m.group(2)[:3]], int(m.group(1)))
            if kind == "Mdy":
                return datetime(int(m.group(3)), _MONTHS[m.group(1)[:3]], int(m.group(2)))
        except (ValueError, KeyError):
            continue
    return None


def classify(text: str, file_name: str, declared_type: Optional[str] = None) -> Tuple[str, float]:
    """Return (document_type, confidence). Declared type wins when content agrees or text is empty."""
    lower_text = text.lower()
    lower_name = file_name.lower()
    scores: Dict[str, float] = {}
    for doc_type, keywords in _KEYWORDS:
        hits = sum(1 for k in keywords if k in lower_text)
        if hits:
            scores[doc_type] = scores.get(doc_type, 0) + hits * 1.0
    for doc_type, hints in _FILENAME_HINTS:
        if any(h in lower_name for h in hints):
            scores[doc_type] = scores.get(doc_type, 0) + 1.5
    if declared_type and declared_type != DocumentType.OTHER:
        scores[declared_type] = scores.get(declared_type, 0) + 2.0
    if not scores:
        return (declared_type or DocumentType.OTHER, 0.3)
    best = max(scores.items(), key=lambda kv: kv[1])
    total = sum(scores.values())
    confidence = round(min(0.99, 0.4 + 0.6 * (best[1] / total)), 2)
    return best[0], confidence


def extract_fields(text: str, doc_type: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    if not text:
        return fields
    for field, patterns in _FIELD_PATTERNS.items():
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                value = m.group(1).strip().rstrip(".").strip()
                if field.endswith("_date"):
                    parsed = parse_date(value)
                    if parsed:
                        fields[field] = parsed.date().isoformat()
                        fields[field + "_raw"] = value
                        break
                    continue
                if field in {"total_amount", "estimate_amount"}:
                    try:
                        fields[field] = float(value.replace(",", ""))
                    except ValueError:
                        fields[field] = value
                    break
                fields[field] = value[:120]
                break
    dates = []
    for pattern, _ in _DATE_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            parsed = parse_date(m.group(0))
            if parsed:
                dates.append(parsed.date().isoformat())
    if dates:
        fields["all_dates"] = sorted(set(dates))[:10]
    return fields


def validate(doc_type: str, text: str, fields: Dict[str, Any], extraction_method: str) -> Tuple[str, List[str]]:
    issues: List[str] = []
    if extraction_method in {"image-no-ocr", "pdf-no-text-layer"}:
        issues.append("Text could not be extracted automatically; please make sure the document is legible.")
        return DocValidation.NEEDS_REVIEW, issues
    if not text.strip():
        issues.append("Document appears to be empty.")
        return DocValidation.INVALID, issues
    for field in _REQUIRED_FIELDS.get(doc_type, []):
        if field not in fields:
            issues.append(f"Could not find '{field.replace('_', ' ')}' in the document.")
    if "admission_date" in fields and "discharge_date" in fields and fields["discharge_date"] < fields["admission_date"]:
        issues.append("Discharge date is earlier than admission date.")
    if issues:
        return DocValidation.NEEDS_REVIEW, issues
    return DocValidation.VALID, issues


def analyse(content_text: str, file_name: str, declared_type: Optional[str], extraction_method: str) -> Dict[str, Any]:
    doc_type, confidence = classify(content_text, file_name, declared_type)
    fields = extract_fields(content_text, doc_type)
    status, issues = validate(doc_type, content_text, fields, extraction_method)
    return {
        "document_type": doc_type,
        "confidence": confidence,
        "fields": fields,
        "validation_status": status,
        "issues": issues,
    }


def cross_document_issues(documents: List[ClaimDocument]) -> List[Dict[str, Any]]:
    """Compare key fields across documents and surface inconsistencies.
    Returns a list of {field, values:{doc_label: value}, message, action}."""
    issues: List[Dict[str, Any]] = []
    compare_fields = ["admission_date", "discharge_date", "patient_name", "policy_number"]
    for field in compare_fields:
        values: Dict[str, str] = {}
        for doc in documents:
            val = (doc.extracted_fields or {}).get(field)
            if val:
                label = DOC_LABELS.get(doc.document_type, doc.document_type)
                norm = str(val).strip().lower() if field.endswith("name") else str(val)
                values[label] = norm
        distinct = set(values.values())
        if len(distinct) > 1:
            pretty = field.replace("_", " ")
            issues.append(
                {
                    "field": field,
                    "values": values,
                    "message": f"Potential inconsistency: {pretty}s differ across documents "
                    + "; ".join(f"{k}: {v}" for k, v in values.items())
                    + ".",
                    "action": f"Please verify the correct {pretty} before submission.",
                }
            )
    return issues


def label_for(doc_type: str) -> str:
    return DOC_LABELS.get(doc_type, doc_type.replace("_", " ").title())
