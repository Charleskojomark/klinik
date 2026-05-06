"""
Klinik — Transcription Agent
Converts audio input to text. In production, uses LiveKit STT pipeline.
For hackathon demo, also accepts direct text input.
"""

import logging
from datetime import datetime
from app.models.clinical_state import ClinicalState, AgentStatus

logger = logging.getLogger(__name__)

AGENT_NAME = "transcription"


async def run_transcription_agent(state: ClinicalState) -> ClinicalState:
    """
    Agent 1 — Transcription (Sequential Phase 1)
    
    In production: receives real-time audio from LiveKit and converts to text.
    For demo/development: the transcript may already be provided as text input.
    """
    state.set_agent_status(AGENT_NAME, AgentStatus.RUNNING)
    logger.info(f"[{AGENT_NAME}] Starting transcription...")

    try:
        if state.transcript:
            # Text was provided directly (demo mode)
            logger.info(f"[{AGENT_NAME}] Using provided transcript ({len(state.transcript)} chars)")
        elif state.raw_audio_path:
            # In production: process audio through LiveKit STT
            # For now, placeholder for LiveKit integration
            logger.info(f"[{AGENT_NAME}] Processing audio from: {state.raw_audio_path}")
            state.transcript = "[Audio transcription would be processed here via LiveKit STT]"
        else:
            raise ValueError("No transcript or audio path provided")

        state.set_agent_status(
            AGENT_NAME, AgentStatus.COMPLETED,
            output=f"Transcribed {len(state.transcript)} characters"
        )

    except Exception as e:
        logger.error(f"[{AGENT_NAME}] Failed: {e}")
        state.set_agent_status(AGENT_NAME, AgentStatus.FAILED, error=str(e))

    return state
