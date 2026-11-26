import type { Attempt } from '@/types/attempt'
import type { AnswerBox, Context, ExamStructure, Subtask, Task } from '@/types/exam'

export function includedTasks(exam: ExamStructure, a: Attempt): Task[] {
  return exam.tasks.filter((t) => a.includedTaskIds.includes(t.id))
}

export function orderedShown(exam: ExamStructure, shownIds: string[]): string[] {
  const shown = new Set(shownIds)
  return exam.tasks.flatMap((t) => t.subtasks.map((s) => s.id)).filter((id) => shown.has(id))
}

export type SheetBlock =
  | { kind: 'context'; context: Context }
  | { kind: 'subtask'; subtask: Subtask }

/** a task's shown subtasks with their contexts, in document order: each context sits before its applies_from subtask */
export function sheetBlocks(task: Task, shownSubtaskIds: string[]): SheetBlock[] {
  const ctx = (from: string | null): SheetBlock[] =>
    task.context
      .filter((c) => c.applies_from === from)
      .map((context) => ({ kind: 'context', context }))
  const last = Math.max(
    -1,
    ...task.subtasks.flatMap((s, i) => (shownSubtaskIds.includes(s.id) ? [i] : [])),
  )
  if (last === -1) return []
  return [
    ...ctx(null),
    ...task.subtasks
      .slice(0, last + 1)
      .flatMap((subtask): SheetBlock[] => [
        ...ctx(subtask.id),
        ...(shownSubtaskIds.includes(subtask.id) ? [{ kind: 'subtask' as const, subtask }] : []),
      ]),
  ]
}

export function subtaskTitle(task: Task, sub: Subtask): string {
  return sub.label === '' ? `Aufgabe ${task.number}` : `Aufgabe ${task.number} · ${sub.label}`
}

export function neighbors(
  exam: ExamStructure,
  a: Attempt,
  id: string,
): { prev: string | null; next: string | null } {
  const ids = includedTasks(exam, a).flatMap((t) => t.subtasks.map((s) => s.id))
  const i = ids.indexOf(id)
  if (i === -1) return { prev: null, next: null }
  return { prev: ids[i - 1] ?? null, next: ids[i + 1] ?? null }
}

/** the crop overlay works only if every option has a real box on a region with an image */
export function mcOverlayUsable(sub: Subtask): boolean {
  const options = sub.mc_options ?? []
  return (
    options.length > 0 &&
    options.every(
      ({ region, bbox: b }) => b.x1 > b.x0 && b.y1 > b.y0 && !!sub.regions[region]?.image,
    )
  )
}

export interface Crop {
  name: string
  regionIndex: number
}

export function crops(sub: Subtask): Crop[] {
  return sub.regions.flatMap((r, regionIndex) =>
    r.image === null ? [] : [{ name: r.image, regionIndex }],
  )
}

/** one answer box with the crops shown around it; box null = text field below the crops */
export interface SheetPart {
  crops: Crop[]
  box: AnswerBox | null
}

/**
 * One part per printed answer box (an area split over two pages gives two). A part ends at the
 * crop holding its box; crops after the last box join the last part. No box: a single part.
 */
export function answerParts(sub: Subtask): SheetPart[] {
  const boxes = new Map((sub.answer_boxes ?? []).map((b) => [b.region, b]))
  const parts: SheetPart[] = []
  let pending: Crop[] = []
  for (const c of crops(sub)) {
    pending.push(c)
    const box = boxes.get(c.regionIndex)
    if (box) {
      parts.push({ crops: pending, box })
      pending = []
    }
  }
  if (parts.length === 0) return [{ crops: pending, box: null }]
  parts[parts.length - 1]!.crops.push(...pending)
  return parts
}
