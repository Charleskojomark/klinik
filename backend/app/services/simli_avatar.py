"""
Klinik — Simli Avatar Service
Takes Base64 MP3 audio (from Deepgram TTS) and returns a WebRTC session token
for the photorealistic avatar lip-synced to the clinical summary.
Uses a module-level httpx client for connection pooling (#13 fix).
"""

import logging
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)

# Module-level client — reuses TCP connections instead of creating one per call
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=35.0)
    return _http_client


async def generate_simli_session_token(audio_b64: str) -> str:
    """
    Sends Base64 audio to Simli REST API and returns a WebRTC session_token.
    The frontend uses this token to stream lip-synced video.
    Returns empty string on failure or missing configuration.
    """
    settings = get_settings()

    if not settings.simli_api_key or not settings.simli_face_id:
        logger.warning("Simli API key or face_id not configured. Skipping avatar video.")
        return ""

    if not audio_b64:
        return ""

    url = "https://api.simli.ai/startAudioToVideoSession"
    payload = {
        "audioBase64": audio_b64,
        "faceId": settings.simli_face_id,
        "audioFormat": "mp3",
        "apiKey": settings.simli_api_key,
    }

    try:
        client = _get_client()
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        session_token = data.get("session_token") or ""
        if session_token:
            logger.info("✅ Simli WebRTC session token generated successfully.")
            return session_token
        else:
            logger.warning(f"Simli returned unexpected response keys: {list(data.keys())}")
            return ""

    except httpx.HTTPStatusError as e:
        logger.error(f"Simli API HTTP error {e.response.status_code}: {e.response.text[:200]}")
        return ""
    except httpx.TimeoutException:
        logger.error("Simli API timed out after 35s")
        return ""
    except Exception as e:
        logger.error(f"Simli avatar generation failed: {e}")
        return ""
