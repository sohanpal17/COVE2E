from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.lang import SYSTEM_STYLE, language_instruction, localize, normalise
from app.core.database import get_db
from app.core.security import get_current_user
from app.integrations.sarvam_client import get_sarvam
from app.models import InsuranceProduct, User
from app.schemas.api import DiscoveryRequest, DiscoveryResponse, ProductOut
from app.services import demo_service
from app.services.discovery_service import match_products

router = APIRouter(prefix="/api/discovery", tags=["discovery"])

DISCLAIMER = "COVE2E explains how each option matches the requirements you provided. It does not recommend a 'best' policy; the right choice depends on your full situation and the insurer's underwriting."


@router.get("/products", response_model=List[ProductOut])
def products(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    demo_service.ensure_products(db)
    db.commit()
    return db.query(InsuranceProduct).order_by(InsuranceProduct.product_type, InsuranceProduct.premium_annual).all()


@router.post("", response_model=DiscoveryResponse)
def discover(req: DiscoveryRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    demo_service.ensure_products(db)
    db.commit()
    matches = match_products(db, req)
    lang = normalise(req.language)
    if matches:
        top = matches[0]
        narrative = f"{top.product.name} ({top.product.insurer}) matches the requirements you provided because: " + " ".join(top.reasons[:3])
        if top.cautions:
            narrative += " Keep in mind: " + " ".join(top.cautions[:2])
        if len(matches) > 1:
            narrative += f" {matches[1].product.name} is an alternative with a different trade-off: " + (matches[1].reasons[0] if matches[1].reasons else "") + (f" but {matches[1].cautions[0]}" if matches[1].cautions else "")
    else:
        narrative = "No products of this type are available in the catalogue."
    source = "DETERMINISTIC"
    sarvam = get_sarvam()
    if sarvam.enabled and matches:
        text = sarvam.chat(
            [
                {"role": "system", "content": SYSTEM_STYLE + " Compare the matched options in 3-4 sentences. Never say 'best'. Use 'matches the requirements you provided because'. " + language_instruction(lang)},
                {"role": "user", "content": f"REQUIREMENTS: {req.model_dump_json()}\nMATCHES: " + "; ".join(f"{m.product.name}: score {m.match_score}, reasons {m.reasons}, cautions {m.cautions}" for m in matches)},
            ],
            max_tokens=320,
        )
        if text:
            narrative, source = text.strip(), "AI"
    elif lang != "en":
        narrative = localize(narrative, lang)
    return DiscoveryResponse(matches=matches, narrative=narrative, narrative_source=source, disclaimer=DISCLAIMER)
