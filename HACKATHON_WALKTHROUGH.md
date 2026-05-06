# Building Klinik: A Voice-Native Clinical AI with 8 Parallel Agents on AMD MI300X

**Author:** Charles Kojomark  
**Hackathon:** lablab.ai × AMD Developer Hackathon  
**Repo:** github.com/Charleskojomark/klinik  
**Live Demo:** https://klinik.charlesmark.xyz  

---

## The Problem

Doctors spend 2–4 hours per day on documentation. Every hour of admin is an hour not spent on patients. The bottleneck isn't knowledge — it's paperwork.

After a consultation, a doctor must write SOAP notes, order labs, send referrals, generate prescriptions, assign billing codes, schedule follow-ups, and notify the patient. Every task is mechanical. Every task is automatable.

Klinik solves this with a single voice input.

---

## What Klinik Does

A doctor speaks naturally after seeing a patient. Klinik transcribes the conversation, understands the clinical context, and dispatches 8 specialized AI agents that work in parallel to complete every downstream task — in under 14 seconds.

The doctor reviews the output. Dr. Aria (a talking AI avatar) reads the summary aloud. The patient gets an SMS. The encounter is saved to the EHR.

That's the entire workflow.

---

## Architecture

```
Doctor Voice Input
       │
       ▼
┌─────────────────┐
│  Transcription  │  ← Deepgram STT
│     Agent       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Clinical NLP   │  ← Llama 3.1 70B extracts: diagnoses,
│     Agent       │    symptoms, vitals, medications
└────────┬────────┘
         │
    ┌────┴─────────────────────────────────────┐
    │         6 Parallel Agents                │
    │                                          │
    │  ┌──────────┐  ┌──────────┐  ┌────────┐ │
    │  │   SOAP   │  │   Lab    │  │Referral│ │
    │  │  Notes   │  │  Orders  │  │Letters │ │
    │  └──────────┘  └──────────┘  └────────┘ │
    │  ┌──────────┐  ┌──────────┐  ┌────────┐ │
    │  │ Billing  │  │Scheduling│  │Patient │ │
    │  │ICD-10/CPT│  │Follow-up │  │  SMS   │ │
    │  └──────────┘  └──────────┘  └────────┘ │
    └────────────────────┬─────────────────────┘
                         │
                         ▼
               ┌─────────────────┐
               │    Supervisor   │  ← Compiles final summary
               │      Agent      │
               └────────┬────────┘
                        │
                        ▼
              Dr. Aria speaks summary
              Patient record saved
              SMS sent (Twilio)
```

**Why parallel agents?**  
Sequential execution of 6 agents at ~4.25s each = 25+ seconds.  
Parallel execution = 13.68 seconds total.  
The AMD MI300X makes this possible — enough memory and compute to handle concurrent LLM calls without serialization.

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| LLM | Llama 3.1 70B (full precision) | Clinical reasoning quality |
| Inference | vLLM + ROCm on AMD MI300X | OpenAI-compatible API, GPU-native |
| Orchestration | LangGraph | Native parallel agent support |
| Backend | FastAPI + Python | Async, fast, clean |
| Database | Turso (libSQL) | Edge-native, persistent EHR records |
| Message bus | Redis Cloud | Agent event streaming |
| STT | Deepgram | Real-time, medical vocabulary |
| TTS | Deepgram Aura | Natural voice synthesis |
| Avatar | Simli AI | WebRTC talking avatar |
| Video/Voice calls | LiveKit Cloud | Real-time WebRTC |
| Frontend | React + Vite | Fast, responsive UI |
| Reverse proxy | Caddy | Auto-SSL, simple config |
| Monitoring | Prometheus + Grafana | GPU + inference observability |
| SMS | Twilio | Patient notifications |
| Scheduling | Calendly API | Follow-up booking |

---

## Why AMD MI300X

This is not a marketing answer. Here is the specific technical reason MI300X mattered for this project.

**Llama 3.1 70B at BF16 requires ~140GB VRAM.**

On a 40GB A100: impossible without quantization.  
On a 80GB H100: impossible without quantization.  
On a 192GB MI300X: runs with 52GB to spare.

Quantization (4-bit, 8-bit) reduces memory requirements but degrades reasoning quality. For a clinical application — where a hallucinated drug interaction or missed contraindication has real consequences — running the full precision model is not a nice-to-have. It's a design requirement.

The MI300X is the only single-GPU solution that meets this requirement.

**Additional observations:**
- ROCm + vLLM is production-ready. The OpenAI-compatible API meant zero application code changes.
- `rocm-smi` provides more detailed power metrics than `nvidia-smi` — useful for monitoring energy efficiency.
- HBM3 memory bandwidth handles the parallel agent workload without memory bottlenecking.

---

## Real Performance Numbers

All metrics captured from a live deployment. No estimates.

### GPU Metrics (rocm-smi)
```
GPU Power Draw:        206W (during inference)
VRAM Utilized:         90% (~148GB / 192GB HBM3)
Junction Temperature:  52°C (stable under load)
Memory Temperature:    45°C
GPU Utilization:       ~87% during parallel agent execution
```

### vLLM Inference Metrics (138 real requests)
```
Average LLM call latency:   4.25 seconds
p95 latency:                < 2.5 seconds (short prompts)
Total requests served:      138
Model:                      Llama 3.1 70B full precision
```

### Application Pipeline
```
End-to-end consultation:    13.68 seconds
  └─ Transcription:         ~0.3s (Deepgram)
  └─ Clinical NLP:          ~4.25s (LLM)
  └─ 6 parallel agents:     ~4-6s (concurrent LLM calls)
  └─ Supervisor summary:    ~4.25s (LLM)
  └─ TTS + Avatar init:     ~2s (Deepgram + Simli)

Sequential equivalent:      ~34+ seconds
Parallel speedup:           2.5x
```

---

## How I Built It — Step by Step

### 1. Setting Up vLLM on AMD MI300X

The ROCm vLLM image is the fastest path. Key flags that are easy to miss:

```bash
docker run \
  --device /dev/kfd \
  --device /dev/dri \
  --group-add video \
  -p 8001:8000 \
  rocm/vllm:latest \
  --model meta-llama/Llama-3.1-70B-Instruct \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192 \
  --host 0.0.0.0 \
  --port 8000
```

`--device /dev/kfd` and `--device /dev/dri` are mandatory for ROCm GPU access inside Docker. Missing them gives you CPU-only inference with no useful error message.

**Warmup tip:** First inference request has ~200ms GPU cold-start. Add a warmup call at application boot:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up vLLM on startup
    try:
        await llm_client.complete("warmup", max_tokens=1)
    except:
        pass
    yield
```

### 2. LangGraph Parallel Agent Pipeline

The key is using `Send` for parallel dispatch after the NLP stage:

```python
from langgraph.graph import StateGraph
from langgraph.constants import Send

def dispatch_parallel_agents(state: ClinicalState):
    """Fire all downstream agents simultaneously."""
    return [
        Send("ehr_notes", state),
        Send("lab_order", state),
        Send("referral", state),
        Send("billing_coding", state),
        Send("scheduling", state),
        Send("relationship", state),  # patient SMS
    ]

workflow = StateGraph(ClinicalState)
workflow.add_node("transcription", transcription_agent)
workflow.add_node("clinical_nlp", clinical_nlp_agent)
workflow.add_conditional_edges("clinical_nlp", dispatch_parallel_agents)
# ... add parallel nodes
workflow.add_node("supervisor", supervisor_agent)
```

This is the architectural decision that makes the 13.68s end-to-end possible.

### 3. Clinical Output Sanitization

LLMs are not reliable for structured medical data without validation. Example failure mode caught in testing:

```python
# LLM returned this for heart_rate:
{"heart_rate": "fast", "blood_pressure": "elevated"}

# Required output:
{"heart_rate": 110, "blood_pressure": "160/100"}
```

Always validate and sanitize clinical AI output before saving to records:

```python
def sanitize_vitals(vitals: dict) -> dict:
    """Convert LLM descriptive outputs to structured values."""
    hr = vitals.get("heart_rate")
    if isinstance(hr, str) and not hr.isdigit():
        vitals["heart_rate"] = None  # flag for manual entry
    return vitals
```

### 4. Monitoring Stack

Full observability was important for demonstrating MI300X performance:

```
AMD GPU Exporter (port 5000) ──→ socat proxy (5001) ──┐
vLLM metrics (port 8001/metrics)                      ├──→ Prometheus → Grafana
FastAPI (prometheus-fastapi-instrumentator)           ┘
Node Exporter (system metrics)
```

Key Grafana panels:
- AMD GPU power over time (spikes clearly visible during parallel agent execution)
- vLLM latency percentiles (p50/p95/p99)
- FastAPI request rate and response time
- VRAM usage (flat at 90% — model loaded, memory stable)

---

## What I'd Do Differently

**1. Model quantization strategy**  
For the parallel agent workload, GPTQ 8-bit would free ~20GB VRAM with minimal quality loss for structured output tasks (billing codes, scheduling). Reserve full precision for the clinical NLP and supervisor agents where reasoning depth matters most.

**2. KV cache sharing across agents**  
All 6 parallel agents share the same patient context. A shared KV cache prefix would reduce memory pressure and improve throughput. vLLM's prefix caching feature handles this — I'd enable it from the start next time.

**3. Streaming responses to frontend**  
Currently the frontend waits for the full pipeline to complete before showing output. Progressive streaming (SOAP notes appear as they're generated) would feel significantly faster even with the same backend latency.

---

## Lessons Learned

**On AMD MI300X and ROCm:**
- vLLM on ROCm is genuinely production-ready. The OpenAI-compatible API is not a compatibility shim — it's a full implementation.
- The AMD Developer Cloud provisioning is fast. GPU was available within minutes.
- `rocm-smi --showpower` gives you real-time wattage — more useful than temperature alone for understanding GPU load.
- Documentation for Docker device flags is scattered. A single "run vLLM on MI300X" quickstart page would save hours.

**On clinical AI specifically:**
- Structured output from LLMs requires strict validation. Medical data has no tolerance for type errors.
- Parallel agents are not just faster — they're architecturally cleaner. Each agent has a single responsibility and can be independently tested.
- The talking avatar (Dr. Aria) was the most impactful UX decision. Audio + video output makes the AI feel like a colleague, not a form.

---

## Running Klinik Locally

```bash
git clone https://github.com/Charleskojomark/klinik
cd klinik
cp .env.example .env  # fill in your API keys
docker compose up -d
```

For AMD MI300X deployment, see `DEPLOY_AMD_MI300X.md` in the repo.

The backend API is at `http://localhost:8080/docs` — full Swagger UI with all endpoints.

---

## AMD Developer Feedback

**Environment:**
- AMD Developer Cloud: MI300X instance
- ROCm version: 6.16.13 (driver)
- vLLM image: rocm/vllm:latest
- Model: Llama 3.1 70B Instruct (full BF16 precision)

**What worked well:**
- vLLM ROCm image pulled and ran correctly with proper device flags
- OpenAI-compatible API required zero application code changes
- 192GB HBM3 enabled full-precision 70B inference — the core technical differentiator
- `rocm-smi` is comprehensive and scriptable — better power visibility than alternatives
- AMD GPU Prometheus exporter was already running on the instance — monitoring setup was fast

**Suggestions for AMD Developer Experience:**

1. **Single quickstart guide for vLLM on MI300X** — The `--device /dev/kfd --device /dev/dri --group-add video` flags are essential but scattered across docs. One authoritative page would significantly reduce onboarding time.

2. **vLLM warmup documentation** — The ~200ms GPU cold-start on first inference request is confusing for developers who don't expect it. Documenting this behavior and the warmup pattern would prevent debugging time.

3. **Pre-cached model volumes** — HuggingFace model download inside Docker on first run is slow (70B = significant download time). A documented pattern for pre-downloading to a persistent volume would improve the developer loop.

4. **ROCm container health check** — When the Docker device flags are missing, the container starts successfully but runs on CPU with no clear error. A startup check that validates GPU access and warns loudly would save debugging time.

**Performance observations:**
- GPU utilization: ~87% during parallel 8-agent execution
- Memory: ~148GB / 192GB HBM3 (90%) — stable, no OOM
- Power draw: 206W sustained during inference
- Temperature: 52°C junction — excellent thermal management
- End-to-end clinical pipeline: 13.68 seconds (8 agents, 6 parallel)
- Average LLM call: 4.25 seconds per agent

**Overall:** The MI300X is the only single-GPU solution that runs Llama 70B at full precision. For healthcare AI where model quality directly affects patient safety, this is not a marginal improvement — it's a fundamental architectural enabler.
