"""Journey Agent: explains claim tracking / journey status in plain language."""
from app.agents.lang import SYSTEM_STYLE, language_instruction, localize, normalise
from app.integrations.sarvam_client import get_sarvam
from app.schemas.api import ClaimTracking


def explain_tracking(tracking: ClaimTracking, language: str = "en") -> str:
    lang = normalise(language)
    deterministic = f"{tracking.what_happened} {tracking.what_is_pending} " + (f"Action needed from you: {tracking.next_step}" if tracking.user_action_required else f"Next step: {tracking.next_step}")
    sarvam = get_sarvam()
    if sarvam.enabled:
        stages = ", ".join(f"{s.label}={s.status}" for s in tracking.stages)
        text = sarvam.chat(
            [
                {"role": "system", "content": SYSTEM_STYLE + " Explain the claim status in 2-3 short sentences. Do not predict the decision. " + language_instruction(lang)},
                {"role": "user", "content": f"Claim {tracking.claim.claim_number}. State: {tracking.current_state_label}. Stages: {stages}. Facts: {deterministic}"},
            ],
            max_tokens=250,
        )
        if text:
            return text.strip()
    return localize(deterministic, lang)
