import logging
import base64
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

async def generate_tts_audio_b64(text: str) -> str:
    """
    Generates ultra-realistic TTS audio using Deepgram Aura.
    Returns the audio payload as a Base64 encoded string (MP3 format).
    """
    if not settings.deepgram_api_key:
        logger.warning("Deepgram API key not set. Skipping TTS generation.")
        return ""

    url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en"
    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "text": text
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            response.raise_for_status()
            
            audio_bytes = response.content
            b64_encoded = base64.b64encode(audio_bytes).decode('utf-8')
            logger.info("Successfully generated Deepgram TTS audio.")
            return b64_encoded
            
    except Exception as e:
        logger.error(f"Failed to generate Deepgram TTS: {e}")
        return ""
