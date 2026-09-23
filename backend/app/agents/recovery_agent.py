"""Recovery Agent: builds the recovery plan via the deterministic Recovery Engine
(which routes the action through the Action Gate) and phrases the message."""
from typing import Optional

from sqlalchemy.orm import Session

from app.agents.lang import SYSTEM_STYLE, language_instruction, localize, normalise
from app.engines import recovery_engine
from app.integrations.sarvam_client import get_sarvam
from app.models import Claim, Journey, User
from app.schemas.ai import InvestigationResult, RecoveryPlan


def run(db: Session, *, user: User, journey: Journey, claim: Optional[Claim], investigation: InvestigationResult, language: str = "en") -> RecoveryPlan:
    lang = normalise(language)
    plan = recovery_engine.build_plan(db, user=user, journey=journey, claim=claim, investigation=investigation)
    plan.message_source = "DETERMINISTIC"

    sarvam = get_sarvam()
    if sarvam.enabled:
        steps = "; ".join(f"{s.order}. {s.label} [{s.status}]" for s in plan.steps)
        gate = f"Action: {plan.action.title}. Gate decision: {plan.action.gate_decision}. Reasons: {'; '.join(plan.action.gate_reasons)}." if plan.action else "No executable action."
        text = sarvam.chat(
            [
                {"role": "system", "content": SYSTEM_STYLE + " Explain the prepared recovery plan in 2-3 sentences. If confirmation is required say so and ask the user to confirm. If escalated, say a human agent will review. Never promise approval. " + language_instruction(lang)},
                {"role": "user", "content": f"BLOCKER: {plan.blocker_label}\nSTEPS: {steps}\n{gate}\nRISK CLASS: {plan.risk_class}\nDETERMINISTIC MESSAGE: {plan.message}"},
            ],
            max_tokens=260,
        )
        if text:
            plan.message = text.strip()
            plan.message_source = "AI"
    elif lang != "en":
        plan.message = localize(plan.message, lang)
        plan.summary = localize(plan.summary, lang)
    db.flush()
    return plan
