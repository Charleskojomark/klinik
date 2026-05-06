import { useEffect, useRef } from 'react'

export default function AudioVisualizer({ stream, isActive }) {
  const canvasRef  = useRef(null)
  const animRef    = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')

    // Hi-DPI resize
    const resize = () => {
      const dpr = window.devicePixelRatio || 1
      const rect = canvas.getBoundingClientRect()
      canvas.width  = rect.width  * dpr
      canvas.height = rect.height * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)

    const W = () => canvas.getBoundingClientRect().width
    const H = () => canvas.getBoundingClientRect().height

    /* ── Idle: breathing wave ── */
    const drawIdle = () => {
      const w = W(), h = H()
      if (w <= 0 || h <= 0) { animRef.current = requestAnimationFrame(drawIdle); return }
      ctx.clearRect(0, 0, w, h)
      const bars = 56
      const gap  = 2.5
      const barW = Math.max(1, (w - gap * (bars - 1)) / bars)
      const now  = Date.now() / 1000

      for (let i = 0; i < bars; i++) {
        const x    = i * (barW + gap)
        const wave = Math.sin(now * 1.8 + i * 0.28) * 0.5 + 0.5
        const bh   = 2 + wave * 8
        const y    = (h - bh) / 2

        const grad = ctx.createLinearGradient(x, y, x, y + bh)
        grad.addColorStop(0, 'rgba(37,99,235,0.30)')
        grad.addColorStop(1, 'rgba(37,99,235,0.06)')
        ctx.fillStyle = grad
        ctx.beginPath()
        ctx.roundRect(x, y, barW, Math.max(0.1, bh), Math.min(barW / 2, Math.max(0, Math.min(barW, Math.max(0.1, bh)) / 2)))
        ctx.fill()
      }
      animRef.current = requestAnimationFrame(drawIdle)
    }

    /* ── Live: real frequency data ── */
    let audioCtx, source
    const drawLive = (analyser) => {
      const bufLen = analyser.frequencyBinCount
      const data   = new Uint8Array(bufLen)

      const paint = () => {
        analyser.getByteFrequencyData(data)
        const w = W(), h = H()
        ctx.clearRect(0, 0, w, h)

        const bars = 64
        const gap  = 2
        const barW = (w - gap * (bars - 1)) / bars
        const step = Math.max(1, Math.floor(bufLen / bars))

        for (let i = 0; i < bars; i++) {
          let sum = 0
          for (let j = 0; j < step; j++) {
            const idx = i * step + j
            sum += idx < bufLen ? data[idx] : 0
          }
          const avg  = sum / step
          const norm = avg / 255
          const bh   = Math.max(2, norm * h * 0.88)
          const y    = (h - bh) / 2
          const x    = i * (barW + gap)

          const grad = ctx.createLinearGradient(x, y, x, y + bh)
          if (norm > 0.55) {
            grad.addColorStop(0, 'rgba(37,99,235,1)')
            grad.addColorStop(0.5, 'rgba(96,165,250,0.9)')
            grad.addColorStop(1, 'rgba(37,99,235,0.35)')
          } else if (norm > 0.25) {
            grad.addColorStop(0, 'rgba(37,99,235,0.8)')
            grad.addColorStop(1, 'rgba(37,99,235,0.2)')
          } else {
            grad.addColorStop(0, 'rgba(37,99,235,0.40)')
            grad.addColorStop(1, 'rgba(37,99,235,0.06)')
          }
          ctx.fillStyle = grad
          if (norm > 0.45) {
            ctx.shadowColor = 'rgba(37,99,235,0.45)'
            ctx.shadowBlur  = 6
          } else {
            ctx.shadowBlur = 0
          }
          ctx.beginPath()
          ctx.roundRect(x, y, barW, Math.max(0.1, bh), Math.min(barW / 2, Math.max(0, Math.min(barW, Math.max(0.1, bh)) / 2)))
          ctx.fill()
        }
        ctx.shadowBlur = 0
        animRef.current = requestAnimationFrame(paint)
      }
      paint()
    }

    if (stream && isActive) {
      cancelAnimationFrame(animRef.current)
      try {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)()
        const analyser = audioCtx.createAnalyser()
        analyser.fftSize = 256
        analyser.smoothingTimeConstant = 0.78
        source = audioCtx.createMediaStreamSource(stream)
        source.connect(analyser)
        drawLive(analyser)
      } catch (e) {
        drawIdle()
      }
    } else {
      cancelAnimationFrame(animRef.current)
      drawIdle()
    }

    return () => {
      cancelAnimationFrame(animRef.current)
      window.removeEventListener('resize', resize)
      try { source?.disconnect() } catch {}
      try { audioCtx?.close() } catch {}
    }
  }, [stream, isActive])

  return <canvas ref={canvasRef} style={{width:'100%',height:'100%',display:'block'}} />
}
