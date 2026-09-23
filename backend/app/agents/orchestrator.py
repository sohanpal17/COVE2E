"""Orchestrator: the Ask COVE2E entry point.

Sarvam detects intent (structured). FastAPI routes to the specialised agent.
Every intent has a deterministic keyword fallback so the demo never breaks.
"""
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agents import claim_agent, investigation_agent, journey_agent, policy_agent, recovery_agent
from app.agents.lang import SYSTEM_STYLE, language_instruction, localize, normalise
from app.integrations.sarvam_client import get_sarvam
from app.models import Claim, Journey, Policy, User
from app.schemas.ai import IntentResult
from app.schemas.api import ChatRequest, ChatResponse
from app.services import claim_service, journey_service, policy_service
from app.services.readiness_service import compute_readiness

KEYWORDS = [
    ("STUCK_CLAIM", r"stuck|why.*(claim|delay)|no update|pending for|not moving|blocked|recover|eight days|\d+ days"),
    ("TRACK_CLAIM", r"track|status|where is my claim|progress"),
    ("MISSING_DOCUMENTS", r"missing|which documents|what documents|checklist|need to upload"),
    ("CLAIM_READINESS", r"ready|readiness|can i submit|complete"),
    ("START_CLAIM", r"start a claim|file a claim|new claim|raise a claim|make a claim"),
    ("INCIDENT_REPORT", r"hospitali[sz]ed|admitted|accident|hit|stolen|theft|damaged|broke|injur|surgery|fever"),
    ("COMPARE_INSURANCE", r"compare|best (policy|plan|insurance)|which (policy|plan)|buy|new insurance|options"),
    ("POLICY_QUESTION", r"cover|covered|limit|waiting|deductible|exclu|room rent|icu|dental|expire|expiry|premium|sum insured|policy"),
    ("ESCALATE", r"escalate|human|agent|speak to someone|complain"),
    ("GREETING", r"^(hi|hello|hey|namaste|namaskar|good (morning|afternoon|evening))\b"),
]
# Hindi / Marathi keywords for the deterministic fallback
KEYWORDS_INDIC = [
    ("STUCK_CLAIM", r"अटक|रुक|फंस|क्यों.*क्लेम|दावा.*अटक|क्लेम.*दिन"),
    ("TRACK_CLAIM", r"स्थिति|स्टेटस|ट्रैक|कहाँ"),
    ("MISSING_DOCUMENTS", r"दस्तावेज|कागद|डॉक्युमेंट"),
    ("INCIDENT_REPORT", r"अस्पताल|भर्ती|दुर्घटना|चोरी|एक्सीडेंट|रुग्णालय|अपघात"),
    ("POLICY_QUESTION", r"कवर|पॉलिसी|आईसीयू|प्रतीक्षा|वेटिंग|समाप्त|कव्हर"),
    ("COMPARE_INSURANCE", r"तुलना|कौन सी पॉलिसी|कोणती"),
    ("GREETING", r"नमस्ते|नमस्कार|हैलो"),
]


def detect_intent(message: str, language: str) -> IntentResult:
    sarvam = get_sarvam()
    if sarvam.enabled:
        ai = sarvam.structured(
            SYSTEM_STYLE + " Classify the user's message into exactly one intent. STUCK_CLAIM = the user thinks a claim is delayed/stuck or asks why; TRACK_CLAIM = wants status; POLICY_QUESTION = asks what the policy covers/limits/expiry; INCIDENT_REPORT = describes something that happened.",
            f"LANGUAGE HINT: {language}\nMESSAGE: {message}",
            IntentResult,
        )
        if ai:
            return ai
    text = message.strip()
    for intent, pattern in KEYWORDS_INDIC:
        if re.search(pattern, text):
            return IntentResult(intent=intent, confidence=0.7, language=language)  # type: ignore[arg-type]
    lower = text.lower()
    for intent, pattern in KEYWORDS:
        if re.search(pattern, lower):
            return IntentResult(intent=intent, confidence=0.75, language=language)  # type: ignore[arg-type]
    return IntentResult(intent="GENERAL", confidence=0.4, language=language)


def _pick_claim(db: Session, user: User, req: ChatRequest, prefer_stuck: bool = False) -> Optional[Claim]:
    if req.claim_id:
        return claim_service.get_claim(db, user, req.claim_id)
    if req.journey_id:
        j = journey_service.get_journey(db, user, req.journey_id)
        return db.get(Claim, j.claim_id) if j.claim_id else None
    claims = claim_service.list_claims(db, user)
    if prefer_stuck:
        for c in claims:
            if any(q.status == "OPEN" for q in c.queries):
                return c
        for c in claims:
            if c.payment_status == "COMPLETED" and c.settlement_status != "COMPLETED":
                return c
    active = [c for c in claims if c.status not in {"SETTLED", "REJECTED"}]
    return active[0] if active else (claims[0] if claims else None)


def _pick_policy(db: Session, user: User, req: ChatRequest, message: str) -> Optional[Policy]:
    if req.policy_id:
        return policy_service.get_policy(db, user, req.policy_id)
    policies = policy_service.list_policies(db, user)
    lower = message.lower()
    for p in policies:
        if p.policy_type.lower() in lower or (p.policy_type == "MOTOR" and re.search(r"car|vehicle|bike", lower)):
            return p
    return policies[0] if policies else None


def chat(db: Session, user: User, req: ChatRequest) -> ChatResponse:
    lang = normalise(req.language)
    intent = detect_intent(req.message, lang)
    data: Dict[str, Any] = {}
    suggested: List[Dict[str, str]] = []
    navigate: Optional[str] = None
    source = "DETERMINISTIC"

    if intent.intent == "STUCK_CLAIM":
        claim = _pick_claim(db, user, req, prefer_stuck=True)
        if not claim or not claim.journey_id:
            reply = "I could not find an active claim to investigate. Start a claim first, or load the demo data."
            navigate = "/claims"
        else:
            journey = db.get(Journey, claim.journey_id)
            inv = investigation_agent.run(db, user=user, journey=journey, claim=claim, message=req.message, language=lang)
            plan = recovery_agent.run(db, user=user, journey=journey, claim=claim, investigation=inv, language=lang)
            db.commit()
            reply = inv.explanation + "\n\n" + plan.message
            source = "AI" if inv.explanation_source == "AI" else "DETERMINISTIC"
            data = {"investigation": inv.model_dump(), "recovery_plan": plan.model_dump(), "journey_id": journey.id, "claim_id": claim.id}
            navigate = f"/journeys/{journey.id}/investigation"
            suggested = [{"label": "Open investigation", "link": navigate}, {"label": "View recovery plan", "link": f"/journeys/{journey.id}/recovery"}]
    elif intent.intent == "TRACK_CLAIM":
        claim = _pick_claim(db, user, req)
        if not claim:
            reply = "You have no claims yet."
        else:
            journey = db.get(Journey, claim.journey_id) if claim.journey_id else None
            tr = journey_service.tracking(db, claim, journey)
            reply = f"Claim {claim.claim_number}: {tr.current_state_label}. " + journey_agent.explain_tracking(tr, lang)
            data = {"tracking": tr.model_dump(mode='json'), "claim_id": claim.id}
            navigate = f"/claims/{claim.id}/tracking"
            suggested = [{"label": "Open tracking", "link": navigate}]
    elif intent.intent in {"MISSING_DOCUMENTS", "CLAIM_READINESS"}:
        claim = _pick_claim(db, user, req)
        if not claim:
            reply = "You have no claims yet. Describe what happened and I will help you start one."
            navigate = "/incidents"
        else:
            r = compute_readiness(claim)
            outstanding = [i.label for i in r.items if i.status != "DONE"]
            reply = f"Claim {claim.claim_number} readiness is {r.percent}% (documentation completeness, not an approval prediction). " + ("Outstanding: " + "; ".join(outstanding) + ". " if outstanding else "Nothing outstanding. ") + r.next_action
            data = {"readiness": r.model_dump(), "claim_id": claim.id}
            navigate = f"/claims/{claim.id}/readiness"
            suggested = [{"label": "Open readiness", "link": navigate}, {"label": "Upload documents", "link": f"/claims/{claim.id}/documents"}]
    elif intent.intent in {"INCIDENT_REPORT", "START_CLAIM"}:
        policies = policy_service.list_policies(db, user)
        cls = claim_agent.classify_incident(db, user, req.message, policies, lang)
        db.commit()
        reply = f"{cls.summary}\n{cls.coverage_note}\nNext actions:\n" + "\n".join(f"{i + 1}. {a}" for i, a in enumerate(cls.next_actions))
        data = {"classification": cls.model_dump()}
        navigate = "/incidents"
        suggested = [{"label": "Start the claim", "link": f"/claims/new?policy_id={cls.matched_policy_id or ''}&incident_type={cls.incident_type}&claim_type={cls.suggested_claim_type or ''}"}]
    elif intent.intent == "POLICY_QUESTION":
        policy = _pick_policy(db, user, req, req.message)
        if not policy:
            reply = "You have no policy on file yet. Upload a policy PDF and I will answer from it."
            navigate = "/policies"
        else:
            ans = policy_agent.answer_question(db, policy, req.message, lang)
            db.commit()
            reply = ans.answer + (f"\nWhy: {ans.why}" if ans.why else "") + (f"\nImportant: {ans.important_condition}" if ans.important_condition else "") + (f"\nSource: {ans.source}" if ans.source else "")
            source = "AI" if "AI_INTERPRETATION" in ans.fact_types and get_sarvam().enabled else "DETERMINISTIC"
            data = {"policy_answer": ans.model_dump(), "policy_id": policy.id}
            navigate = f"/policies/{policy.id}/companion"
            suggested = [{"label": "Open Policy Companion", "link": navigate}]
    elif intent.intent == "COMPARE_INSURANCE":
        reply = "I can compare options against the requirements you provide — age, family situation, budget and what matters to you. I will explain why each option matches; I will not call any option 'the best'."
        navigate = "/discovery"
        suggested = [{"label": "Open Insurance Discovery", "link": navigate}]
    elif intent.intent == "ESCALATE":
        reply = "I can raise this to a human agent with a full escalation packet (problem, evidence, state, actions attempted). Open the journey's recovery page and choose Escalate."
        navigate = "/journeys"
    elif intent.intent == "GREETING":
        reply = f"Hello {user.name.split(' ')[0]}. I can explain your policy, help you start a claim, check readiness, track a claim, or find out why a claim is stuck. What would you like to work on?"
    else:
        sarvam = get_sarvam()
        text = sarvam.chat([{"role": "system", "content": SYSTEM_STYLE + " Answer briefly and, if relevant, point the user to: policy questions, starting a claim, claim readiness, tracking, or recovering a stuck claim. " + language_instruction(lang)}, {"role": "user", "content": req.message}], max_tokens=220) if sarvam.enabled else None
        if text:
            reply = text.strip()
            source = "AI"
        else:
            reply = "I can help with your policy, a new claim, claim readiness, tracking, or a stuck claim. Try: 'Is ICU covered?', 'My father was hospitalized yesterday', or 'Why is my claim stuck?'"

    if source == "DETERMINISTIC" and lang != "en":
        reply = localize(reply, lang)
    return ChatResponse(reply=reply, intent=intent.intent, confidence=intent.confidence, language=lang, source=source, data=data, suggested_actions=suggested, navigate_to=navigate)
