"""Insurance discovery: needs analysis and deterministic product matching.

Never says "best". Explains why an option matches the requirements provided.
"""
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.models import InsuranceProduct
from app.schemas.api import DiscoveryMatch, DiscoveryRequest, ProductOut


def match_products(db: Session, req: DiscoveryRequest) -> List[DiscoveryMatch]:
    products = db.query(InsuranceProduct).filter(InsuranceProduct.product_type == req.insurance_type.upper()).all()
    matches: List[DiscoveryMatch] = []
    for p in products:
        score, reasons, cautions = _score(p, req)
        matches.append(DiscoveryMatch(product=ProductOut.model_validate(p), match_score=score, reasons=reasons, cautions=cautions))
    matches.sort(key=lambda m: m.match_score, reverse=True)
    return matches


def _score(p: InsuranceProduct, req: DiscoveryRequest) -> Tuple[int, List[str], List[str]]:
    score = 50
    reasons: List[str] = []
    cautions: List[str] = []
    family = req.family_situation.lower()
    risks = [r.lower() for r in req.risk_requirements]
    tags = [t.lower() for t in (p.suitability_tags or [])]

    if not (p.min_age <= req.age <= p.max_age):
        score -= 30
        cautions.append(f"Entry age range is {p.min_age}-{p.max_age}; you entered {req.age}.")
    else:
        reasons.append(f"Entry age {req.age} is within the eligible range ({p.min_age}-{p.max_age}).")

    if req.budget_annual:
        if p.premium_annual <= req.budget_annual:
            score += 15
            reasons.append(f"Annual premium ₹{p.premium_annual:,.0f} fits within your budget of ₹{req.budget_annual:,.0f}.")
        else:
            over = p.premium_annual - req.budget_annual
            score -= min(25, int(over / max(req.budget_annual, 1) * 50))
            cautions.append(f"Premium ₹{p.premium_annual:,.0f} exceeds your budget by ₹{over:,.0f}.")

    if "family" in family or "married" in family or "children" in family:
        if "family" in tags:
            score += 15
            reasons.append("Designed as a family floater, matching your family situation.")
        else:
            cautions.append("Individual plan; each family member needs separate cover.")
    else:
        if "individual" in tags:
            score += 10
            reasons.append("Individual plan suits a single applicant.")

    for r in risks:
        if any(r in t for t in tags):
            score += 8
            reasons.append(f"Addresses your stated requirement: {r}.")
    if "low deductible" in risks or "no deductible" in risks:
        if p.deductible == 0:
            score += 8
            reasons.append("No deductible.")
        else:
            cautions.append(f"Deductible of ₹{p.deductible:,.0f} applies per claim.")
    if "short waiting period" in risks and p.waiting_period_days <= 30:
        score += 8
        reasons.append(f"Short initial waiting period ({p.waiting_period_days} days).")
    elif p.waiting_period_days > 30:
        cautions.append(f"Initial waiting period of {p.waiting_period_days} days.")

    if req.existing_coverage and any("health" in c.lower() for c in req.existing_coverage) and p.product_type == "HEALTH":
        cautions.append("You already have health coverage; consider this as a top-up rather than a replacement.")

    if p.exclusions:
        cautions.append("Major exclusions: " + "; ".join(p.exclusions[:2]) + ".")
    reasons.append(f"Sum insured ₹{p.sum_insured:,.0f}.")
    return max(0, min(100, score)), reasons, cautions
