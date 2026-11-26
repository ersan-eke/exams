import type { Answer, AnswerMode, AnswerPart } from '@/types/attempt'

export function emptyAnswer(mode: AnswerMode): Answer {
  return { mode, parts: [], done: false, ticks: [] }
}

export const emptyPart = (): AnswerPart => ({ text: '', strokes: [] })

const partAnswered = (p: AnswerPart) => p.text.trim() !== '' || p.strokes.some((s) => !s.erase)

export function isAnswered(a?: Answer): boolean {
  if (!a) return false
  return a.parts.some(partAnswered) || a.done || a.ticks.length > 0
}

/** answered only by the former "On paper" mode, nothing written */
export const onPaperOnly = (a: Answer) => a.done && !a.parts.some(partAnswered)

function samePart(x: AnswerPart = emptyPart(), y: AnswerPart = emptyPart()): boolean {
  return (
    x.text === y.text &&
    x.strokes.length === y.strokes.length &&
    x.strokes.every((s, i) => {
      const o = y.strokes[i]!
      return (
        s.erase === o.erase &&
        s.color === o.color &&
        s.size === o.size &&
        s.points.length === o.points.length &&
        s.points.every((p, j) => p[0] === o.points[j]![0] && p[1] === o.points[j]![1])
      )
    })
  )
}

export function sameAnswer(a?: Answer, b?: Answer): boolean {
  const x = a ?? emptyAnswer(b?.mode ?? 'type')
  const y = b ?? emptyAnswer(a?.mode ?? 'type')
  const n = Math.max(x.parts.length, y.parts.length)
  return (
    x.mode === y.mode &&
    x.done === y.done &&
    x.ticks.length === y.ticks.length &&
    x.ticks.every((t, i) => t === y.ticks[i]) &&
    Array.from({ length: n }, (_, i) => samePart(x.parts[i], y.parts[i])).every(Boolean)
  )
}

type OldAnswer = Answer & { text?: string; strokes?: AnswerPart['strokes'] }

/** answers saved before parts existed had one text and one drawing */
export function migrateAnswer(a: OldAnswer): Answer {
  if (a.parts) return a
  const { text = '', strokes = [], ...rest } = a
  return { ...rest, parts: text || strokes.length ? [{ text, strokes }] : [] }
}
