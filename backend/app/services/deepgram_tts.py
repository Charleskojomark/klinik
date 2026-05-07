"""
Klinik — Deepgram TTS Service
Generates ultra-realistic speech audio using Deepgram Aura.
Uses a module-level httpx client for connection pooling (#13 fix).
"""

import logging
import base64
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)

# Module-level client — reuses TCP connections instead of creating a new one per call
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=15.0)
    return _http_client


async def generate_tts_audio_b64(text: str) -> str:
    """
    Generates TTS audio using Deepgram Aura.
    Returns the audio payload as a Base64 encoded string (MP3 format).
    Returns empty string if Deepgram is not configured or fails.
    """
    settings = get_settings()

    if not settings.deepgram_api_key:
        logger.warning("Deepgram API key not set. Skipping TTS generation.")
        return ""

    if not text or not text.strip():
        return ""

    # aura-luna-en: warm, natural, human-sounding female voice — best for clinical AI
    url = "https://api.deepgram.com/v1/speak?model=aura-luna-en&encoding=mp3&sample_rate=16000"
    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        "Content-Type": "application/json",
    }

    try:
        client = _get_client()
        response = await client.post(url, headers=headers, json={"text": text})
        response.raise_for_status()
        b64_encoded = base64.b64encode(response.content).decode("utf-8")
        logger.info(f"✅ Deepgram TTS generated ({len(response.content):,} bytes)")
        return b64_encoded
    except httpx.TimeoutException:
        logger.error("Deepgram TTS timed out after 15s")
        return ""
    except Exception as e:
        logger.error(f"Failed to generate Deepgram TTS: {e}")
        return ""
