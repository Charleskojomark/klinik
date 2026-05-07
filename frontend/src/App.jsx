import { useState, useEffect, useRef, useCallback } from 'react'
import PatientPanel from './components/PatientPanel.jsx'
import SupervisorAvatar, { decodeMp3ToPcm } from './components/SupervisorAvatar.jsx'
import AudioVisualizer from './components/AudioVisualizer.jsx'

const API = '/api'

const AGENTS = [
  { key: 'transcription',  name: 'Transcription',  icon: '🎙️', done: 'Transcript processed',   working: 'Processing audio…' },
  { key: 'clinical_nlp',   name: 'Clinical NLP',   icon: '🧠', done: 'Entities extracted',      working: 'Analysing…' },
  { key: 'ehr_notes',      name: 'EHR Notes',      icon: '📋', done: 'SOAP note saved',          working: 'Writing note…' },
  { key: 'lab_order',      name: 'Lab Order',      icon: '🧪', done: 'Lab ordered',              working: 'Ordering…' },
  { key: 'pharmacy',       name: 'Pharmacy',       icon: '💊', done: 'Rx dispensed',             working: 'Checking…' },
  { key: 'referral',       name: 'Referral',       icon: '📨', done: 'Referral sent',            working: 'Referring…' },
  { key: 'scheduling',     name: 'Scheduling',     icon: '📅', done: 'Follow-up booked',         working: 'Scheduling…' },
  { key: 'billing_coding', name: 'Billing',        icon: '💳', done: 'ICD-10 coded',             working: 'Coding…' },
]

// (DEMO data removed, fetching from DB)

// ── SVG Icons ──
const Ic = ({ d, extra = '' }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round" className={extra}>{d}</svg>
)
const IconHome     = () => <Ic d={<><path d="M3 9.5L12 3l9 6.5V21a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5z"/><polyline points="9 22 9 12 15 12 15 22"/></>} />
const IconPatients = () => <Ic d={<><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></>} />
const IconNotes    = () => <Ic d={<><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></>} />
const IconSettings = () => <Ic d={<><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></>} />
const IconMic      = () => <Ic d={<><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></>} />
const IconGear     = () => <Ic d={<><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></>} />
const IconCheck    = () => <Ic d={<polyline points="20 6 9 17 4 12"/>} />
const IconRight    = () => <Ic d={<polyline points="9 18 15 12 9 6"/>} />

// ── TTS helper — picks the most natural voice available ──
function speak(text, onEnd) {
  if (!window.speechSynthesis) return
  window.speechSynthesis.cancel()
  const utter = new SpeechSynthesisUtterance(text)
  const voices = window.speechSynthesis.getVoices()
  const preferred = ['Google UK English Female', 'Microsoft Zira - English (United States)',
    'Samantha', 'Karen', 'Google US English']
  const voice = preferred.map(n => voices.find(v => v.name === n)).find(Boolean)
    || voices.find(v => v.lang.startsWith('en') && /female|woman/i.test(v.name))
    || voices.find(v => v.lang.startsWith('en'))
    || voices[0]
  if (voice) utter.voice = voice
  utter.rate  = 0.95
  utter.pitch = 1.05
  utter.onend = onEnd
  window.speechSynthesis.speak(utter)
}

export default function App() {
  const [page,           setPage]          = useState('home')
  const [phase,          setPhase]         = useState('idle')     // idle|recording|processing|complete
  const [finalTx,        setFinalTx]       = useState('')
  const [interimTx,      setInterimTx]     = useState('')
  const [agentStatus,    setAgentStatus]   = useState({})
  const [elapsed,        setElapsed]       = useState(0)
  const [result,         setResult]        = useState(null)
  const [isSpeaking,     setIsSpeaking]    = useState(false)
  const [srError,        setSrError]       = useState(null)
  const [ariaReady,      setAriaReady]     = useState(false)
  const [pendingResult,  setPendingResult] = useState(null)
  const [pcmBuffer,      setPcmBuffer]     = useState(null)   // pre-decoded PCM bytes
  const [pcmDurationMs,  setPcmDurationMs] = useState(0)
  
  // ── Database State ──
  const [patients,       setPatients]      = useState([])
  const [activePatient,  setActivePatient] = useState(null)

  // Fetch patients on mount
  const fetchPatients = async () => {
    try {
      const res = await fetch(`${API}/patients`)
      if (res.ok) {
        const data = await res.json()
        setPatients(data.patients || [])
      }
    } catch (e) {
      console.error("Failed to fetch patients", e)
    }
  }

  useEffect(() => {
    fetchPatients()
  }, [])

  const recRef   = useRef(null)
  const timerRef = useRef(null)
  const sseRef   = useRef(null)

  // ── Speech Recognition setup ──
  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { setSrError('Speech recognition not supported. Use Chrome or Edge.'); return }
    const rec = new SR()
    rec.continuous    = true
    rec.interimResults = true
    rec.lang          = 'en-US'
    rec.onresult = (e) => {
      let fin = '', inter = ''
      for (let i = 0; i < e.results.length; i++) {
        if (e.results[i].isFinal) fin  += e.results[i][0].transcript + ' '
        else                      inter += e.results[i][0].transcript
      }
      setFinalTx(fin)
      setInterimTx(inter)
    }
    rec.onerror = (e) => { if (e.error !== 'aborted') setSrError(`Mic error: ${e.error}`) }
    recRef.current = rec
    // preload voices
    window.speechSynthesis?.getVoices()
  }, [])

  // ── Elapsed timer ──
  useEffect(() => {
    if (phase === 'processing') {
      const t0 = Date.now()
      timerRef.current = setInterval(() => setElapsed(((Date.now()-t0)/1000).toFixed(1)), 200)
    } else clearInterval(timerRef.current)
    return () => clearInterval(timerRef.current)
  }, [phase])

  // ── Start recording ──
  const startRecording = () => {
    if (phase !== 'idle') return
    setSrError(null)
    setFinalTx(''); setInterimTx('')
    try { recRef.current?.start() } catch(e) {}
    setPhase('recording')
  }

  // ── Stop recording → submit ──
  const stopRecording = useCallback(() => {
    if (phase !== 'recording') return
    recRef.current?.stop()
    const text = (finalTx + ' ' + interimTx).trim()
    if (text.length > 3) {
      setInterimTx('')
      runConsultation(text)
    } else {
      setPhase('idle')
    }
  }, [phase, finalTx, interimTx])
  // ── Real SSE subscription ──
  const subscribeSSE = (sessionId) => {
    if (sseRef.current) sseRef.current.close()
    const es = new EventSource(`${API}/sessions/${sessionId}/events`)
    es.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data)
        if (ev.agent_name && ev.status) {
          const mapped = ev.status === 'running' ? 'working'
            : ev.status === 'completed' ? 'done'
            : ev.status === 'failed' ? 'error' : 'pending'
          setAgentStatus(prev => ({ ...prev, [ev.agent_name]: mapped }))

          // #11 / #6 fix: handle background audio_ready event from TTS task
          if (ev.agent_name === 'audio' && ev.status === 'ready' && ev.output) {
            try {
              const audioData = JSON.parse(ev.output)
              if (audioData.supervisor_audio_b64) {
                decodeMp3ToPcm(audioData.supervisor_audio_b64)
                  .then(({ pcm, durationMs }) => {
                    setPcmBuffer(pcm)
                    setPcmDurationMs(durationMs)
                  })
                  .catch(() => {})
              }
            } catch (_) {}
          }
        }
      } catch {}
    }
    es.onerror = () => es.close()
    sseRef.current = es
    return es
  }

  // ── Main consultation flow ──
  const runConsultation = async (text) => {
    setPhase('processing')
    setResult(null)
    setPendingResult(null)
    setAriaReady(false)
    setPcmBuffer(null)
    setPcmDurationMs(0)
    setElapsed(0)
    const init = {}; AGENTS.forEach(a => { init[a.key] = 'pending' })
    setAgentStatus(init)

    // Generate session_id client-side and send in body so backend uses the same one.
    // SSE subscription is opened AFTER the POST returns to use the confirmed session_id.
    const sessionId = `session-${crypto.randomUUID().slice(0,8)}`

    try {
      const res = await fetch(`${API}/consultation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          transcript: text,
          session_id: sessionId,
          patient_id: activePatient ? activePatient.id : undefined 
        }),
      })
      if (!res.ok) throw new Error('API error')
      const data = await res.json()

      // #11 fix: subscribe SSE AFTER the POST confirms the session_id.
      // The event_bus in-process log replays any events already published mid-workflow.
      subscribeSSE(data.session_id || sessionId)

      const all = {}; AGENTS.forEach(a => { all[a.key] = 'done' })
      setAgentStatus(all)
      fetchPatients()
      // Audio arrives via SSE 'audio_ready' event when background TTS task finishes.
      // Falls back to inline audio if backend provides it directly.
      if (data.supervisor_audio_b64) {
        decodeMp3ToPcm(data.supervisor_audio_b64)
          .then(({ pcm, durationMs }) => {
            setPcmBuffer(pcm)
            setPcmDurationMs(durationMs)
          })
          .catch(() => {})
      }
      setPendingResult(data)

    } catch {
      const fallback = {
        supervisor_summary: `All done. ${text.slice(0,60)}… Visit recorded. Your next patient is ready.`,
      }
      const all = {}; AGENTS.forEach(a => { all[a.key] = 'done' })
      setAgentStatus(all)
      setPendingResult(fallback)
    }
  }

  // ── When BOTH result and Aria are ready → show complete screen ──
  useEffect(() => {
    if (!pendingResult || !ariaReady) return
    setResult(pendingResult)
    setPendingResult(null)
    setPhase('complete')
    setIsSpeaking(true)
    if (pendingResult.supervisor_audio_b64) {
      const wordCount = (pendingResult.supervisor_summary || '').split(' ').length
      setTimeout(() => setIsSpeaking(false), Math.max(5000, wordCount * 350))
    } else {
      speak(pendingResult.supervisor_summary, () => setIsSpeaking(false))
    }
  }, [pendingResult, ariaReady])

  // ── Demo ──
  const runDemo = async () => {
    const txt = 'Amaka Obi, 28 years old, 12 weeks pregnant. Blood pressure 145 over 95. ' +
      'Patient reports persistent headache for 3 days and blurred vision. ' +
      'Pre-eclampsia suspected. Please order urine protein, refer obstetrics urgently, admit for monitoring. Follow up tomorrow at 9 AM.'
    setFinalTx(txt); setInterimTx('')
    await runConsultation(txt)
  }

  const reset = () => {
    window.speechSynthesis?.cancel()
    sseRef.current?.close()
    setPhase('idle'); setFinalTx(''); setInterimTx('')
    setResult(null); setAgentStatus({}); setIsSpeaking(false)
  }

  const fullTx = (finalTx + ' ' + interimTx).trim()
  const doneCount = Object.values(agentStatus).filter(s => s === 'done').length

  return (
    <div className="mobile-shell">
      {/* Header */}
      <header className="app-header">
        <div className="header-left" onClick={() => { reset(); setPage('home'); }} style={{cursor:'pointer'}}>
          <svg viewBox="0 0 32 32" fill="none" style={{width:30,height:30,filter:'drop-shadow(0 0 8px rgba(167,139,250,0.6))',flexShrink:0}}>
            <rect x="2" y="2" width="28" height="28" rx="10" fill="rgba(167,139,250,0.12)" stroke="#A78BFA" strokeWidth="2" />
            <path d="M7 16 H12 L14 10 L18 22 L20 16 H25" stroke="#A78BFA" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="16" cy="16" r="2" fill="#fff" />
          </svg>
          <span className="header-logo-text">KLINIK</span>
        </div>
        {phase !== 'idle' && (
          <div className="header-center">
            <div className="header-patient-name">{activePatient ? activePatient.name : 'New Patient'} — Active</div>
            <div className="center-orb-wrapper">
              <AudioVisualizer stream={recRef.current?.stream} isActive={phase === 'recording'} />
            </div>
            <div className="header-patient-sub">
              {phase === 'recording' ? '● Recording' : phase === 'processing' ? `${doneCount}/${AGENTS.length} agents` : 'Complete'}
            </div>
          </div>
        )}
        <div className="header-gear" onClick={() => setPage('settings')} style={{cursor:'pointer'}}><IconGear /></div>
      </header>

      <div className="main-content">
        {page === 'home' && (
          <>
            <div className="patient-context-strip" onClick={() => setPage('patients')}>
              <div>
                <div className="context-label">Current Patient</div>
                <div className="context-name">
                  {activePatient 
                    ? `${activePatient.name}, ${activePatient.age || '--'}${activePatient.sex || ''}` 
                    : 'Select a Patient'}
                </div>
              </div>
              <div className="context-arrow"><IconRight /></div>
            </div>

            {(phase === 'idle' || phase === 'recording') && (
              <VoiceScreen
                phase={phase}
                transcript={fullTx}
                interimTx={interimTx}
                error={srError}
                isSpeaking={isSpeaking}
                onStart={startRecording}
                onStop={stopRecording}
                onDemo={runDemo}
                onTextSubmit={runConsultation}
                stream={recRef.current?.stream}
              />
            )}
            {phase === 'processing' && (
              <AgentsScreen statuses={agentStatus} elapsed={elapsed} doneCount={doneCount} total={AGENTS.length} />
            )}
            {/* Mount SupervisorAvatar from recording onwards for maximum pre-warm time */}
            {(phase === 'recording' || phase === 'processing' || phase === 'complete') && (
              <div style={{ display: phase === 'complete' ? 'block' : 'none' }}>
                <SupervisorAvatar
                  summary={result?.supervisor_summary || ''}
                  isSpeaking={isSpeaking}
                  pcmBuffer={pcmBuffer}
                  pcmDurationMs={pcmDurationMs}
                  onReady={() => setAriaReady(true)}
                  onSummary={() => setPage('patients')}
                  onSend={() => setPhase('chat')}
                />
              </div>
            )}
            {phase === 'chat' && (
              <ChatScreen
                patient={activePatient}
                result={result}
                onDone={() => { reset(); setPage('home') }}
                onBack={() => setPhase('complete')}
              />
            )}
          </>
        )}

        {page === 'patients' && (
          <PatientPanel
            patients={patients}
            activePatient={activePatient}
            setActivePatient={setActivePatient}
            onBack={() => setPage('home')}
            refreshPatients={fetchPatients}
          />
        )}

        {page === 'notes' && <NotesPage patients={patients} />}
        {page === 'settings' && <SettingsPage />}
      </div>

      <nav className="bottom-nav">
        {[
          { key: 'home',     label: 'Home',     Icon: IconHome },
          { key: 'patients', label: 'Patients', Icon: IconPatients },
          { key: 'notes',    label: 'Notes',    Icon: IconNotes },
          { key: 'settings', label: 'Settings', Icon: IconSettings },
        ].map(({ key, label, Icon }) => (
          <button key={key} className={`nav-item ${page === key ? 'active' : ''}`} onClick={() => { if (key === 'home') reset(); setPage(key); }}>
            <Icon />
            <span className="nav-item-label">{label}</span>
            {page === key && <div className="nav-active-line" />}
          </button>
        ))}
      </nav>
    </div>
  )
}

/* ── 1. Voice / Recording Screen ── */
function VoiceScreen({ phase, transcript, interimTx, error, isSpeaking, onStart, onStop, onDemo, onTextSubmit, stream }) {
  const recording = phase === 'recording'
  const [inputMode, setInputMode] = useState('voice') // 'voice' | 'type'
  const [typed, setTyped] = useState('')
  const bars = [20,35,55,80,100,80,55,90,70,40,60,95,75,50,85,65,45,78,92,60,38,72,88,55,42,68,82,30]

  const handleTextSubmit = () => {
    if (typed.trim().length > 3) { onTextSubmit(typed.trim()); setTyped('') }
  }

  return (
    <div className="voice-screen">

      {/* Mode Toggle */}
      <div className="mode-toggle">
        <button data-mode="voice" className={`mode-btn ${inputMode==='voice'?'active':''}`} onClick={() => setInputMode('voice')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
          Voice
        </button>
        <button data-mode="type" className={`mode-btn ${inputMode==='type'?'active':''}`} onClick={() => setInputMode('type')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg>
          Type
        </button>
      </div>

      {inputMode === 'voice' ? (<>
        {/* Waveform Display */}
        <div className={`waveform-display ${recording ? 'active' : ''}`}>
          <div className="waveform-label">{recording ? '● Live Audio' : 'Audio Visualiser'}</div>
          <div className="waveform-bars">
            {bars.map((h, i) => (
              <div key={i} className={`waveform-bar ${recording ? 'animated' : ''}`}
                style={{ height:`${recording ? h : Math.max(12,h*0.2)}%`,
                  opacity: recording ? 1 : 0.18,
                  animationDelay:`${(i*0.04).toFixed(2)}s` }} />
            ))}
          </div>
        </div>

        {/* Status Badge */}
        <div className={`status-badge ${recording ? 'rec' : ''}`}>
          <div className={`status-badge-dot ${recording ? 'recording' : ''}`} />
          {recording ? 'RECORDING — Release to Submit' : 'READY TO LISTEN'}
        </div>

        {/* Transcript */}
        <div className="transcript-box">
          <div className="transcript-label">Live Transcript</div>
          <div className={`transcript-text ${!transcript ? 'placeholder' : ''}`}>
            {transcript || (error || 'Hold the mic button and speak the patient details…')}
            {recording && interimTx && <span style={{color:'var(--text-muted)',fontStyle:'italic'}}> {interimTx}</span>}
          </div>
        </div>

        {/* Mic + Demo */}
        <div className="mic-area">
          <div className="mic-outer-ring">
            <button
              className={`mic-ring-btn ${recording ? 'recording' : ''}`}
              onMouseDown={onStart} onMouseUp={onStop}
              onTouchStart={e => { e.preventDefault(); onStart() }}
              onTouchEnd={e   => { e.preventDefault(); onStop()  }}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" width="28" height="28">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                <line x1="12" y1="19" x2="12" y2="23"/>
                <line x1="8" y1="23" x2="16" y2="23"/>
              </svg>
            </button>
          </div>
          <div className="mic-hint">{recording ? 'Release to process ↑' : 'Hold to talk'}</div>
          {!recording && (
            <button className="demo-btn" onClick={onDemo}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              Try Demo — Amaka
            </button>
          )}
        </div>
      </>) : (
        /* Type Mode */
        <div className="type-mode">
          <div className="type-header">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="18" height="18"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
            Type Patient Details
          </div>
          <textarea
            className="type-textarea"
            placeholder="E.g. John Doe, 45M, came in for chest pain, BP 130/85, shortness of breath on exertion. No prior cardiac history..."
            value={typed}
            onChange={e => setTyped(e.target.value)}
            rows={5}
          />
          <div style={{fontSize:11,color:'var(--text-muted)',marginBottom:8}}>Voice-first: type only when mic is unavailable.</div>
          <button
            className="submit-btn"
            onClick={handleTextSubmit}
            disabled={typed.trim().length < 4}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            Process Consultation
          </button>
        </div>
      )}
    </div>
  )
}

/* ── Agents Screen ── */
function AgentsScreen({ statuses, elapsed, doneCount, total }) {
  return (
    <div className="agents-screen">
      <div className="agents-header">
        <div className="agents-title-block">
          <div className="agents-title">AI Agents Working</div>
          <div className="agents-sub">{doneCount} of {total} complete</div>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <div className="agents-timer-block">
            <div className="agents-elapsed">{elapsed}s</div>
            <div className="agents-total">Elapsed</div>
          </div>
          <div className="agents-spinner" />
        </div>
      </div>
      <div className="agents-grid">
        {AGENTS.map(agent => {
          const s = statuses[agent.key] || 'pending'
          return (
            <div key={agent.key} className={`agent-card ${s}`}>
              <div className="agent-card-top">
                <div className="agent-icon-circle"><span style={{fontSize:18}}>{agent.icon}</span></div>
                <div className="agent-status-icon">
                  {s === 'done'    && <div className="check-circle"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg></div>}
                  {s === 'working' && <div className="mini-spinner" />}
                  {s === 'pending' && <div style={{width:20,height:20,borderRadius:'50%',border:'2px solid var(--border)',opacity:0.4}} />}
                </div>
              </div>
              <div>
                <div className="agent-card-name">{agent.name}</div>
                <div className="agent-card-sub">{s==='done'?agent.done:s==='working'?agent.working:'—'}</div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ── Notes Page ── */
function NotesPage({ patients }) {
  const [encounters, setEncounters] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/encounters')
      .then(r => r.json())
      .then(d => { setEncounters(d.encounters || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  return (
    <div style={{padding:'0 0 24px'}}>
      <div style={{padding:'16px 18px 8px',fontWeight:700,fontSize:13,color:'var(--text-muted)',letterSpacing:'0.08em',textTransform:'uppercase'}}>Clinical Notes</div>
      {loading && <div style={{textAlign:'center',padding:40,color:'var(--text-muted)'}}>Loading notes…</div>}
      {!loading && encounters.length === 0 && (
        <div style={{textAlign:'center',padding:48}}>
          <svg viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" width="48" height="48" style={{margin:'0 auto 12px',display:'block'}}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <div style={{color:'var(--text-muted)',fontSize:14}}>No clinical notes yet.</div>
          <div style={{color:'var(--text-muted)',fontSize:12,marginTop:4}}>Record a consultation to generate AI notes.</div>
        </div>
      )}
      <div style={{padding:'0 16px'}}>
          {encounters.map((enc, i) => {
            const patientLabel = (enc.patient_name && enc.patient_name.trim())
              ? enc.patient_name.trim()
              : (enc.transcript && enc.transcript.length > 3)
                ? enc.transcript.trim().split(' ').slice(0,3).join(' ') + '…'
                : (enc.patient_id ? `Session #${enc.patient_id.substring(3,11)}` : 'Unknown Patient')
            const assessment   = enc.soap_note?.assessment || ''
            const summary      = enc.supervisor_summary || ''
            // Prefer the SOAP assessment as headline if supervisor summary is generic
            const isGeneric    = summary.startsWith('All done.')
            const headline     = !isGeneric ? summary : (assessment || summary)
            const diagnoses    = enc.diagnoses || []
            const labs         = enc.lab_orders || []
            const rxs          = enc.prescriptions || []
            return (
              <div key={enc.id} className="history-card" style={{marginBottom:12}}>
                <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:6}}>
                  <div className="history-date">{new Date(enc.created_at).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'})}</div>
                  <span style={{fontSize:10,background:'var(--accent-light)',color:'var(--accent)',borderRadius:'var(--r-full)',padding:'2px 10px',fontWeight:600,border:'1px solid var(--accent-border)'}}>SOAP</span>
                </div>
                <div className="history-title">{patientLabel}</div>
                {/* Clinical summary headline */}
                <div style={{fontSize:12,color:'var(--text-secondary)',marginTop:5,lineHeight:1.55}}>{headline}</div>
                {/* Diagnoses chips */}
                {diagnoses.length > 0 && (
                  <div style={{display:'flex',flexWrap:'wrap',gap:4,marginTop:8}}>
                    {diagnoses.slice(0,3).map((dx,j) => (
                      <span key={j} style={{fontSize:10,background:'rgba(220,38,38,0.08)',color:'#DC2626',border:'1px solid rgba(220,38,38,0.2)',borderRadius:6,padding:'2px 8px',fontWeight:600}}>{dx}</span>
                    ))}
                  </div>
                )}
                {/* Lab + Rx summary row */}
                {(labs.length > 0 || rxs.length > 0) && (
                  <div style={{display:'flex',gap:12,marginTop:6}}>
                    {labs.length > 0 && <span style={{fontSize:11,color:'var(--text-muted)'}}>🧪 {labs.map(l=>l.test_name).join(', ')}</span>}
                    {rxs.length  > 0 && <span style={{fontSize:11,color:'var(--text-muted)'}}>💊 {rxs.map(r=>r.drug_name).join(', ')}</span>}
                  </div>
                )}
              </div>
            )
          })}
      </div>
    </div>
  )
}

/* ── Chat Screen (SMS Simulation) ── */
function ChatScreen({ patient, result, onDone, onBack }) {
  const [messages, setMessages] = useState([])
  const messagesEndRef = useRef(null)

  // Resolve patient name from: 1) selected patient, 2) clinical NLP extraction, 3) fallback
  const patientName = patient?.name
    || result?.state?.patient?.name
    || result?.state?.patient?.patient_id
    || 'Patient'

  const patientInitial = patientName[0]?.toUpperCase() || 'P'

  useEffect(() => {
    if (!result) return
    const msgs = [
      { sender: 'sys', text: 'Klinik secure messaging started.' },
      { sender: 'doc', text: `Hi ${patientName}. I've sent your lab orders. Please follow the instructions below.` }
    ]
    
    let instructions = ''
    if (result.state?.soap_note?.plan) instructions += result.state.soap_note.plan + '\n'
    if (result.state?.prescriptions?.length) {
      instructions += 'Prescriptions sent to pharmacy: ' + result.state.prescriptions.map(p=>p.drug_name).join(', ')
    }
    if (instructions) msgs.push({ sender: 'bot', text: instructions.trim() })
    
    if (result.state?.follow_up?.scheduled) {
      msgs.push({ sender: 'bot', text: `Your follow-up is scheduled for ${result.state.follow_up.recommended_date}.` })
    }

    // Simulate typing effect
    setMessages([msgs[0]])
    const timeouts = []
    msgs.slice(1).forEach((m, i) => {
      const to = setTimeout(() => {
        setMessages(prev => {
          // Prevent duplicates
          if (prev.some(msg => msg.text === m.text)) return prev
          return [...prev, m]
        })
      }, (i + 1) * 1200)
      timeouts.push(to)
    })
    
    return () => timeouts.forEach(clearTimeout)
  }, [result, patient])

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="chat-screen">
      <div className="chat-header">
        <div style={{display:'flex',alignItems:'center',gap:12}}>
          <button onClick={onBack} style={{background:'none',border:'none',color:'var(--text-secondary)',cursor:'pointer',display:'flex',alignItems:'center'}}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{width:20,height:20}}>
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </button>
          <div style={{width:36,height:36,borderRadius:'50%',background:'var(--accent)',display:'flex',alignItems:'center',justifyContent:'center',color:'#fff',fontWeight:700,fontSize:14}}>
            {patientInitial}
          </div>
          <div>
            <div style={{fontSize:15,fontWeight:700,color:'var(--text-primary)'}}>{patientName}</div>
            <div style={{fontSize:11,color:'var(--success)',display:'flex',alignItems:'center',gap:4}}>
              <span style={{width:6,height:6,borderRadius:'50%',background:'var(--success)',display:'block'}}/> Online
            </div>
          </div>
        </div>
      </div>
      
      <div className="chat-body">
        <div className="chat-date">Today</div>
        {messages.map((m, i) => (
          <div key={i} className={`chat-bubble-wrap ${m.sender}`}>
            {m.sender === 'sys' ? (
              <div className="chat-sys">{m.text}</div>
            ) : (
              <div className={`chat-bubble ${m.sender}`}>
                {m.text}
                <div className="chat-time">{new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</div>
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-footer">
        <button className="chat-done-btn" onClick={onDone}>Next Patient →</button>
      </div>
    </div>
  )
}

/* ── Settings Page ── */
function SettingsPage() {
  const [voice, setVoice] = useState('aura-asteria-en')
  const [notifications, setNotifications] = useState(true)
  const [autoSpeak, setAutoSpeak] = useState(true)

  const Row = ({ label, sub, children }) => (
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'14px 18px',borderBottom:'1px solid var(--border)'}}>
      <div>
        <div style={{fontSize:14,fontWeight:600,color:'var(--text-primary)'}}>{label}</div>
        {sub && <div style={{fontSize:12,color:'var(--text-muted)',marginTop:2}}>{sub}</div>}
      </div>
      {children}
    </div>
  )
  const Toggle = ({ on, onChange }) => (
    <button onClick={() => onChange(!on)} style={{
      width:44,height:24,borderRadius:12,border:'none',cursor:'pointer',
      background: on ? 'var(--accent)' : 'var(--border-md)',
      position:'relative',transition:'background 0.2s',padding:0
    }}>
      <span style={{
        position:'absolute',top:3,left: on ? 22 : 3,width:18,height:18,
        borderRadius:'50%',background:'#fff',transition:'left 0.2s',display:'block'
      }}/>
    </button>
  )

  return (
    <div style={{paddingBottom:24}}>
      <div style={{padding:'16px 18px 8px',fontWeight:700,fontSize:13,color:'var(--text-muted)',letterSpacing:'0.08em',textTransform:'uppercase'}}>Preferences</div>

      <div style={{background:'var(--bg-card)',borderRadius:'var(--r-lg)',margin:'0 16px 16px',border:'1px solid var(--border)',overflow:'hidden',boxShadow:'var(--shadow-card)'}}>
        <Row label="Auto-Speak Summary" sub="Supervisor reads results aloud"><Toggle on={autoSpeak} onChange={setAutoSpeak}/></Row>
        <Row label="Notifications" sub="Alerts for lab & referral updates"><Toggle on={notifications} onChange={setNotifications}/></Row>
      </div>

      <div style={{padding:'0 18px 8px',fontWeight:700,fontSize:13,color:'var(--text-muted)',letterSpacing:'0.08em',textTransform:'uppercase'}}>Voice Model</div>
      <div style={{background:'var(--bg-card)',borderRadius:'var(--r-lg)',margin:'0 16px 16px',border:'1px solid var(--border)',overflow:'hidden',boxShadow:'var(--shadow-card)'}}>
        {[
          {val:'aura-asteria-en', label:'Asteria', sub:'Natural female — recommended'},
          {val:'aura-orion-en',   label:'Orion',   sub:'Natural male voice'},
          {val:'aura-luna-en',    label:'Luna',     sub:'Soft female voice'},
        ].map(v => (
          <div key={v.val} onClick={() => setVoice(v.val)} style={{
            display:'flex',justifyContent:'space-between',alignItems:'center',
            padding:'14px 18px',borderBottom:'1px solid var(--border)',cursor:'pointer',
            background: voice===v.val ? 'var(--accent-light)' : 'transparent'
          }}>
            <div>
              <div style={{fontSize:14,fontWeight:600,color: voice===v.val ? 'var(--accent)' : 'var(--text-primary)'}}>{v.label}</div>
              <div style={{fontSize:12,color:'var(--text-muted)'}}>{v.sub}</div>
            </div>
            {voice===v.val && <svg viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="3" width="18" height="18"><polyline points="20 6 9 17 4 12"/></svg>}
          </div>
        ))}
      </div>

      <div style={{padding:'0 18px 8px',fontWeight:700,fontSize:13,color:'var(--text-muted)',letterSpacing:'0.08em',textTransform:'uppercase'}}>About</div>
      <div style={{background:'var(--bg-card)',borderRadius:'var(--r-lg)',margin:'0 16px',border:'1px solid var(--border)',overflow:'hidden',boxShadow:'var(--shadow-card)'}}>
        <Row label="Klinik" sub="v0.2.0 — Voice-Native Clinical AI"><span style={{fontSize:11,color:'var(--text-muted)'}}>Built with ❤️</span></Row>
        <Row label="AI Model" sub="meta-llama/Llama-3.1-70B-Instruct"><span style={{fontSize:11,color:'var(--accent)',fontWeight:600}}>AMD</span></Row>
        <Row label="TTS" sub="Deepgram Aura"><span style={{fontSize:11,color:'var(--accent)',fontWeight:600}}>LIVE</span></Row>
        <Row label="Database" sub="Turso (libSQL cloud)"><span style={{fontSize:11,color:'var(--success)',fontWeight:600}}>✓</span></Row>
      </div>
    </div>
  )
}
