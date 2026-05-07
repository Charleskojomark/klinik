/**
 * DoctorAvatar — Replaces Simli WebRTC
 *
 * Audio: base64 MP3 → Blob URL → <audio autoPlay>  (< 100ms to first sound)
 * Animation: Web Audio AnalyserNode drives mouth amplitude in real time.
 *            Falls back to sine-wave pulse if AudioContext is unavailable.
 */
import { useEffect, useRef, useState } from 'react'

const AVATAR_NAME = 'Dr. Aria'

const IconSummary = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round" style={{width:20,height:20}}>
    <rect x="3" y="3" width="18" height="18" rx="2"/>
    <line x1="8" y1="9" x2="16" y2="9"/><line x1="8" y1="13" x2="16" y2="13"/>
    <line x1="8" y1="17" x2="12" y2="17"/>
  </svg>
)
const IconSend = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round" style={{width:20,height:20}}>
    <line x1="22" y1="2" x2="11" y2="13"/>
    <polygon points="22 2 15 22 11 13 2 9 22 2"/>
  </svg>
)

export default function DoctorAvatar({ audioB64, summary, isSpeaking, onDone, onSummary, onSend }) {
  const [displayText, setDisplayText] = useState('')
  const [isTyping,    setIsTyping]    = useState(true)
  const [mouthOpen,   setMouthOpen]   = useState(0)   // 0–1
  const [speaking,    setSpeaking]    = useState(false)

  const audioRef    = useRef(null)
  const animIdRef   = useRef(null)
  const audioCtxRef = useRef(null)
  const sourceRef   = useRef(null)   // keep MediaElementSource alive

  /* ── Typewriter ── */
  useEffect(() => {
    if (!summary) return
    setIsTyping(true); setDisplayText('')
    let i = 0
    const iv = setInterval(() => {
      if (i < summary.length) { setDisplayText(summary.slice(0, i + 1)); i++ }
      else { clearInterval(iv); setIsTyping(false) }
    }, 18)
    return () => clearInterval(iv)
  }, [summary])

  /* ── Audio playback + analyser ── */
  useEffect(() => {
    if (!audioB64) return
    const audio = audioRef.current
    if (!audio) return

    // Decode base64 → Blob → Object URL (no fetch round-trip)
    const bytes = Uint8Array.from(atob(audioB64), c => c.charCodeAt(0))
    const blob  = new Blob([bytes], { type: 'audio/mpeg' })
    const url   = URL.createObjectURL(blob)

    let ctx = null
    let animId = null

    const startAnalyser = () => {
      try {
        // Reuse existing context if possible (createMediaElementSource can only be called once per element)
        if (!audioCtxRef.current || audioCtxRef.current.state === 'closed') {
          ctx = new (window.AudioContext || window.webkitAudioContext)()
          audioCtxRef.current = ctx
        } else {
          ctx = audioCtxRef.current
          if (ctx.state === 'suspended') ctx.resume()
        }

        // Only create source node once per audio element
        if (!sourceRef.current) {
          sourceRef.current = ctx.createMediaElementSource(audio)
        }

        const analyser = ctx.createAnalyser()
        analyser.fftSize = 256
        sourceRef.current.connect(analyser)
        analyser.connect(ctx.destination)

        const data = new Uint8Array(analyser.frequencyBinCount)
        const tick = () => {
          analyser.getByteFrequencyData(data)
          // Use voice-frequency bands (roughly 300–3400Hz maps to bins 2–22 at 44.1kHz)
          const voiced = Array.from(data.slice(2, 18))
          const avg    = voiced.reduce((a, b) => a + b, 0) / voiced.length
          setMouthOpen(Math.min(1, avg / 90))
          animId = requestAnimationFrame(tick)
          animIdRef.current = animId
        }
        tick()
      } catch (err) {
        // Fallback: natural-feeling sine-wave animation
        let t = 0
        const tick = () => {
          setMouthOpen(0.20 + 0.45 * Math.abs(Math.sin(t * 4.5 + Math.sin(t * 1.7) * 0.5)))
          t += 0.055
          animId = requestAnimationFrame(tick)
          animIdRef.current = animId
        }
        tick()
      }
    }

    const stopAnimation = () => {
      cancelAnimationFrame(animIdRef.current)
      animIdRef.current = null
      setMouthOpen(0)
    }

    audio.src = url
    audio.onplay   = () => { setSpeaking(true);  startAnalyser() }
    audio.onended  = () => { setSpeaking(false); stopAnimation(); onDone?.(); URL.revokeObjectURL(url) }
    audio.onerror  = () => { setSpeaking(false); stopAnimation(); onDone?.() }
    audio.onpause  = () => { setSpeaking(false); stopAnimation() }

    // Attempt autoplay — mobile may block until user gesture
    audio.play().catch(() => {
      // Silent fail: user can tap the avatar to resume
      console.warn('[DoctorAvatar] Autoplay blocked — waiting for user gesture')
    })

    return () => {
      audio.pause()
      stopAnimation()
      URL.revokeObjectURL(url)
    }
  }, [audioB64])

  // Mouth SVG path — cubic bezier, opens downward
  const mouthY = 52 + mouthOpen * 10   // resting=52, open=62
  const mouthPath = `M 31 50 Q 40 ${mouthY} 49 50`

  return (
    <div className="completion-overlay">
      <style>{`
        @keyframes da-speaking {
          0%,100% { box-shadow: 0 0 24px rgba(167,139,250,0.25), 0 0 48px rgba(167,139,250,0.15); }
          50%      { box-shadow: 0 0 56px rgba(167,139,250,0.55), 0 0 90px rgba(167,139,250,0.30); }
        }
        @keyframes da-blink {
          0%,88%,100% { transform: scaleY(1);   }
          94%          { transform: scaleY(0.08); }
        }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        .da-ring.speaking { animation: da-speaking 0.75s ease-in-out infinite; }
        .da-eye-l { animation: da-blink 4.2s ease-in-out infinite; transform-origin: 34px 37px; }
        .da-eye-r { animation: da-blink 4.2s ease-in-out infinite 0.12s; transform-origin: 46px 37px; }
      `}</style>

      {/* ── Avatar ── */}
      <div className="sv-avatar-wrap">
        <div style={{ position:'relative', display:'inline-block' }}>
          <div
            className={`sv-avatar-ring da-ring ${speaking ? 'speaking' : ''}`}
            style={{ width:160, height:160, overflow:'hidden', background:'#0F0A1E',
                     cursor: !speaking && audioB64 ? 'pointer' : 'default' }}
            onClick={() => {
              // Resume autoplay on first tap (mobile gesture unlock)
              if (audioRef.current?.paused && audioB64) audioRef.current.play().catch(() => {})
            }}
          >
            <svg viewBox="0 0 80 80" width="160" height="160" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <radialGradient id="da-face" cx="48%" cy="42%" r="52%">
                  <stop offset="0%"   stopColor="#DDD6FE"/>
                  <stop offset="60%"  stopColor="#C4B5FD"/>
                  <stop offset="100%" stopColor="#8B5CF6"/>
                </radialGradient>
                <radialGradient id="da-bg" cx="50%" cy="50%" r="70%">
                  <stop offset="0%"   stopColor="#1E1040"/>
                  <stop offset="100%" stopColor="#0F0A1E"/>
                </radialGradient>
                <radialGradient id="da-cheek" cx="50%" cy="50%" r="50%">
                  <stop offset="0%"   stopColor="#F9A8D4" stopOpacity="0.35"/>
                  <stop offset="100%" stopColor="#F9A8D4" stopOpacity="0"/>
                </radialGradient>
              </defs>

              {/* Background */}
              <circle cx="40" cy="40" r="40" fill="url(#da-bg)"/>

              {/* Hair */}
              <ellipse cx="40" cy="20" rx="19" ry="10" fill="#3B0764"/>
              <rect    x="21" y="20" width="38" height="10" fill="#3B0764"/>
              <ellipse cx="22" cy="32" rx="3" ry="10" fill="#3B0764"/>
              <ellipse cx="58" cy="32" rx="3" ry="10" fill="#3B0764"/>

              {/* Face */}
              <ellipse cx="40" cy="38" rx="18" ry="20" fill="url(#da-face)"/>

              {/* Cheek blush */}
              <ellipse cx="30" cy="42" rx="5" ry="3" fill="url(#da-cheek)"/>
              <ellipse cx="50" cy="42" rx="5" ry="3" fill="url(#da-cheek)"/>

              {/* Eyes */}
              <ellipse cx="34" cy="37" rx="3.2" ry="3.5" fill="#1A0038" className="da-eye-l"/>
              <ellipse cx="46" cy="37" rx="3.2" ry="3.5" fill="#1A0038" className="da-eye-r"/>
              {/* Iris */}
              <circle cx="34" cy="37" r="2" fill="#4C1D95"/>
              <circle cx="46" cy="37" r="2" fill="#4C1D95"/>
              {/* Pupil + shine */}
              <circle cx="34" cy="37" r="1" fill="#0F0A1E"/>
              <circle cx="46" cy="37" r="1" fill="#0F0A1E"/>
              <circle cx="35" cy="36" r="0.8" fill="white" opacity="0.85"/>
              <circle cx="47" cy="36" r="0.8" fill="white" opacity="0.85"/>

              {/* Eyebrows */}
              <path d="M 30.5 32.5 Q 34 31 37.5 32.5" stroke="#3B0764" strokeWidth="1.4" fill="none" strokeLinecap="round"/>
              <path d="M 42.5 32.5 Q 46 31 49.5 32.5" stroke="#3B0764" strokeWidth="1.4" fill="none" strokeLinecap="round"/>

              {/* Nose */}
              <path d="M 38.5 40 L 37.5 44.5 Q 40 46 42.5 44.5 L 41.5 40"
                stroke="#A78BFA" strokeWidth="0.9" fill="none" opacity="0.5" strokeLinecap="round"/>

              {/* Mouth — driven by AnalyserNode amplitude */}
              <path
                d={mouthPath}
                stroke="#6D28D9" strokeWidth="1.8"
                fill={mouthOpen > 0.18 ? 'rgba(15,5,40,0.85)' : 'none'}
                strokeLinecap="round"
              />
              {/* Teeth hint when mouth open */}
              {mouthOpen > 0.3 && (
                <ellipse cx="40" cy={51 + mouthOpen * 2} rx={3 + mouthOpen * 3} ry="2"
                  fill="white" opacity={Math.min(0.9, mouthOpen * 1.5)}/>
              )}

              {/* Earrings */}
              <circle cx="22" cy="41" r="1.8" fill="#A78BFA" opacity="0.8"/>
              <circle cx="22" cy="44" r="1.2" fill="#7C3AED" opacity="0.7"/>
              <circle cx="58" cy="41" r="1.8" fill="#A78BFA" opacity="0.8"/>
              <circle cx="58" cy="44" r="1.2" fill="#7C3AED" opacity="0.7"/>

              {/* White coat */}
              <path d="M 22 80 L 26 56 Q 33 60 40 58 Q 47 60 54 56 L 58 80 Z" fill="#EDE9FE" opacity="0.92"/>
              {/* Lapels */}
              <path d="M 33 58 L 36 66 L 40 62 L 44 66 L 47 58" fill="#C4B5FD" opacity="0.6"/>
              {/* Stethoscope */}
              <path d="M 35 62 Q 31 68 34 72 Q 37 76 40 74"
                stroke="#A78BFA" strokeWidth="1.5" fill="none" strokeLinecap="round"/>
              <circle cx="40" cy="74" r="2.5" fill="none" stroke="#A78BFA" strokeWidth="1.2"/>
            </svg>
          </div>

          {/* Tap-to-play hint on mobile if autoplay was blocked */}
          {audioB64 && !speaking && (
            <div style={{
              position:'absolute', bottom:-2, right:-2,
              background:'var(--accent)', borderRadius:'50%',
              width:22, height:22,
              display:'flex', alignItems:'center', justifyContent:'center',
              fontSize:11, boxShadow:'0 0 8px rgba(167,139,250,0.5)',
              cursor:'pointer'
            }}
              onClick={() => audioRef.current?.play().catch(() => {})}
              title="Tap to play"
            >▶</div>
          )}
        </div>

        {/* Hidden audio element */}
        <audio ref={audioRef} style={{ display:'none' }} preload="auto"/>

        <div className="sv-badge">
          {speaking ? `● ${AVATAR_NAME} speaking…` : `● ${AVATAR_NAME}`}
        </div>
      </div>

      {/* Summary text */}
      <div className="completion-message">
        {displayText}
        {isTyping && <span style={{ color:'var(--accent)', animation:'blink 1s step-end infinite' }}>|</span>}
      </div>

      {/* Action buttons */}
      <div className="completion-actions">
        <button className="comp-btn" onClick={onSummary}><IconSummary /> Summary</button>
        <button className="comp-btn comp-btn-primary" onClick={onSend}><IconSend /> Chat & Send</button>
      </div>
    </div>
  )
}
