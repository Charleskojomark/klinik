import { useEffect, useRef, useState } from 'react'
import { SimliClient, generateSimliSessionToken } from 'simli-client'

const SIMLI_API_KEY = import.meta.env.VITE_SIMLI_API_KEY || ''
const SIMLI_FACE_ID = import.meta.env.VITE_SIMLI_FACE_ID || 'afdb6a3e-3939-40aa-92df-01604c23101c'
const AVATAR_NAME   = 'Dr. Aria'

const IconSummary = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{width:20,height:20}}>
    <rect x="3" y="3" width="18" height="18" rx="2"/>
    <line x1="8" y1="9" x2="16" y2="9"/>
    <line x1="8" y1="13" x2="16" y2="13"/>
    <line x1="8" y1="17" x2="12" y2="17"/>
  </svg>
)
const IconSend = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{width:20,height:20}}>
    <line x1="22" y1="2" x2="11" y2="13"/>
    <polygon points="22 2 15 22 11 13 2 9 22 2"/>
  </svg>
)

/* ── Decode MP3 base64 → raw PCM Uint8Array (pre-computable) ── */
export async function decodeMp3ToPcm(mp3B64) {
  const bytes = Uint8Array.from(atob(mp3B64), c => c.charCodeAt(0))
  const ctx   = new AudioContext({ sampleRate: 16000 })
  const buf   = await ctx.decodeAudioData(bytes.buffer.slice(0))
  const float = buf.getChannelData(0)
  await ctx.close()
  const pcm16 = new Int16Array(float.length)
  for (let i = 0; i < float.length; i++)
    pcm16[i] = Math.max(-32768, Math.min(32767, Math.round(float[i] * 32767)))
  const durationMs = (float.length / 16000) * 1000
  return { pcm: new Uint8Array(pcm16.buffer), durationMs }
}

/* ── Silence keep-alive ── */
function silenceChunk(ms = 500, sr = 16000) {
  return new Uint8Array(new Int16Array(Math.floor(sr * ms / 1000)).buffer)
}

export default function SupervisorAvatar({ summary, isSpeaking, pcmBuffer, pcmDurationMs, onReady, onSummary, onSend }) {
  const [displayText, setDisplayText] = useState('')
  const [isTyping,    setIsTyping]    = useState(true)
  const [avatarReady, setAvatarReady] = useState(false)
  const [connecting,  setConnecting]  = useState(true)

  const videoRef     = useRef(null)
  const audioRef     = useRef(null)
  const clientRef    = useRef(null)
  const pcmRef       = useRef(pcmBuffer)          // always up-to-date PCM bytes
  const durationRef  = useRef(pcmDurationMs || 0)
  const sentRef      = useRef(false)
  const startedRef   = useRef(false)              // guard: 'start' may fire multiple times
  const silenceIvRef = useRef(null)

  // Keep pcm ref current as soon as App pre-decodes audio
  useEffect(() => { pcmRef.current = pcmBuffer }, [pcmBuffer])
  useEffect(() => { durationRef.current = pcmDurationMs || 0 }, [pcmDurationMs])

  /* ── Typewriter ── */
  useEffect(() => {
    if (!summary) return
    setIsTyping(true)
    setDisplayText('')
    let i = 0
    const iv = setInterval(() => {
      if (i < summary.length) { setDisplayText(summary.slice(0, i + 1)); i++ }
      else { clearInterval(iv); setIsTyping(false) }
    }, 18)
    return () => clearInterval(iv)
  }, [summary])

  /* ── Send PCM + start keep-alive ── */
  const sendAudio = (client) => {
    if (!pcmRef.current || sentRef.current) return
    sentRef.current = true
    client.sendAudioData(pcmRef.current)
    console.log(`🔊 Dr. Aria speaking (~${(durationRef.current/1000).toFixed(1)}s)`)

    // Trigger screen transition — called AFTER audio is queued in Simli
    onReady?.()

    // Keep-alive silence starts only AFTER speech finishes
    const delay = (durationRef.current || 5000) + 1500
    setTimeout(() => {
      if (silenceIvRef.current) return
      silenceIvRef.current = setInterval(() => {
        try { client.sendAudioData(silenceChunk()) } catch (_) {}
      }, 8000)
    }, delay)
  }

  /* ── Simli WebRTC ── */
  useEffect(() => {
    if (!videoRef.current || !audioRef.current) return
    let cancelled = false

    ;(async () => {
      try {
        const _res = await fetch('https://api.simli.ai/compose/token', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-simli-api-key': SIMLI_API_KEY,
          },
          body: JSON.stringify({
            faceId: SIMLI_FACE_ID,
            handleSilence: true,
            maxSessionLength: 300,
            maxIdleTime: 120,
          }),
        })
        const { session_token } = await _res.json()
        if (cancelled) return

        const client = new SimliClient(
          session_token, videoRef.current, audioRef.current,
          null, undefined, 'livekit',
        )

        client.on('start', () => {
          if (startedRef.current || cancelled) return
          startedRef.current = true
          console.log('✅ Dr. Aria connected')
          setAvatarReady(true)
          setConnecting(false)
          clientRef.current = client

          // If PCM is ready → send immediately (zero extra latency)
          if (pcmRef.current) {
            sendAudio(client)
          }
          // Else: wait for pcmBuffer prop to arrive (handled below)
        })

        client.on('failed', () => {
          if (!cancelled) { setConnecting(false); onReady?.() }
        })

        await client.start()
      } catch (err) {
        if (!cancelled) { console.error('Dr. Aria error:', err); setConnecting(false); onReady?.() }
      }
    })()

    return () => {
      cancelled = true
      clearInterval(silenceIvRef.current)
      silenceIvRef.current = null
      if (clientRef.current) { try { clientRef.current.stop() } catch (_) {} clientRef.current = null }
    }
  }, [])

  /* ── PCM arrives after connection is already up ── */
  useEffect(() => {
    if (!pcmBuffer || !avatarReady || sentRef.current || !clientRef.current) return
    sendAudio(clientRef.current)
  }, [pcmBuffer, avatarReady])

  return (
    <div className="completion-overlay">
      <style>{`
        @keyframes sv-talk  { 0%,100%{r:2} 50%{r:5} }
        @keyframes sv-pulse { 0%,100%{opacity:.15;transform:scale(1)} 50%{opacity:.3;transform:scale(1.1)} }
        .sv-mouth.speaking { animation:sv-talk .3s ease-in-out infinite alternate; transform-origin:center }
        .sv-bg.speaking    { animation:sv-pulse 1.5s ease-in-out infinite; transform-origin:center }
        .sv-spin {
          position:absolute; inset:-5px; border-radius:50%;
          border:2.5px solid transparent; border-top-color:var(--accent);
          animation:spin .9s linear infinite; pointer-events:none;
        }
        @keyframes spin { to { transform:rotate(360deg) } }
      `}</style>

      <div className="sv-avatar-wrap">
        <div style={{ position:'relative', display:'inline-block' }}>
          <div
            className={`sv-avatar-ring ${isSpeaking || avatarReady ? 'speaking' : ''}`}
            style={{ width:160, height:160, overflow:'hidden', background: avatarReady ? '#000' : 'transparent' }}
          >
            <video ref={videoRef}
              style={{ width:'100%', height:'100%', objectFit:'cover', borderRadius:'50%',
                       display: avatarReady ? 'block' : 'none' }}
              muted={false} playsInline autoPlay />
            <audio ref={audioRef} autoPlay />

            {!avatarReady && (
              <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg" width="90" height="90">
                <circle cx="40" cy="28" r="16" fill="#A78BFA" className={`sv-bg ${isSpeaking?'speaking':''}`}/>
                <circle cx="40" cy="26" r="12" fill="#A78BFA" opacity="0.8"/>
                <path d="M18 68c0-12.15 9.85-22 22-22s22 9.85 22 22" stroke="#A78BFA" strokeWidth="3" strokeLinecap="round" fill="none" opacity="0.8"/>
                <path d="M33 36c0 3.866 3.134 7 7 7s7-3.134 7-7" stroke="white" strokeWidth="2" fill="none"/>
                <circle cx="40" cy="44" r="2" fill="white"/>
                {isSpeaking && <circle cx="40" cy="30" r="2" fill="white" className="sv-mouth speaking"/>}
              </svg>
            )}
          </div>
          {connecting && !avatarReady && <div className="sv-spin" />}
        </div>
        <div className="sv-badge">
          {avatarReady ? `● ${AVATAR_NAME}` : connecting ? 'Connecting…' : AVATAR_NAME}
        </div>
      </div>

      <div className="completion-message">
        {displayText}
        {isTyping && <span style={{ color:'var(--accent)', animation:'blink 1s step-end infinite' }}>|</span>}
      </div>

      <div className="completion-actions">
        <button className="comp-btn" onClick={onSummary}><IconSummary /> Summary</button>
        <button className="comp-btn comp-btn-primary" onClick={onSend}><IconSend /> Chat &amp; Send</button>
      </div>
    </div>
  )
}

