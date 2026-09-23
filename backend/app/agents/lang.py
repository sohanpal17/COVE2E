"""Language helpers. Journey/policy/claim logic is language-independent; only
user-facing text is localised, via Sarvam translation when available."""
from typing import Optional

from app.integrations.sarvam_client import get_sarvam

SUPPORTED = {"en", "hi", "mr"}
LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi"}


def normalise(language: Optional[str]) -> str:
    lang = (language or "en").lower()[:2]
    return lang if lang in SUPPORTED else "en"


def localize(text: str, language: Optional[str]) -> str:
    """Translate English text to the target language via Sarvam. Falls back to English."""
    lang = normalise(language)
    if lang == "en" or not text:
        return text
    translated = get_sarvam().translate(text, "en", lang)
    return translated or text


SYSTEM_STYLE = (
    "You are COVE2E, an insurance journey teammate. Be precise, calm and honest. "
    "Never guarantee approval or payout. Never invent coverage, requirements or insurer decisions. "
    "Distinguish policy facts from interpretation. The insurer always makes the final decision. "
    "Prefer phrasing like 'appears ready for the next stage based on the available information'."
)


def language_instruction(language: Optional[str]) -> str:
    lang = normalise(language)
    if lang == "en":
        return "Respond in English."
    return f"Respond in {LANGUAGE_NAMES[lang]} (Devanagari script). Keep insurance terms understandable."
