# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Critical Non-Obvious Patterns

**LangGraph Graph Compilation**: The clinical workflow graph is compiled ONCE at module import time (`backend/app/graph/clinical_workflow.py:172`), NOT per request. Never rebuild the graph in request handlers.

**Bounded Session Store**: Sessions dict uses custom `_LRUDict` with 500-item cap (`backend/app/main.py:49-63`). Old sessions auto-evict but persist to SQLite, so nothing is lost.

**Parallel Agent Deep Copies**: Phase 2 agents receive `cs.model_copy(deep=True)` to prevent race conditions during concurrent execution (`backend/app/graph/clinical_workflow.py:84-89`). Results are manually merged back into master state.

**LLM JSON Extraction**: LLM responses often include markdown fences or explanatory text. Always use `_extract_json()` from `llm_client.py` which strips code blocks and finds JSON boundaries.

**Vitals Sanitization**: LLMs return descriptive strings like "fast" for heart_rate. Use `_to_int()` and `_to_float()` coercion helpers in `clinical_nlp.py:21-42` to convert or return None.

**Event Bus Fallback**: Redis event bus falls back to in-process log when Redis unavailable (`backend/app/services/event_bus.py:34`). SSE subscriptions replay existing events then poll for new ones.

**Frontend Audio Flow**: TTS audio is returned inline in POST response (`supervisor_audio_b64`), NOT via SSE. Avatar component receives base64 MP3 directly and streams to Simli.

**Docker Device Flags**: vLLM on ROCm requires `--device /dev/kfd --device /dev/dri --group-add video` or it silently runs on CPU with no error.

**Prescription Field Aliasing**: `Prescription` model accepts both `drug_name` and `medication` fields, normalizing in `__init__` (`backend/app/models/clinical_state.py:81-87`).

## Commands

```bash
# Backend (from project root)
cd backend && uvicorn app.main:app --reload --port 8080

# Frontend (from project root)  
cd frontend && npm run dev

# Full stack with Docker
docker compose up -d

# vLLM on AMD MI300X (requires ROCm)
docker run --device /dev/kfd --device /dev/dri --group-add video \
  -p 8001:8000 rocm/vllm:latest \
  --model meta-llama/Llama-3.1-70B-Instruct \
  --gpu-memory-utilization 0.90 --max-model-len 8192
```

## Architecture Notes

- **Phase 1 (Sequential)**: Transcription → Clinical NLP
- **Phase 2 (Parallel)**: 6 agents fire concurrently via `asyncio.gather`
- **Phase 3 (Sequential)**: Relationship → Supervisor
- LangGraph uses `MemorySaver` checkpointer with per-session thread_id
- Frontend SSE subscribes BEFORE POST to catch real-time agent events