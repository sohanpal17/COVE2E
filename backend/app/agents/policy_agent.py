"""Policy Agent: policy-specific Q&A grounded in the knowledge layer.

Deterministic retrieval + rule-based coverage decision first; Sarvam refines the
wording and fills the explanation. The AI may not flip a confident deterministic
coverage decision.
"""
import re
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.agents.lang import SYSTEM_STYLE, language_instruction, localize, normalise
from app.core.enums import Actor, AuditAction
from app.integrations.sarvam_client import get_sarvam
from app.models import Policy
from app.schemas.ai import PolicyAnswer
from app.services.audit_service import record_audit
from app.services.policy_knowledge import get_policy_knowledge_service
from app.services.policy_knowledge.base import PolicyContext


def _fmt_money(v: Optional[float]) -> str:
    if v is None:
        return ""
    return f"₹{v:,.0f}"


def _deterministic(policy: Policy, question: str, ctx: PolicyContext) -> Tuple[PolicyAnswer, bool]:
    """Returns (answer, confident)."""
    q = question.lower()
    coverage_hits = [c for c in ctx.chunks if c.kind == "coverage"]
    condition_hits = [c for c in ctx.chunks if c.kind == "condition"]
    sources = [c.source for c in ctx.chunks[:3] if c.source]

    # Expiry / period questions (waiting-period questions are handled below)
    if re.search(r"expir|valid|renew|end date|policy period", q) or (re.search(r"\bperiod\b", q) and "waiting" not in q):
        end = policy.end_date.strftime("%d %b %Y") if policy.end_date else "not stated"
        start = policy.start_date.strftime("%d %b %Y") if policy.start_date else "not stated"
        from app.core.timeutil import aware, now

        days = (aware(policy.end_date) - now()).days if policy.end_date else None
        return PolicyAnswer(answer=f"Your policy period is {start} to {end}." + (f" It expires in {days} days." if days is not None else ""), coverage="UNKNOWN", why="Policy period from the policy schedule.", important_condition="Renew before expiry to avoid a fresh waiting period.", what_you_should_do="Set a renewal reminder about two weeks before expiry.", source="Policy schedule — Policy Period", fact_types=["POLICY_FACT", "GENERAL_GUIDANCE"], confidence=0.95, knowledge_backend=ctx.backend, retrieved_context=[c.text for c in ctx.chunks[:3]]), True

    if re.search(r"waiting period|waiting", q):
        wp = policy.waiting_period_days
        wait_conditions = [c.text for c in condition_hits if "waiting" in c.text.lower()]
        return PolicyAnswer(answer=(f"Yes. Your policy has an initial waiting period of {wp} days from the policy start date." if wp else "No general initial waiting period is stated in your policy."), coverage="CONDITIONAL" if wp else "YES", why="; ".join(wait_conditions[:2]) or "Waiting period from the policy schedule.", important_condition="Waiting periods usually do not apply to accidental hospitalisation. Pre-existing and specified illnesses have longer waiting periods.", what_you_should_do="Check the admission date against the policy start date before filing.", source="Waiting periods section", fact_types=["POLICY_FACT"], confidence=0.93, knowledge_backend=ctx.backend, retrieved_context=[c.text for c in ctx.chunks[:3]]), True

    if re.search(r"deductible|co-?pay", q):
        ded = policy.deductible
        copay = [c.text for c in condition_hits if "co-pay" in c.text.lower() or "copay" in c.text.lower() or "co-payment" in c.text.lower()]
        return PolicyAnswer(answer=(f"Your policy has a deductible of {_fmt_money(ded)} per reimbursement claim." if ded else "No deductible is stated in your policy.") + (f" {copay[0]}" if copay else ""), coverage="CONDITIONAL" if ded or copay else "YES", why="Deductible and co-payment terms from the policy conditions.", important_condition=copay[0] if copay else "", what_you_should_do="Expect the deductible to be reduced from any reimbursement.", source="Limits and conditions", fact_types=["POLICY_FACT"], confidence=0.92, knowledge_backend=ctx.backend, retrieved_context=[c.text for c in ctx.chunks[:3]]), True

    if coverage_hits:
        top = coverage_hits[0]
        text = top.text
        m = re.match(r"(.+?): covered=(YES|NO|CONDITIONAL)(?:; limit (.+?))?(?:; condition: (.+))?$", text)
        name, covered, limit, condition = (m.group(1), m.group(2), m.group(3), m.group(4)) if m else (text, "CONDITIONAL", None, None)
        exclusion_hits = [c.text for c in condition_hits if c.text.startswith("[Exclusion]")]
        if covered == "YES":
            answer = f"Yes — {name} is covered under your policy" + (f", up to {limit}" if limit else "") + "."
        elif covered == "NO":
            answer = f"No — {name} is not covered under your policy."
        else:
            answer = f"{name} is covered subject to conditions" + (f" (limit {limit})" if limit else "") + "."
        return PolicyAnswer(
            answer=answer,
            coverage=covered,
            why=(condition or f"Listed in the coverage schedule as '{name}'.") + (f" Related exclusion: {exclusion_hits[0]}" if exclusion_hits and covered != "YES" else ""),
            important_condition=condition or (f"Limit: {limit}." if limit else ("Subject to the initial waiting period and policy exclusions." if covered == "YES" else "")),
            what_you_should_do=("Keep the itemised bill; charges above the limit are borne by you." if limit else ("Check with the insurer before treatment if this is planned." if covered == "CONDITIONAL" else ("Consider whether another policy covers this." if covered == "NO" else "No special action needed; keep all bills and reports."))),
            source=top.source or "Coverage schedule",
            fact_types=["POLICY_FACT"] + (["AI_INTERPRETATION"] if covered == "CONDITIONAL" else []),
            confidence=0.9,
            knowledge_backend=ctx.backend,
            retrieved_context=[c.text for c in ctx.chunks[:4]],
        ), True

    exclusion_hits = [c.text for c in condition_hits if c.text.startswith("[Exclusion]")]
    if exclusion_hits:
        return PolicyAnswer(answer=f"This appears to fall under a policy exclusion: {exclusion_hits[0].replace('[Exclusion] ', '')}.", coverage="NO", why="Matched the exclusions section of your policy.", important_condition="Exclusions may have exceptions (e.g. accident-related). Confirm with the insurer for your specific case.", what_you_should_do="If your situation is accident-related, mention that when filing.", source="Exclusions", fact_types=["POLICY_FACT", "AI_INTERPRETATION"], confidence=0.8, knowledge_backend=ctx.backend, retrieved_context=[c.text for c in ctx.chunks[:3]]), True

    if ctx.chunks:
        return PolicyAnswer(answer="Here is what your policy says about this: " + ctx.chunks[0].text[:300], coverage="UNKNOWN", why="Closest matching policy text.", important_condition="", what_you_should_do="Confirm the specific scenario with the insurer if it is not explicit.", source=ctx.chunks[0].source or "Policy document", fact_types=["POLICY_FACT", "AI_INTERPRETATION"], confidence=0.6, knowledge_backend=ctx.backend, retrieved_context=[c.text for c in ctx.chunks[:3]]), False

    return PolicyAnswer(answer="I could not find this in your policy document.", coverage="UNKNOWN", why="No matching coverage, condition or exclusion was found.", important_condition="Absence in the document does not mean it is covered or excluded.", what_you_should_do="Ask the insurer directly, or upload the full policy wording for a more complete answer.", source="", fact_types=["MISSING_INFORMATION"], confidence=0.4, knowledge_backend=ctx.backend, retrieved_context=[]), False


def answer_question(db: Session, policy: Policy, question: str, language: str = "en") -> PolicyAnswer:
    lang = normalise(language)
    ks = get_policy_knowledge_service(db)
    ctx = ks.get_policy_context(policy.id, question)
    base, confident = _deterministic(policy, question, ctx)

    sarvam = get_sarvam()
    if sarvam.enabled:
        context_text = "\n".join(f"- ({c.kind}, {c.source}) {c.text}" for c in ctx.chunks[:8]) or "(no matching policy text)"
        system = SYSTEM_STYLE + "\nAnswer ONLY from the policy context. If the context does not answer the question, set coverage to UNKNOWN and fact_types to MISSING_INFORMATION. " + language_instruction(lang)
        user = (
            f"POLICY: {policy.policy_type} — {policy.plan_name or policy.insurer}, sum insured {_fmt_money(policy.sum_insured)}, waiting period {policy.waiting_period_days} days, deductible {_fmt_money(policy.deductible)}.\n"
            f"POLICY CONTEXT:\n{context_text}\n\nDETERMINISTIC PRE-ANSWER (trust its coverage value when confident={confident}): {base.model_dump_json()}\n\nQUESTION: {question}"
        )
        ai = sarvam.structured(system, user, PolicyAnswer)
        if ai:
            if confident and ai.coverage != base.coverage:
                ai.coverage = base.coverage  # the AI may explain, not override
            ai.knowledge_backend = ctx.backend
            ai.retrieved_context = base.retrieved_context
            ai.source = ai.source or base.source
            if "AI_INTERPRETATION" not in ai.fact_types:
                ai.fact_types.append("AI_INTERPRETATION")
            record_audit(db, AuditAction.POLICY_QUESTION_ANSWERED, actor=Actor.AI, user_id=policy.user_id, metadata={"policy_id": policy.id, "question": question, "coverage": ai.coverage, "backend": ctx.backend, "source": "sarvam"})
            return ai

    if lang != "en":
        base.answer = localize(base.answer, lang)
        base.why = localize(base.why, lang)
        base.important_condition = localize(base.important_condition, lang)
        base.what_you_should_do = localize(base.what_you_should_do, lang)
    record_audit(db, AuditAction.POLICY_QUESTION_ANSWERED, actor=Actor.SYSTEM, user_id=policy.user_id, metadata={"policy_id": policy.id, "question": question, "coverage": base.coverage, "backend": ctx.backend, "source": "deterministic"})
    return base
