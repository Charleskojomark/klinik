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
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from app.config import get_settings
from app.models.clinical_state import ClinicalState
from app.models.fhir_models import clinical_state_to_fhir_bundle
from app.models.database import init_db, save_clinical_state, get_all_patients, get_patient, get_all_encounters, get_encounter
from app.graph.clinical_workflow import run_clinical_workflow
from app.services.event_bus import get_event_bus
from app.services.auth import get_current_user, RoleChecker
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

# CORS — allow frontend (localhost dev + production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://localhost:5174",
        "https://klinik.charlesmark.xyz",
        "http://klinik.charlesmark.xyz",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def audit_log_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    
    # Run audit logging in background to avoid blocking
    if request.url.path.startswith("/api/"):
        from app.models.database import log_audit_event
        asyncio.create_task(
            log_audit_event(
                ip_address=request.client.host if request.client else "unknown",
                endpoint=request.url.path,
                method=request.method,
                status_code=response.status_code,
                duration_ms=duration_ms
            )
        )
    return response


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
    supervisor_audio_b64: Optional[str] = None   # populated asynchronously via SSE
    supervisor_simli_token: Optional[str] = None  # populated asynchronously via SSE


# (Background audio task removed — TTS is now generated synchronously
#  and returned directly in the POST response for zero SSE roundtrip latency)



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


@app.post("/api/auth/login")
async def login(request: Request):
    """
    Unified JSON & Form Login.
    Supports application/json for the React frontend and Form data for Swagger UI.
    """
    from app.models.database import get_user_by_username
    from app.services.auth import verify_password, create_access_token

    username = None
    password = None

    # Determine content type and extract credentials
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            username = body.get("username")
            password = body.get("password")
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            username = form.get("username")
            password = form.get("password")
        except Exception:
            pass

    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = await get_user_by_username(username)
    if not user or not verify_password(user["password_hash"], password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token({"sub": user["username"], "role": user["role"], "name": user["name"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "name": user["name"]
        }
    }


@app.get("/api/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Retrieve the current logged-in user details."""
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "role": current_user["role"],
        "name": current_user["name"]
    }


@app.get("/api/admin/audit-logs")
async def get_audit_logs(current_user: dict = Depends(RoleChecker(["admin"]))):
    """Retrieve the system audit logs (admin only)."""
    from app.models.database import _get_conn
    conn = await _get_conn()
    try:
        cursor = conn.execute("""
            SELECT id, timestamp, ip_address, endpoint, method, status_code, duration_ms
            FROM audit_logs
            ORDER BY timestamp DESC
            LIMIT 100
        """)
        logs = [
            {
                "id": r[0],
                "timestamp": r[1],
                "ip_address": r[2],
                "endpoint": r[3],
                "method": r[4],
                "status_code": r[5],
                "duration_ms": r[6]
            }
            for r in cursor.fetchall()
        ]
        return {"logs": logs}
    except Exception as e:
        logger.error(f"Failed to fetch audit logs: {e}")
        raise HTTPException(status_code=500, detail="Database error fetching logs")



@app.post("/api/consultation", response_model=ConsultationResponse)
async def start_consultation(
    req: ConsultationRequest,
    current_user: dict = Depends(RoleChecker(["doctor", "nurse"]))
):
    """
    Executes the multi-agent clinical workflow, then generates TTS audio.
    Audio is returned directly in the response (no SSE roundtrip needed).
    """
    from app.services.deepgram_tts import generate_tts_audio_b64

    session_id = req.session_id if req.session_id else f"session-{uuid.uuid4().hex[:8]}"
    logger.info(f"📋 New consultation: {session_id} by {current_user['name']}")

    clinical_state = ClinicalState(
        session_id=session_id,
        doctor_id=current_user["id"],
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

    # Generate TTS synchronously — audio travels with the HTTP response,
    # no SSE polling roundtrip needed. Deepgram latency is ~150ms.
    audio_b64 = ""
    try:
        audio_b64 = await generate_tts_audio_b64(result.supervisor_summary)
        logger.info(f"🔊 Deepgram audio included in response for {session_id}")
    except Exception as e:
        logger.warning(f"TTS failed, response will have no audio: {e}")

    await event_bus.publish_agent_event(
        session_id, "workflow", "completed", output=result.supervisor_summary
    )

    return ConsultationResponse(
        session_id=session_id,
        supervisor_summary=result.supervisor_summary,
        state=result,
        supervisor_audio_b64=audio_b64 or None,
        supervisor_simli_token=None,
    )


@app.post("/api/demo", response_model=ConsultationResponse)
async def run_demo(current_user: dict = Depends(RoleChecker(["doctor", "nurse", "admin"]))):
    """The Winning Demo — Amaka pre-eclampsia scenario."""
    demo_transcript = (
        "Amaka Obi, 28, 12 weeks pregnant, BP 145/95, headache, blurred vision. "
        "Pre-eclampsia suspected. Order urine protein. Refer obstetrics urgently. "
        "Admit for monitoring. Follow up tomorrow morning."
    )
    req = ConsultationRequest(
        transcript=demo_transcript,
        doctor_id=current_user["id"],
        patient_phone="+2348012345678",
    )
    return await start_consultation(req, current_user=current_user)


# ──────────────────────────────────────────────
# Session Endpoints
# ──────────────────────────────────────────────

@app.get("/api/sessions")
async def list_sessions(current_user: dict = Depends(get_current_user)):
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
async def get_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """Get full state of a consultation session."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]


@app.put("/api/sessions/{session_id}", response_model=ClinicalState)
async def update_session(
    session_id: str,
    updated_state: ClinicalState,
    current_user: dict = Depends(RoleChecker(["doctor"]))
):
    """
    Update the persisted clinical state after the doctor reviews and edits it.
    """
    sessions[session_id] = updated_state
    try:
        await save_clinical_state(updated_state)
    except Exception as e:
        logger.error(f"Failed to persist updated session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database save error: {e}")

    event_bus = await get_event_bus()
    await event_bus.publish_agent_event(
        session_id, "workflow", "committed", output=updated_state.supervisor_summary
    )

    return updated_state


@app.get("/api/sessions/{session_id}/agents")
async def get_agent_status(session_id: str, current_user: dict = Depends(get_current_user)):
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
async def stream_session_events(
    session_id: str,
    token: Optional[str] = None
):
    """
    Server-Sent Events endpoint for real-time agent status updates.
    We authenticate via token query parameter.
    """
    # Authenticate token query param fallback
    await get_current_user(token_param=token)

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
async def export_fhir_bundle(session_id: str, current_user: dict = Depends(get_current_user)):
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
async def get_livekit_token(
    room_name: str = "klinik-consultation",
    participant_name: str = "doctor",
    current_user: dict = Depends(get_current_user)
):
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
async def list_patients(current_user: dict = Depends(get_current_user)):
    """List all patients from the database."""
    patients = await get_all_patients()
    return {"count": len(patients), "patients": patients}


@app.get("/api/patients/{patient_id}")
async def get_patient_detail(patient_id: str, current_user: dict = Depends(get_current_user)):
    """Get a patient with their encounter history."""
    patient = await get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@app.get("/api/encounters")
async def list_encounters(current_user: dict = Depends(get_current_user)):
    """List all encounters from the database."""
    encounters = await get_all_encounters()
    return {"count": len(encounters), "encounters": encounters}


@app.get("/api/encounters/{encounter_id}")
async def get_encounter_detail(encounter_id: str, current_user: dict = Depends(get_current_user)):
    """Get a single encounter."""
    enc = await get_encounter(encounter_id)
    if not enc:
        raise HTTPException(status_code=404, detail="Encounter not found")
    return enc
