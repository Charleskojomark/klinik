# 🏥 Klinik — Voice-Native Clinical AI

> **AMD Developer Hackathon 2026** — Track 1: AI Agents & Agentic Workflows

A voice-native clinical AI platform where doctors speak naturally and **8 specialized AI agents** handle every downstream clinical task in parallel — powered by **Llama 3.1 70B on AMD MI300X (ROCm 7.2)**.

🌐 **Live Demo:** https://klinik.charlesmark.xyz

![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-blueviolet?style=flat-square)
![ROCm](https://img.shields.io/badge/AMD-ROCm%207.2%20%2B%20MI300X-ED1C24?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square)
![React](https://img.shields.io/badge/React-Vite-61DAFB?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## ✨ What It Does

A doctor opens Klinik, selects a patient, and speaks:

> *"Patient Amaka Obi, 28-year-old female, 12 weeks pregnant. Presenting with severe headache and blurred vision. BP 145/95. Suspect pre-eclampsia. Order urine protein urgently, refer to obstetrics."*

In **13.68 seconds**, 8 AI agents fire in parallel and produce:

| Agent | Output |
|---|---|
| 🎙️ Transcription | Cleaned, structured transcript |
| 🧠 Clinical NLP | Patient demographics, vitals, diagnoses |
| 📋 EHR Notes | Full SOAP note saved to database |
| 🧪 Lab Order | Urgent urine protein ordered |
| 📨 Referral | Obstetrics referral letter generated |
| 📅 Scheduling | Follow-up appointment booked |
| 💳 Billing | ICD-10 / CPT codes generated |
| 💬 Patient SMS | Patient notification via Twilio |

Then **Dr. Aria** (a talking AI avatar) speaks the summary aloud. The doctor is ready for the next patient.

---

## 🏗️ Architecture

```
Doctor speaks
     │
     ▼
[React Frontend — Dark Purple UI]
     │  POST /api/consultation
     ▼
[FastAPI Backend]
     │
     ├─ Phase 1 (Sequential)
     │   ├─ Transcription Agent   ← Deepgram STT
     │   └─ Clinical NLP Agent    ← Llama 3.1 70B extracts vitals/diagnoses
     │
     └─ Phase 2 (Parallel — LangGraph Send)
         ├─ SOAP Notes Agent
         ├─ Lab Order Agent
         ├─ Referral Agent
         ├─ Scheduling Agent
         ├─ Billing Agent (ICD-10/CPT)
         └─ Patient SMS Agent
              │
              ▼
         Supervisor Agent → Final summary
              │
              ▼
         Dr. Aria speaks (Deepgram TTS + Simli WebRTC)
              │
              ▼
         Turso DB (encounter saved) + Patient SMS (Twilio)
```

**Why parallel?** Sequential execution = 34s+. Parallel = 13.68s. The AMD MI300X handles concurrent LLM calls without memory bottlenecking.

---

## 📊 Real Performance on AMD MI300X

All metrics from live deployment on AMD Developer Cloud (ROCm 7.2, MI300X 192GB):

| Metric | Value |
|---|---|
| End-to-end consultation | **13.68 seconds** |
| GPU VRAM utilized | **90% (~148GB / 192GB HBM3)** |
| GPU power draw | **206W** sustained during inference |
| Junction temperature | **52°C** stable under load |
| Avg LLM call latency | **4.25s** per agent |
| p95 LLM latency | **< 2.5s** short prompts |
| Total requests served | **138** logged |
| Parallel speedup | **2.5x** vs sequential |

> Llama 3.1 70B requires ~140GB VRAM at full BF16 precision. The MI300X is the only single-GPU solution that runs it without quantization.

---

## 🚀 Quick Start (Local Dev)

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker + Docker Compose

### 1. Clone & Configure

```bash
git clone https://github.com/Charleskojomark/klinik.git
cd klinik
cp .env.example .env
# Fill in your API keys in .env
```

### 2. Start Services

```bash
docker compose up -d
```

### 3. Open the App

```
http://localhost:3000
```

> **No GPU?** The backend falls back to mock LLM responses automatically. The full UI, agent pipeline, database, TTS, and avatar still work for testing.

---

## ☁️ AMD MI300X Deployment

See **[DEPLOY_AMD_MI300X.md](./DEPLOY_AMD_MI300X.md)** for the full production guide.

```bash
# On AMD Developer Cloud MI300X (ROCm 7.2):
git clone https://github.com/Charleskojomark/klinik.git && cd klinik
cp .env.example .env  # fill in keys

# Start vLLM on ROCm
docker run \
  --device /dev/kfd --device /dev/dri --group-add video \
  -p 8001:8000 rocm/vllm:latest \
  --model meta-llama/Llama-3.1-70B-Instruct \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192

# Start app
docker compose up -d

# Monitor GPU
rocm-smi --showuse --showmemuse --showtemp --showpower
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **LLM Inference** | vLLM + ROCm 7.2 on AMD MI300X |
| **Model** | Llama 3.1 70B Instruct (full BF16) |
| **Agent Orchestration** | LangGraph (parallel Send) |
| **Backend** | FastAPI + Python 3.11 |
| **Frontend** | React + Vite |
| **Database** | Turso (libSQL edge SQLite) |
| **Cache / Events** | Redis Cloud |
| **STT** | Deepgram |
| **TTS** | Deepgram Aura |
| **Avatar** | Simli AI (WebRTC) |
| **Video/Voice** | LiveKit Cloud |
| **SMS** | Twilio |
| **Reverse Proxy** | Caddy (auto-SSL) |
| **Monitoring** | Prometheus + Grafana |

---

## 📁 Project Structure

```
klinik/
├── backend/
│   └── app/
│       ├── agents/               # 8 clinical AI agents
│       │   ├── transcription.py
│       │   ├── clinical_nlp.py
│       │   ├── ehr_notes.py
│       │   ├── lab_order.py
│       │   ├── referral.py
│       │   ├── scheduling.py
│       │   ├── billing_coding.py
│       │   ├── relationship.py   # patient SMS
│       │   └── supervisor.py
│       ├── graph/
│       │   └── clinical_workflow.py  # LangGraph parallel orchestration
│       ├── models/
│       │   ├── clinical_state.py
│       │   └── database.py
│       ├── services/
│       │   ├── llm_client.py         # vLLM / OpenAI-compatible
│       │   ├── deepgram_tts.py
│       │   ├── simli_avatar.py
│       │   └── event_bus.py
│       └── main.py
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── index.css
│       └── components/
│           ├── SupervisorAvatar.jsx  # Dr. Aria
│           ├── PatientPanel.jsx
│           └── AudioVisualizer.jsx
├── docker-compose.yml
├── DEPLOY_AMD_MI300X.md
├── HACKATHON_WALKTHROUGH.md
└── .env.example
```

---

## 🔑 Environment Variables

```bash
cp .env.example .env
```

Key variables:

```env
# LLM
VLLM_BASE_URL=http://localhost:8001/v1
LLM_MODEL=/models/llama-3.1-70b
HF_TOKEN=your_huggingface_token

# Redis
REDIS_URL=redis://localhost:6379

# LiveKit Cloud
LIVEKIT_URL=wss://your-app.livekit.cloud
LIVEKIT_API_KEY=your_key
LIVEKIT_API_SECRET=your_secret

# Simli Avatar
SIMLI_API_KEY=
SIMLI_FACE_ID=

# Deepgram
DEEPGRAM_API_KEY=

# Twilio SMS
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=+1XXXXXXXXXX

# Turso Database
DATABASE_URL=libsql://your-db.turso.io
TURSO_AUTH_TOKEN=

# App
APP_ENV=development
APP_SECRET_KEY=change-me-in-production
```

---

## 📖 Technical Walkthrough

See **[HACKATHON_WALKTHROUGH.md](./HACKATHON_WALKTHROUGH.md)** for a full deep-dive:
- Architecture decisions and LangGraph parallel agent implementation
- ROCm + vLLM setup on AMD MI300X
- Real performance benchmarks with Prometheus/Grafana
- AMD Developer feedback and lessons learned

---

## 🏆 AMD Developer Hackathon 2026

**Track:** AI Agents & Agentic Workflows
**Challenge:** Ship It (Build in Public)
**Instance:** AMD Developer Cloud — MI300X 192GB (ROCm 7.2), ATL1

- ✅ LangGraph multi-agent parallel orchestration
- ✅ Llama 3.1 70B on AMD MI300X via vLLM + ROCm 7.2
- ✅ Real clinical workflow automation (8 agents)
- ✅ Persistent patient records across consultations
- ✅ Full observability — Prometheus + Grafana + AMD GPU metrics
- ✅ Live deployment: https://klinik.charlesmark.xyz
- ✅ Open-source + documented

---

## 📄 License

MIT — use freely, contributions welcome.
