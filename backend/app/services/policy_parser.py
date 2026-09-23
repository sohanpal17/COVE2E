"""Deterministic policy text → structured profile extraction.

Regex-driven so uploads work offline. When Sarvam is configured, PolicyAgent
may enrich the profile, but the deterministic parse is always the baseline.
"""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.document_intelligence import parse_date

_AMOUNT = r"(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d+)?)\s*(lakh|lakhs|lac|l|crore|cr|k)?"


def _amount(raw: Optional[str], unit: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    unit = (unit or "").lower()
    if unit in {"lakh", "lakhs", "lac", "l"}:
        value *= 100_000
    elif unit in {"crore", "cr"}:
        value *= 10_000_000
    elif unit == "k":
        value *= 1_000
    return value


def _find_amount(text: str, labels: List[str]) -> Optional[float]:
    for label in labels:
        m = re.search(label + r"\s*[:\-]?\s*" + _AMOUNT, text, flags=re.IGNORECASE)
        if m:
            return _amount(m.group(1), m.group(2))
    return None


def _find(text: str, patterns: List[str]) -> Optional[str]:
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _section(text: str, headers: List[str]) -> str:
    """Return the text under the first matching header until the next ALL-CAPS/numbered header."""
    for h in headers:
        # Header match is case-insensitive; the lookahead for the NEXT header must be case-sensitive
        # (an all-caps line), otherwise ordinary bullet lines would terminate the section.
        header_re = "".join(f"[{c.upper()}{c.lower()}]" if c.isalpha() else re.escape(c) for c in h)
        m = re.search(rf"^\s*(?:\d+(?:\.\d+)*\.?\s*)?{header_re}[^\n]*\n(.*?)(?=^\s*(?:\d+(?:\.\d+)*\.?\s+)?[A-Z][A-Z \-/&()]{{4,}}\s*$|\Z)", text, flags=re.DOTALL | re.MULTILINE)
        if m:
            return m.group(1).strip()
    return ""


def _bullets(block: str) -> List[str]:
    items = []
    for line in block.splitlines():
        s = line.strip()
        s = re.sub(r"^[\-\*•\d\.\)]+\s*", "", s)
        if len(s) > 3:
            items.append(s)
    return items


def parse_policy_text(text: str) -> Dict[str, Any]:
    t = text or ""
    lower = t.lower()
    policy_type = "HEALTH"
    if any(k in lower for k in ["motor", "vehicle", "two wheeler", "four wheeler", "car insurance", "own damage"]):
        policy_type = "MOTOR"
    if any(k in lower for k in ["gadget", "mobile phone insurance", "imei"]):
        policy_type = "GADGET"

    policy_number = _find(t, [r"policy (?:no|number)\.?\s*[:\-]\s*([A-Z0-9\-/]+)"])
    insurer = _find(t, [r"insurer\s*[:\-]\s*([^\n]+)", r"issued by\s*[:\-]?\s*([^\n]+)", r"^([A-Z][A-Za-z&\. ]+ (?:General|Health|Life) Insurance(?: Company)?(?: Ltd\.?| Limited)?)"])
    plan_name = _find(t, [r"(?:plan|product) name\s*[:\-]\s*([^\n]+)", r"plan\s*[:\-]\s*([^\n]+)"])
    holder = _find(t, [r"(?:policy ?holder|proposer|insured) name\s*[:\-]\s*([^\n]+)"])
    members_block = _find(t, [r"insured members?\s*[:\-]\s*([^\n]+)"])
    members = [m.strip() for m in re.split(r",|;|\band\b", members_block)] if members_block else []

    sum_insured = _find_amount(t, [r"sum insured", r"idv", r"insured declared value", r"coverage amount"])
    premium = _find_amount(t, [r"(?:annual |total )?premium(?: paid)?"])
    deductible = _find_amount(t, [r"deductible", r"compulsory deductible"]) or 0.0
    room_rent = _find_amount(t, [r"room rent(?: limit)?", r"room rent(?: capped at| up to)?"])

    _date_tok = r"(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9},?\s+\d{4})"
    start_raw = _find(t, [rf"period\s*[:\-]\s*{_date_tok}\s*(?:to|-|–)", rf"(?:policy )?(?:start|commencement|from) (?:date)?\s*[:\-]?\s*{_date_tok}"])
    end_raw = _find(t, [rf"period\s*[:\-]\s*[^\n]+?\s*(?:to|-|–)\s*{_date_tok}", rf"(?:policy )?(?:end|expiry|valid (?:till|until)|to) (?:date)?\s*[:\-]?\s*{_date_tok}"])
    start = parse_date(start_raw) if start_raw else None
    end = parse_date(end_raw) if end_raw else None

    wp = _find(t, [r"(?:initial |general )?waiting period(?: of)?\s*[:\-]?\s*(\d+)\s*days", r"(\d+)[- ]day waiting period"])
    waiting_days = int(wp) if wp else 0

    claim_types: List[str] = []
    if "cashless" in lower:
        claim_types.append("CASHLESS")
    if "reimbursement" in lower:
        claim_types.append("REIMBURSEMENT")
    if "own damage" in lower:
        claim_types.append("OWN_DAMAGE")
    if "third party" in lower or "third-party" in lower:
        claim_types.append("THIRD_PARTY")
    if not claim_types:
        claim_types = ["REIMBURSEMENT"] if policy_type == "HEALTH" else ["OWN_DAMAGE"]

    exclusions = _bullets(_section(t, ["EXCLUSIONS", "WHAT IS NOT COVERED", "GENERAL EXCLUSIONS"]))
    coverage_lines = _bullets(_section(t, ["COVERAGE", "WHAT IS COVERED", "BENEFITS", "COVERAGE SCHEDULE"]))
    required_docs = _bullets(_section(t, ["REQUIRED DOCUMENTS", "CLAIM DOCUMENTS", "DOCUMENTS REQUIRED"]))
    claim_process = _bullets(_section(t, ["CLAIM PROCESS", "CLAIM PROCEDURE", "HOW TO CLAIM"]))
    conditions_lines = _bullets(_section(t, ["CONDITIONS", "SPECIAL CONDITIONS", "LIMITS AND CONDITIONS", "LIMITS"]))

    coverages = []
    for line in coverage_lines:
        covered = "YES"
        if re.search(r"\bnot covered\b|\bexcluded\b", line, re.I):
            covered = "NO"
        elif re.search(r"\bsubject to\b|\bup to\b|\blimit\b|\bcapped\b|\bafter\b|\bonly\b", line, re.I):
            covered = "CONDITIONAL"
        name = re.split(r"[:\-–]", line, maxsplit=1)[0].strip()[:120]
        limit_m = re.search(_AMOUNT + r"(?:\s*(?:per day|/day|per year|per claim))?", line, re.I)
        limit_amt = _amount(limit_m.group(1), limit_m.group(2)) if limit_m and limit_m.group(1) else None
        coverages.append({"name": name, "covered": covered, "limit_amount": limit_amt, "limit_text": limit_m.group(0).strip() if limit_m and limit_amt else "", "condition_text": line if covered == "CONDITIONAL" else "", "section_ref": "Coverage", "keywords": [w.lower() for w in re.findall(r"[A-Za-z]{4,}", name)][:6]})

    conditions = []
    for e in exclusions:
        conditions.append({"kind": "EXCLUSION", "title": e[:160], "description": e, "value": "", "section_ref": "Exclusions"})
    for c in conditions_lines:
        kind = "LIMIT" if re.search(r"limit|up to|capped|per day", c, re.I) else "CONDITION"
        conditions.append({"kind": kind, "title": c[:160], "description": c, "value": "", "section_ref": "Conditions"})
    for d in required_docs:
        conditions.append({"kind": "REQUIRED_DOCUMENT", "title": d[:160], "description": "", "value": "", "section_ref": "Required documents"})
    for i, p in enumerate(claim_process, 1):
        conditions.append({"kind": "CLAIM_PROCEDURE", "title": f"Step {i}: {p[:150]}", "description": p, "value": "", "section_ref": "Claim process"})
    if waiting_days:
        conditions.append({"kind": "WAITING_PERIOD", "title": "Initial waiting period", "description": f"Claims (other than accidents) are payable only after {waiting_days} days from policy start.", "value": f"{waiting_days} days", "section_ref": "Waiting periods"})
    if deductible:
        conditions.append({"kind": "DEDUCTIBLE", "title": "Deductible", "description": "Amount borne by the insured per claim.", "value": f"₹{deductible:,.0f}", "section_ref": "Deductible"})
    if room_rent:
        conditions.append({"kind": "LIMIT", "title": "Room rent limit", "description": "Maximum room rent payable per day.", "value": f"₹{room_rent:,.0f}/day", "section_ref": "Limits"})

    return {
        "policy_type": policy_type,
        "policy_number": policy_number or "",
        "insurer": insurer or "",
        "plan_name": plan_name or "",
        "holder_name": holder or "",
        "insured_members": members,
        "sum_insured": sum_insured or 0.0,
        "premium": premium or 0.0,
        "deductible": deductible,
        "room_rent_limit": room_rent,
        "waiting_period_days": waiting_days,
        "start_date": start.date().isoformat() if start else None,
        "end_date": end.date().isoformat() if end else None,
        "claim_types": claim_types,
        "coverages": coverages,
        "conditions": conditions,
        "exclusions": exclusions,
        "required_documents": required_docs,
        "claim_process": claim_process,
        "extraction": "deterministic-regex",
    }


def to_datetime(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None
