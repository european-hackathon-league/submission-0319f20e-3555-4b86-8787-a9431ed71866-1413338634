"use client"

import { useEffect, useRef, useState } from "react"
import { Pause, Play } from "lucide-react"

/** Original blue airflow ribbons, drawn locally without video or a 3D runtime. */
export function MotionField() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const phaseRef = useRef(0)
  const [paused, setPaused] = useState(false)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext("2d", { alpha: true })
    if (!canvas || !ctx) return
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)")
    let frame = 0
    let width = 0
    let height = 0
    let visible = true
    let previousTime = 0

    function position(u: number, lane: number, band: number) {
      const curve = Math.sin(u * 5.5 - 1.2 + phaseRef.current * 0.13)
      const fan = (lane - 0.5) * (0.12 + u * 0.46)
      return height * (0.77 - u * 0.37 + curve * 0.21 + fan + band * 0.2)
    }

    function paint() {
      if (!ctx || width <= 0 || height <= 0) return
      ctx.clearRect(0, 0, width, height)
      const light = ctx.createLinearGradient(0, 0, width, height * 0.3)
      light.addColorStop(0, "rgba(18,69,146,0)")
      light.addColorStop(0.35, "rgba(27,100,224,0.3)")
      light.addColorStop(0.7, "rgba(62,146,255,0.85)")
      light.addColorStop(1, "rgba(181,222,255,0.65)")

      for (let band = 0; band < 3; band++) {
        for (let row = 0; row < 18; row++) {
          const lane = row / 17
          ctx.beginPath()
          for (let step = 0; step <= 120; step++) {
            const u = step / 120
            const x = u * (width + 40) - 20
            const y = position(u, lane, band - 1)
            if (step === 0) ctx.moveTo(x, y)
            else ctx.lineTo(x, y)
          }
          ctx.strokeStyle = light
          ctx.lineWidth = row === 0 || row === 17 ? 1.1 : 0.55
          ctx.globalAlpha = band === 1 ? 0.9 : 0.35
          ctx.stroke()
        }

        // A moving glint follows each ribbon, with no React updates per frame.
        const head = (phaseRef.current * 0.11 + band * 0.32) % 1.35
        const start = Math.max(0, head - 0.24)
        const end = Math.min(1, head)
        if (end > start) {
          const glint = ctx.createLinearGradient(start * width, 0, end * width, 0)
          glint.addColorStop(0, "rgba(87,160,255,0)")
          glint.addColorStop(0.8, "rgba(136,203,255,0.7)")
          glint.addColorStop(1, "rgba(222,244,255,0.95)")
          ctx.beginPath()
          for (let step = 0; step <= 40; step++) {
            const u = start + (end - start) * step / 40
            const x = u * (width + 40) - 20
            const y = position(u, 0.5, band - 1)
            if (step === 0) ctx.moveTo(x, y)
            else ctx.lineTo(x, y)
          }
          ctx.globalAlpha = 0.95
          ctx.strokeStyle = glint
          ctx.lineWidth = 1.8
          ctx.stroke()
        }
      }
      ctx.globalAlpha = 1
    }

    function tick(time: number) {
      if (time - previousTime >= 32) {
        phaseRef.current += Math.min(time - previousTime, 50) / 1000
        paint()
        previousTime = time
      }
      frame = requestAnimationFrame(tick)
    }

    function sync() {
      cancelAnimationFrame(frame)
      previousTime = 0
      paint()
      if (!paused && !reduced.matches && visible && !document.hidden) frame = requestAnimationFrame(tick)
    }

    const resize = new ResizeObserver(([entry]) => {
      width = entry.contentRect.width
      height = entry.contentRect.height
      const ratio = Math.min(window.devicePixelRatio || 1, 1.5)
      canvas.width = Math.round(width * ratio)
      canvas.height = Math.round(height * ratio)
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
      sync()
    })
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync() })
    resize.observe(canvas)
    observer.observe(canvas)
    reduced.addEventListener("change", sync)
    document.addEventListener("visibilitychange", sync)
    return () => {
      cancelAnimationFrame(frame)
      resize.disconnect()
      observer.disconnect()
      reduced.removeEventListener("change", sync)
      document.removeEventListener("visibilitychange", sync)
    }
  }, [paused])

  return <>
    <div className="motion-field" aria-hidden="true"><canvas ref={canvasRef} /></div>
    <button className="motion-control" type="button" onClick={() => setPaused(value => !value)} aria-label={paused ? "Play background animation" : "Pause background animation"} aria-pressed={paused}>
      {paused ? <Play size={13} /> : <Pause size={13} />}
    </button>
  </>
}
