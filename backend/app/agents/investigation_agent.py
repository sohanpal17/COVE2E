"""Investigation Agent: runs the deterministic Investigation Engine, then asks
Sarvam to explain the result in the user's language. The AI cannot alter the
blocker, evidence, next action or confidence."""
from typing import Optional

from sqlalchemy.orm import Session

from app.agents.lang import SYSTEM_STYLE, language_instruction, localize, normalise
from app.core.enums import Actor, AuditAction
from app.engines import investigation_engine
from app.integrations.sarvam_client import get_sarvam
from app.models import Claim, Journey, User
from app.schemas.ai import InvestigationResult
from app.services.audit_service import record_audit


def _deterministic_explanation(r: InvestigationResult) -> str:
    if r.blocker in {"missing_requested_document", "requested_document_not_attached"}:
        return f"Your claim is currently blocked at {r.affected_step.lower()}. {r.evidence[0] if r.evidence else ''} {r.evidence[1] if len(r.evidence) > 1 else ''}".strip()
    if r.blocker == "conflicting_external_state":
        return "The available state indicates the claim is currently blocked because the insurer's systems report conflicting states. This must be reconciled by a human; I will not change anything automatically."
    if r.blocker == "document_inconsistency":
        return "Before submission, your documents disagree with each other. " + (r.evidence[0] if r.evidence else "") + " Please verify the correct value; I will not change any document myself."
    if r.blocker == "awaiting_insurer":
        return "Your claim is not stuck. It is under review with the insurer and no action is needed from you right now."
    if r.blocker == "insurer_delay":
        return f"The insurer has not updated your claim for {r.days_stuck} days, longer than the expected review window. I can raise a follow-up."
    if r.blocker == "missing_required_documents":
        return "Your claim has not reached the insurer yet; it is waiting for required documents from you."
    if r.blocker == "ready_to_submit":
        return "Your claim appears ready for the next stage based on the available information; it has not been submitted yet."
    if r.blocker == "escalated":
        return "This journey is with a human agent. Automated recovery is paused."
    if r.blocker == "resolved":
        return "This journey is resolved."
    return r.blocker_label


def run(db: Session, *, user: User, journey: Journey, claim: Optional[Claim], message: Optional[str], language: str = "en") -> InvestigationResult:
    lang = normalise(language)
    record_audit(db, AuditAction.USER_REQUESTED_RECOVERY, actor=Actor.USER, user_id=user.id, journey_id=journey.id, claim_id=claim.id if claim else None, metadata={"message": message or ""})

    result = investigation_engine.investigate(db, journey, claim, user_message=message)
    result.explanation = _deterministic_explanation(result)
    result.explanation_source = "DETERMINISTIC"

    sarvam = get_sarvam()
    if sarvam.enabled:
        text = sarvam.chat(
            [
                {"role": "system", "content": SYSTEM_STYLE + " You are explaining a completed, deterministic investigation. Do not add facts, do not change the conclusion, do not predict approval. 2-4 sentences: current state, blocker, key evidence, what happens next. " + language_instruction(lang)},
                {"role": "user", "content": f"USER SAID: {message or 'Why is my claim stuck?'}\nINVESTIGATION RESULT: {result.model_dump_json(exclude={'checks'})}"},
            ],
            max_tokens=320,
        )
        if text:
            result.explanation = text.strip()
            result.explanation_source = "AI"
    elif lang != "en":
        result.explanation = localize(result.explanation, lang)

    record_audit(db, AuditAction.AI_IDENTIFIED_BLOCKER, actor=Actor.AI if result.explanation_source == "AI" else Actor.SYSTEM, user_id=user.id, journey_id=journey.id, claim_id=claim.id if claim else None, new_state=result.blocker, result=f"confidence={result.confidence}", metadata={"blocker": result.blocker, "next_action": result.next_action, "evidence": result.evidence})
    journey.last_investigation = result.model_dump()
    from app.engines.journey_state_engine import add_event

    add_event(db, journey, "INVESTIGATION_COMPLETED", description=f"Investigation: {result.blocker_label}", actor=Actor.AI, metadata={"blocker": result.blocker, "confidence": result.confidence})
    db.flush()
    return result
