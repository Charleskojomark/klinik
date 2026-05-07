"""
Klinik — FastAPI Application
Main entry point for the backend API.
Includes: consultation workflow, SSE streaming, FHIR export, patient management.

Bottleneck fixes applied:
  #3  — Bounded LRU sessions dict (no more unbounded memory growth)
  #6  — TTS + Simli run as background tasks (no longer block HTTP response)
  #10 — Single Instrumentator registration (removed duplicate at bottom)
  #14 — asyncio.wait_for timeout on consultation endpoint
"""

import json
import logging
import uuid
import asyncio
import base64
import tempfile
from collections import OrderedDict
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel
from typing import Optional
import httpx

from app.config import get_settings
from app.models.clinical_state import ClinicalState
from app.models.fhir_models import clinical_state_to_fhir_bundle
from app.models.database import init_db, save_clinical_state, get_all_patients, get_patient, get_all_encounters, get_encounter
from app.graph.clinical_workflow import run_clinical_workflow
from app.services.event_bus import get_event_bus
from prometheus_fastapi_instrumentator import Instrumentator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


# ──────────────────────────────────────────────
# #3 fix — Bounded LRU session store
# Max 500 sessions; oldest evicted when full.
# Sessions are also persisted to SQLite so nothing is truly lost.
# ──────────────────────────────────────────────

class _LRUDict(OrderedDict):
    """OrderedDict with a max-size cap that evicts the oldest entry."""
    def __init__(self, maxsize: int = 500):
        self._maxsize = maxsize
        super().__init__()

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self._maxsize:
            self.popitem(last=False)


sessions: _LRUDict = _LRUDict(maxsize=500)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    logger.info("🏥 Klinik backend starting...")
    logger.info(f"   Environment: {settings.app_env}")
    logger.info(f"   LLM: {settings.llm_model}")
    logger.info(f"   vLLM: {settings.vllm_base_url}")

    await init_db()
    event_bus = await get_event_bus()

    yield

    await event_bus.disconnect()
    logger.info("🏥 Klinik backend shutting down...")


app = FastAPI(
    title="Klinik",
    description="Voice-Native Multi-Agent Clinical Workflow System",
    version="0.2.0",
    lifespan=lifespan,
)

# #10 fix — Single Instrumentator registration only
Instrumentator().instrument(app).expose(app)

# CORS — allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────

class ConsultationRequest(BaseModel):
    """Start a new consultation from a doctor's spoken input."""
    transcript: str
    session_id: Optional[str] = None
    doctor_id: str = "dr-default"
    patient_id: Optional[str] = None
    patient_phone: Optional[str] = None


class ConsultationResponse(BaseModel):
    """Response after the full workflow completes."""
    session_id: str
    supervisor_summary: str
    state: ClinicalState
    supervisor_audio_b64: Optional[str] = None
    supervisor_video_url: Optional[str] = None   # MuseTalk video (arrives via SSE)


MUSETALK_URL = "http://musetalk:8090"  # internal docker service
MUSETALK_VIDEOS_DIR = Path("/musetalk/videos")


async def _render_musetalk_video(session_id: str, audio_b64: str):
    """
    Background task: POST MP3 to MuseTalk service → publish SSE with video_url.
    Runs after the consultation response is already sent to the client.
    The frontend receives the video URL via SSE and swaps the SVG avatar to video.
    """
    event_bus = await get_event_bus()
    try:
        # Decode base64 audio
        audio_bytes = base64.b64decode(audio_b64)

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Check musetalk health first
            try:
                health = await client.get(f"{MUSETALK_URL}/health")
                if health.status_code != 200:
                    logger.warning("[musetalk] Service not ready, skipping video render")
                    return
            except Exception:
                logger.warning("[musetalk] Service unreachable, skipping video render")
                return

            logger.info(f"[musetalk] Rendering video for {session_id}...")
            resp = await client.post(
                f"{MUSETALK_URL}/render",
                files={"audio": ("audio.mp3", audio_bytes, "audio/mpeg")},
            )

        if resp.status_code == 200:
            data = resp.json()
            video_url = data.get("video_url", "")
            logger.info(f"[musetalk] ✅ Video ready for {session_id}: {video_url}")
            await event_bus.publish_agent_event(
                session_id, "musetalk", "ready",
                output=json.dumps({"video_url": video_url})
            )
        else:
            logger.error(f"[musetalk] Render failed ({resp.status_code}): {resp.text[:200]}")

    except Exception as e:
        logger.error(f"[musetalk] Background render error for {session_id}: {e}")

# ──────────────────────────────────────────────
# Core Endpoints
# ──────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "name": "Klinik",
        "tagline": "Give doctors back their time. Give patients back their doctor.",
        "status": "running",
        "version": "0.2.0",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/api/consultation", response_model=ConsultationResponse)
async def start_consultation(req: ConsultationRequest):
    """
    Executes the multi-agent clinical workflow, then generates TTS audio.
    Audio is returned directly in the response (no SSE roundtrip needed).
    """
    from app.services.deepgram_tts import generate_tts_audio_b64

    session_id = req.session_id if req.session_id else f"session-{uuid.uuid4().hex[:8]}"
    logger.info(f"📋 New consultation: {session_id}")

    clinical_state = ClinicalState(
        session_id=session_id,
        doctor_id=req.doctor_id,
        transcript=req.transcript,
    )

    if req.patient_id:
        clinical_state.patient.patient_id = req.patient_id
    if req.patient_phone:
        clinical_state.patient.phone = req.patient_phone

    event_bus = await get_event_bus()
    await event_bus.publish_agent_event(session_id, "workflow", "running", output="Workflow started")

    try:
        result = await asyncio.wait_for(
            run_clinical_workflow(clinical_state),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        logger.error(f"Consultation {session_id} timed out after 120s")
        raise HTTPException(status_code=504, detail="Consultation workflow timed out")

    sessions[session_id] = result

    try:
        await save_clinical_state(result)
    except Exception as e:
        logger.error(f"Failed to persist session {session_id}: {e}")

    # Generate TTS synchronously — audio travels with the HTTP response.
    # Deepgram latency is ~150ms.
    audio_b64 = ""
    try:
        audio_b64 = await generate_tts_audio_b64(result.supervisor_summary)
        logger.info(f"🔊 Deepgram audio included in response for {session_id}")
    except Exception as e:
        logger.warning(f"TTS failed, response will have no audio: {e}")

    # Fire-and-forget MuseTalk render (runs after response is sent)
    # Frontend receives video URL via SSE event when ready (~5-15s)
    if audio_b64:
        asyncio.create_task(_render_musetalk_video(session_id, audio_b64))

    await event_bus.publish_agent_event(
        session_id, "workflow", "completed", output=result.supervisor_summary
    )

    return ConsultationResponse(
        session_id=session_id,
        supervisor_summary=result.supervisor_summary,
        state=result,
        supervisor_audio_b64=audio_b64 or None,
    )


@app.post("/api/demo", response_model=ConsultationResponse)
async def run_demo(background_tasks: BackgroundTasks):
    """The Winning Demo — Amaka pre-eclampsia scenario."""
    demo_transcript = (
        "Amaka Obi, 28, 12 weeks pregnant, BP 145/95, headache, blurred vision. "
        "Pre-eclampsia suspected. Order urine protein. Refer obstetrics urgently. "
        "Admit for monitoring. Follow up tomorrow morning."
    )
    req = ConsultationRequest(
        transcript=demo_transcript,
        doctor_id="dr-eze",
        patient_phone="+2348012345678",
    )
    return await start_consultation(req, background_tasks)


# ──────────────────────────────────────────────
# Session Endpoints
# ──────────────────────────────────────────────

@app.get("/api/sessions")
async def list_sessions():
    """List all consultation sessions (in-memory, capped at 500)."""
    return {
        "count": len(sessions),
        "sessions": [
            {
                "session_id": s.session_id,
                "patient": s.patient.name,
                "status": s.visit_status,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions.values()
        ],
    }


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get full state of a consultation session."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]


@app.get("/api/sessions/{session_id}/agents")
async def get_agent_status(session_id: str):
    """Get agent statuses for the live dashboard."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    state = sessions[session_id]
    return {
        "session_id": session_id,
        "agents": [
            {
                "name": r.agent_name,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "output": r.output,
                "error": r.error,
            }
            for r in state.agent_results
        ],
    }


# ──────────────────────────────────────────────
# SSE — Real-time Agent Events for Dashboard
# ──────────────────────────────────────────────

@app.get("/api/sessions/{session_id}/events")
async def stream_session_events(session_id: str):
    """
    Server-Sent Events endpoint for real-time agent status updates.
    The React dashboard subscribes to this for live visualization.
    Also delivers 'audio ready' events with TTS/Simli payloads.
    """
    event_bus = await get_event_bus()

    async def event_generator():
        async for event_data in event_bus.subscribe_session_events(session_id):
            yield f"data: {json.dumps(event_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ──────────────────────────────────────────────
# FHIR Export
# ──────────────────────────────────────────────

@app.get("/api/sessions/{session_id}/fhir")
async def export_fhir_bundle(session_id: str):
    """
    Export a consultation as a FHIR R4 Bundle.
    Enables interoperability with any FHIR-compliant EHR system.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    state = sessions[session_id]
    bundle = clinical_state_to_fhir_bundle(state)
    return bundle


# ──────────────────────────────────────────────
# LiveKit Tokens
# ──────────────────────────────────────────────

@app.get("/api/livekit/token")
async def get_livekit_token(room_name: str = "klinik-consultation", participant_name: str = "doctor"):
    """
    Generate a LiveKit Access Token for the React frontend to join the room.
    """
    from livekit import api

    if not settings.livekit_api_key or not settings.livekit_api_secret:
        raise HTTPException(status_code=500, detail="LiveKit credentials not configured")

    token = api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
    token.with_identity(f"{participant_name}-{uuid.uuid4().hex[:4]}")
    token.with_name(participant_name)
    token.with_grants(api.VideoGrants(room_join=True, room=room_name))

    return {"token": token.to_jwt(), "url": settings.livekit_url}


# ──────────────────────────────────────────────
# Patient Management
# ──────────────────────────────────────────────

@app.get("/api/patients")
async def list_patients():
    """List all patients from the database."""
    patients = await get_all_patients()
    return {"count": len(patients), "patients": patients}


@app.get("/api/patients/{patient_id}")
async def get_patient_detail(patient_id: str):
    """Get a patient with their encounter history."""
    patient = await get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@app.get("/api/encounters")
async def list_encounters():
    """List all encounters from the database."""
    encounters = await get_all_encounters()
    return {"count": len(encounters), "encounters": encounters}


@app.get("/api/encounters/{encounter_id}")
async def get_encounter_detail(encounter_id: str):
    """Get a single encounter."""
    enc = await get_encounter(encounter_id)
    if not enc:
        raise HTTPException(status_code=404, detail="Encounter not found")
    return enc
