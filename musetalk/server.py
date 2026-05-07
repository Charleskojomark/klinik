"""
MuseTalk FastAPI Service — Klinik Dr. Aria Avatar
Wraps MuseTalk v1.5 inference as a REST microservice.

Endpoints:
  GET  /health           → { "status": "ready" | "loading" }
  POST /render           → { "video_url": "/videos/<job_id>.mp4" }
  GET  /videos/<file>    → static video file

Flow:
  1. Startup: load models + pre-process avatar face landmarks
  2. POST /render: receive MP3 → save temp → run MuseTalk → return video URL
"""

import asyncio
import logging
import os
import subprocess
import sys
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ── Config ──────────────────────────────────────────────────────
AVATAR_PATH   = Path("/musetalk/data/aria_avatar.jpg")
OUTPUT_DIR    = Path("/musetalk/videos")
MODELS_DIR    = Path("/musetalk/models")
MUSETALK_ROOT = Path("/musetalk")

# snapshot_download nests repo dirs: models/musetalkV15/musetalkV15/unet.pth
UNET_MODEL    = MODELS_DIR / "musetalkV15" / "musetalkV15" / "unet.pth"
UNET_CONFIG   = MODELS_DIR / "musetalkV15" / "musetalkV15" / "musetalk.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("musetalk-server")

# ── Server state ─────────────────────────────────────────────────
_ready = False
_avatar_prep_dir = None   # pre-processed avatar directory (cached landmarks)


def _run_avatar_preparation():
    """Pre-process Dr. Aria avatar face landmarks once at startup."""
    global _avatar_prep_dir
    prep_dir = MUSETALK_ROOT / "data" / "aria_prep"
    prep_dir.mkdir(parents=True, exist_ok=True)

    log.info("🎭 Pre-processing Dr. Aria avatar landmarks...")
    result = subprocess.run(
        [
            sys.executable, "-m", "scripts.realtime_inference",
            "--inference_config", "configs/inference/realtime.yaml",
            "--video_path", str(AVATAR_PATH),
            "--result_dir", str(prep_dir),
            "--unet_model_path", str(UNET_MODEL),
            "--unet_config", str(UNET_CONFIG),
            "--version", "v15",
            "--preparation", "True",      # preparation mode only
            "--fps", "25",
        ],
        cwd=str(MUSETALK_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode == 0:
        _avatar_prep_dir = str(prep_dir)
        log.info(f"✅ Avatar pre-processed → {prep_dir}")
    else:
        log.error(f"⚠️  Avatar prep failed (will retry on first render):\n{result.stderr[-500:]}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ready
    log.info("🚀 MuseTalk service starting...")

    # Check models exist
    if not UNET_MODEL.exists():
        log.warning("⚠️  Model weights not found — run download_weights.sh on the droplet first")
        log.warning(f"   Expected: {UNET_MODEL}")
    elif not AVATAR_PATH.exists():
        log.warning(f"⚠️  Avatar image not found: {AVATAR_PATH}")
    else:
        # Pre-process avatar in thread (blocking, takes ~30s first time)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _run_avatar_preparation)

    _ready = True
    log.info("🟢 MuseTalk service ready")
    yield
    log.info("🔴 MuseTalk service shutting down")


app = FastAPI(title="MuseTalk Service", lifespan=lifespan)

# Serve rendered videos as static files
app.mount("/videos", StaticFiles(directory=str(OUTPUT_DIR)), name="videos")


# ── Health endpoint ────────────────────────────────────────────
@app.get("/health")
async def health():
    if not _ready:
        return JSONResponse({"status": "loading"}, status_code=503)
    models_ok = UNET_MODEL.exists()
    avatar_ok = AVATAR_PATH.exists()
    return {
        "status": "ready" if (models_ok and avatar_ok) else "degraded",
        "models_loaded": models_ok,
        "avatar_ready": avatar_ok,
        "avatar_prepped": _avatar_prep_dir is not None,
    }


# ── Render endpoint ────────────────────────────────────────────
@app.post("/render")
async def render_video(audio: UploadFile = File(...)):
    """
    Accept an MP3 audio file, render MuseTalk video, return URL.
    Blocking call — takes 5-15s on MI300X.
    """
    if not _ready:
        raise HTTPException(503, "Service not ready")
    if not UNET_MODEL.exists():
        raise HTTPException(503, "Model weights not downloaded")

    job_id = uuid.uuid4().hex[:8]
    audio_path = Path(f"/tmp/musetalk_{job_id}.mp3")
    job_output_dir = OUTPUT_DIR / job_id

    # Save uploaded audio
    try:
        audio_bytes = await audio.read()
        audio_path.write_bytes(audio_bytes)
        log.info(f"🎵 [{job_id}] Audio received ({len(audio_bytes)/1024:.0f}KB)")
    except Exception as e:
        raise HTTPException(500, f"Failed to save audio: {e}")

    # Build inference command
    cmd = [
        sys.executable, "-m", "scripts.realtime_inference",
        "--inference_config", "configs/inference/realtime.yaml",
        "--video_path", str(AVATAR_PATH),
        "--result_dir", str(job_output_dir),
        "--unet_model_path", str(UNET_MODEL),
        "--unet_config", str(UNET_CONFIG),
        "--version", "v15",
        "--fps", "25",
        "--preparation", "False",
        "--skip_save_images",
    ]

    # If avatar was pre-processed, point to cached landmarks
    # (MuseTalk checks for prep data in result_dir parent)
    if _avatar_prep_dir:
        cmd += ["--avatar_id", "aria_prep"]

    # Run inference (in executor to avoid blocking event loop)
    log.info(f"🎬 [{job_id}] Rendering...")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                cwd=str(MUSETALK_ROOT),
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "PYTHONPATH": str(MUSETALK_ROOT)},
            )
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Render timeout (>120s)")
    except Exception as e:
        raise HTTPException(500, f"Render failed: {e}")
    finally:
        audio_path.unlink(missing_ok=True)

    if result.returncode != 0:
        log.error(f"❌ [{job_id}] Render failed:\n{result.stderr[-500:]}")
        raise HTTPException(500, f"MuseTalk error: {result.stderr[-200:]}")

    # Find the output video file
    video_file = None
    for ext in ["*.mp4", "*.avi"]:
        found = list(job_output_dir.rglob(ext))
        if found:
            video_file = found[0]
            break

    if not video_file or not video_file.exists():
        raise HTTPException(500, "Render completed but no video file found")

    # Move to flat output dir for easy serving
    final_path = OUTPUT_DIR / f"{job_id}.mp4"
    video_file.rename(final_path)

    log.info(f"✅ [{job_id}] Render complete → {final_path.name}")
    return {"video_url": f"/musetalk-video/{job_id}.mp4", "job_id": job_id}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="info")
