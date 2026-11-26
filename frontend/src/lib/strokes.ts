import type { Stroke } from '@/types/attempt'

export function paintStroke(c: CanvasRenderingContext2D, s: Stroke, w: number, h: number): void {
  const pts = s.points
  if (pts.length === 0) return
  c.globalCompositeOperation = s.erase ? 'destination-out' : 'source-over'
  c.strokeStyle = s.color ?? '#1c1c1c'
  c.lineWidth = s.size !== undefined ? s.size * w : s.erase ? 16 : 2
  c.lineCap = 'round'
  c.lineJoin = 'round'
  c.beginPath()
  const first = pts[0]!
  c.moveTo(first[0] * w, first[1] * h)
  if (pts.length === 1) c.lineTo(first[0] * w + 0.01, first[1] * h)
  for (const p of pts.slice(1)) c.lineTo(p[0] * w, p[1] * h)
  c.stroke()
}
