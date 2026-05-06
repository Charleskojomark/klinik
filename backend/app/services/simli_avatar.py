"""
Klinik — Simli Avatar Service
Takes Base64 MP3 audio (from Deepgram TTS) and returns a Base64 MP4 video
of the photorealistic avatar speaking the clinical summary.
Uses Simli's REST audio-to-video endpoint.
"""

import logging
import base64
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def generate_simli_session_token(audio_b64: str) -> str:
    """
    Sends Base64 audio to Simli REST API and returns a WebRTC session_token.
    The frontend uses this token to stream lip-synced video.
    Returns empty string on failure.
    """
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
        "apiKey": settings.simli_api_key, # apiKey belongs in body for this endpoint
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            session_token = data.get("session_token") or ""
            if session_token:
                logger.info("✅ Simli WebRTC session token generated successfully.")
                return session_token
            else:
                logger.warning(f"Simli returned unexpected response: {list(data.keys())}")
                return ""

    except httpx.HTTPStatusError as e:
        logger.error(f"Simli API HTTP error {e.response.status_code}: {e.response.text[:200]}")
        return ""
    except Exception as e:
        logger.error(f"Simli avatar generation failed: {e}")
        return ""
