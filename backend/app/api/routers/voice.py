from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.agents.lang import normalise
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.integrations.sarvam_client import get_sarvam
from app.models import User
from app.schemas.api import TranscribeResponse, TranslateRequest, TranslateResponse, TTSRequest

router = APIRouter(prefix="/api", tags=["voice"])


@router.post("/voice/transcribe", response_model=TranscribeResponse)
async def transcribe(file: UploadFile = File(...), language: str | None = Form(None), user: User = Depends(get_current_user)):
    settings = get_settings()
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio too large")
    sarvam = get_sarvam()
    if not sarvam.enabled:
        raise HTTPException(status_code=503, detail="Voice input requires SARVAM_API_KEY to be configured.")
    result = sarvam.transcribe(content, file.filename or "audio.webm", file.content_type or "audio/webm", normalise(language) if language else None)
    if result is None:
        raise HTTPException(status_code=502, detail=f"Speech-to-text failed: {sarvam.last_error}")
    return TranscribeResponse(transcript=result.get("transcript", ""), language_code=result.get("language_code"), source="sarvam")


@router.post("/translate", response_model=TranslateResponse)
def translate(req: TranslateRequest, user: User = Depends(get_current_user)):
    sarvam = get_sarvam()
    src, tgt = normalise(req.source_language), normalise(req.target_language)
    if src == tgt:
        return TranslateResponse(translated_text=req.text, source="passthrough")
    if not sarvam.enabled:
        return TranslateResponse(translated_text=req.text, source="fallback-untranslated")
    out = sarvam.translate(req.text, src, tgt)
    if out is None:
        return TranslateResponse(translated_text=req.text, source="fallback-untranslated")
    return TranslateResponse(translated_text=out, source="sarvam")


@router.post("/voice/speak")
def speak(req: TTSRequest, user: User = Depends(get_current_user)):
    sarvam = get_sarvam()
    if not sarvam.enabled:
        raise HTTPException(status_code=503, detail="Text-to-speech requires SARVAM_API_KEY.")
    audio = sarvam.text_to_speech(req.text, normalise(req.language))
    if not audio:
        raise HTTPException(status_code=502, detail=f"Text-to-speech failed: {sarvam.last_error}")
    return {"audio_base64": audio, "format": "wav"}
