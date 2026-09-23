"""Sarvam AI adapter: chat completion (sarvam-105b), structured JSON output,
translation, speech-to-text and text-to-speech.

Fails gracefully: every method returns None (or a typed failure) when the API key
is missing or the service is unreachable so callers can use deterministic fallbacks.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.enums import SARVAM_LANGUAGE_CODES

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class SarvamClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.SARVAM_BASE_URL.rstrip("/")
        self.last_error: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return self.settings.sarvam_configured

    def _headers(self) -> Dict[str, str]:
        return {"api-subscription-key": self.settings.SARVAM_API_KEY}

    def status(self) -> Dict[str, Any]:
        return {
            "configured": self.enabled,
            "chat_model": self.settings.SARVAM_CHAT_MODEL,
            "stt_model": self.settings.SARVAM_STT_MODEL,
            "last_error": self.last_error,
        }

    # ---- Chat ----
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 900,
        json_mode: bool = False,
    ) -> Optional[str]:
        if not self.enabled:
            return None
        payload: Dict[str, Any] = {
            "model": self.settings.SARVAM_CHAT_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            with httpx.Client(timeout=self.settings.SARVAM_TIMEOUT_SECONDS) as client:
                resp = client.post(f"{self.base_url}/v1/chat/completions", headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
                if resp.status_code == 400 and json_mode:
                    # Some deployments reject response_format; retry without it.
                    payload.pop("response_format", None)
                    resp = client.post(f"{self.base_url}/v1/chat/completions", headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                self.last_error = None
                return content
        except Exception as exc:
            self.last_error = f"chat: {exc}"
            logger.warning("Sarvam chat failed: %s", exc)
            return None

    def structured(self, system_prompt: str, user_prompt: str, schema: Type[T], *, temperature: float = 0.1) -> Optional[T]:
        """Ask for JSON matching `schema`; validate with Pydantic. Returns None on any failure."""
        json_schema = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": system_prompt
                + "\n\nRespond ONLY with a single JSON object that validates against this JSON Schema. No prose, no markdown fences.\n"
                + json_schema,
            },
            {"role": "user", "content": user_prompt},
        ]
        raw = self.chat(messages, temperature=temperature, json_mode=True)
        if not raw:
            return None
        parsed = _extract_json(raw)
        if parsed is None:
            self.last_error = "structured: no JSON in response"
            return None
        try:
            return schema.model_validate(parsed)
        except ValidationError as exc:
            self.last_error = f"structured: schema validation failed ({exc.error_count()} errors)"
            logger.warning("Sarvam structured output failed validation: %s", exc)
            return None

    # ---- Translation ----
    def translate(self, text: str, source: str, target: str) -> Optional[str]:
        if not self.enabled or not text.strip():
            return None
        if source == target:
            return text
        payload = {
            "input": text[:2000],
            "source_language_code": SARVAM_LANGUAGE_CODES.get(source, "auto"),
            "target_language_code": SARVAM_LANGUAGE_CODES.get(target, target),
            "model": self.settings.SARVAM_TRANSLATE_MODEL,
            "mode": "formal",
        }
        try:
            with httpx.Client(timeout=self.settings.SARVAM_TIMEOUT_SECONDS) as client:
                resp = client.post(f"{self.base_url}/translate", headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
                resp.raise_for_status()
                return resp.json().get("translated_text")
        except Exception as exc:
            self.last_error = f"translate: {exc}"
            logger.warning("Sarvam translate failed: %s", exc)
            return None

    # ---- Speech to text ----
    def transcribe(self, audio_bytes: bytes, file_name: str, mime_type: str, language: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        data = {"model": self.settings.SARVAM_STT_MODEL}
        if language and language in SARVAM_LANGUAGE_CODES:
            data["language_code"] = SARVAM_LANGUAGE_CODES[language]
        else:
            data["language_code"] = "unknown"
        try:
            with httpx.Client(timeout=self.settings.SARVAM_TIMEOUT_SECONDS) as client:
                resp = client.post(
                    f"{self.base_url}/speech-to-text",
                    headers=self._headers(),
                    data=data,
                    files={"file": (file_name, audio_bytes, mime_type or "audio/wav")},
                )
                resp.raise_for_status()
                body = resp.json()
                return {"transcript": body.get("transcript", ""), "language_code": body.get("language_code")}
        except Exception as exc:
            self.last_error = f"stt: {exc}"
            logger.warning("Sarvam STT failed: %s", exc)
            return None

    # ---- Text to speech ----
    def text_to_speech(self, text: str, language: str) -> Optional[str]:
        """Returns base64-encoded audio (wav) or None."""
        if not self.enabled or not text.strip():
            return None
        payload = {
            "text": text[:1500],
            "target_language_code": SARVAM_LANGUAGE_CODES.get(language, "en-IN"),
            "speaker": "anushka",
            "model": self.settings.SARVAM_TTS_MODEL,
        }
        try:
            with httpx.Client(timeout=self.settings.SARVAM_TIMEOUT_SECONDS) as client:
                resp = client.post(f"{self.base_url}/text-to-speech", headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
                resp.raise_for_status()
                audios = resp.json().get("audios") or []
                return audios[0] if audios else None
        except Exception as exc:
            self.last_error = f"tts: {exc}"
            logger.warning("Sarvam TTS failed: %s", exc)
            return None


def _extract_json(raw: str) -> Optional[Any]:
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


_client: Optional[SarvamClient] = None


def get_sarvam() -> SarvamClient:
    global _client
    if _client is None:
        _client = SarvamClient()
    return _client
