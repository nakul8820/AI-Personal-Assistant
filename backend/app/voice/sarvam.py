"""Sarvam STT (Saarika) + TTS (Bulbul) over REST. Failures -> VoiceServiceError."""

import base64
import logging

import httpx

from app.core.config import get_settings
from app.core.errors import VoiceServiceError

logger = logging.getLogger("voice.sarvam")

_STT_URL = "https://api.sarvam.ai/speech-to-text"
_TTS_URL = "https://api.sarvam.ai/text-to-speech"


def _headers() -> dict:
    return {"api-subscription-key": get_settings().sarvam_api_key}


def transcribe(audio: bytes, filename: str = "audio.wav") -> tuple[str, str]:
    """Return (transcript, language_code). Auto-detects language + code-mixing."""
    # Detect mimetype dynamically to avoid 400 errors from strict APIs
    content_type = "audio/wav"
    clean_fn = filename.lower()
    if clean_fn.endswith(".webm"):
        content_type = "audio/webm"
    elif clean_fn.endswith(".mp3"):
        content_type = "audio/mpeg"
    elif clean_fn.endswith(".ogg") or clean_fn.endswith(".opus"):
        content_type = "audio/ogg"

    try:
        r = httpx.post(
            _STT_URL,
            headers=_headers(),
            files={"file": (filename, audio, content_type)},
            data={"model": "saarika:v2.5", "language_code": "unknown"},
            timeout=60,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error("Sarvam STT HTTP error %d: %s", e.response.status_code, e.response.text)
        raise VoiceServiceError(f"Sarvam STT failed: {e.response.text[:200]}")
    except httpx.HTTPError as e:
        logger.error("Sarvam STT connection error: %s", e)
        raise VoiceServiceError(f"Sarvam STT unreachable: {e}")
    data = r.json()
    return data.get("transcript", ""), data.get("language_code", "en-IN")


# Sarvam TTS wants a BCP-47 code; map the LLM's short hints too.
_LANG_MAP = {"hi": "hi-IN", "en": "en-IN", "hinglish": "hi-IN"}


def speak(text: str, language: str = "en-IN") -> bytes:
    """Return WAV bytes for `text` in `language`."""
    lang = _LANG_MAP.get(language, language) if len(language) <= 2 else language
    try:
        r = httpx.post(
            _TTS_URL,
            headers={**_headers(), "Content-Type": "application/json"},
            json={
                "inputs": [text[:1500]],
                "target_language_code": lang or "en-IN",
                "speaker": "anushka",
                "model": "bulbul:v2",
            },
            timeout=60,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise VoiceServiceError(f"Sarvam TTS unavailable: {e}")
    audios = r.json().get("audios", [])
    if not audios:
        raise VoiceServiceError("Sarvam TTS returned no audio.")
    return base64.b64decode(audios[0])
