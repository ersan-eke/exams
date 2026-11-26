import type { Answer, Attempt, StoredExam } from '@/types/attempt'
import type { ExamStructure, McRule, Subtask, Task } from '@/types/exam'
import { sameAnswer } from './answers'

export function mcPoints(rule: McRule, ticks: number[], key: number[], max: number): number {
  const t = new Set(ticks)
  const k = new Set(key)
  if (rule.kind === 'all_or_nothing') {
    return t.size === k.size && [...t].every((x) => k.has(x)) ? max : 0
  }
  let right = 0
  let wrong = 0
  for (const x of t) k.has(x) ? right++ : wrong++
  const sum = rule.right * right + rule.wrong * wrong
  // a single-answer question worth more than one tick (grnvs: 1 P, 0.5 P per tick otherwise): all or nothing
  if (k.size === 1 && max > rule.right) return right === 1 && wrong === 0 ? max : Math.max(rule.floor, Math.min(0, sum))
  return Math.min(max, Math.max(rule.floor, sum))
}

export function changedInOvertime(a: Attempt, subtaskId: string): boolean {
  return a.snapshot !== null && !sameAnswer(a.snapshot[subtaskId], a.answers[subtaskId])
}

/**
 * A subtask's max points. An MC subtask without its own gets an equal share of what its task has
 * left, when every subtask without points is MC (e.g. "8 P" over four MC questions = 2 P each) —
 * except under a per-tick rule, where a question is worth its number of correct boxes (null without a key).
 * `rule` is the attempt's; the task's own rule wins. `key`: the effective MC key (own or attached solution's).
 */
export function maxPoints(task: Task, s: Subtask, rule?: McRule | null, key?: number[] | null): number | null {
  if (s.points !== null) return s.points
  const isMc = (x: Subtask) => (x.mc_options?.length ?? 0) > 0
  const effective = task.mc_rule ?? rule
  if (isMc(s) && effective?.kind === 'per_tick') {
    if (!key?.length) return null
    return key.length === 1 && effective.single != null ? effective.single : key.length * effective.right
  }
  if (task.points === null || !isMc(s)) return null
  const open = task.subtasks.filter((x) => x.points === null)
  if (!open.every(isMc)) return null
  const known = task.subtasks.reduce((sum, x) => sum + (x.points ?? 0), 0)
  const share = Math.max(0, task.points - known) / open.length
  // the backend refuses to split what is not a whole multiple of 0.5 too ("12 P over 9 MC questions; not split")
  return Number.isInteger(share * 2) ? share : null
}

function autoMc(a: Attempt, task: Task, max: number, key: number[] | undefined, answer: Answer | undefined) {
  if (!key || key.length === 0) return 0
  return mcPoints(task.mc_rule ?? a.mcRule, answer?.ticks ?? [], key, max)
}

/** one subtask's points: the hand grade, else automatic MC points; over is null without a snapshot */
export function subtaskScore(
  a: Attempt,
  task: Task,
  s: Subtask,
  key: number[] | undefined,
): { main: number; over: number | null; max: number | null } {
  const g = a.grades[s.id]
  const max = maxPoints(task, s, a.mcRule, key)
  const main = g?.main ?? autoMc(a, task, max ?? 0, key, (a.snapshot ?? a.answers)[s.id])
  const over =
    a.snapshot === null
      ? null
      : changedInOvertime(a, s.id)
        ? (g?.over ?? autoMc(a, task, max ?? 0, key, a.answers[s.id]))
        : main
  return { main, over, max }
}

/** an attempt Claude saved over MCP (record_practice in backend app/mcp/tools.py writes timeLimitMs 0): untimed */
export const isPractice = (a: Attempt) => a.timeLimitMs === 0

/** a practice attempt covers only the subtasks Claude graded */
export function counted(a: Attempt, s: Subtask): boolean {
  return !isPractice(a) || s.id in a.grades
}

/** `keys` (see mcKeys) overrides the subtasks' own mc_key, e.g. with an attached solution's key */
export function scores(
  a: Attempt,
  exam: ExamStructure,
  keys?: Record<string, number[]>,
): { main: number; over: number | null; maxKnown: number } {
  let main = 0
  let over = 0
  let maxKnown = 0
  for (const task of exam.tasks) {
    if (!a.includedTaskIds.includes(task.id)) continue
    for (const s of task.subtasks) {
      if (!counted(a, s)) continue
      const r = subtaskScore(a, task, s, keys ? keys[s.id] : (s.mc_key ?? undefined))
      main += r.main
      over += r.over ?? 0
      maxKnown += r.max ?? 0
    }
  }
  return { main, over: a.snapshot === null ? null : over, maxKnown }
}

/** up to one decimal: 62, 61.5 */
export function formatPoints(p: number): string {
  return String(Math.round(p * 10) / 10)
}

/** a copy of the exam whose subtasks carry the hand-set max points, so every consumer sees them */
export function withPointOverrides(e: StoredExam): StoredExam {
  const o = e.pointOverrides
  if (!o || !Object.keys(o).length) return e
  return {
    ...e,
    structure: {
      ...e.structure,
      tasks: e.structure.tasks.map((t) => ({
        ...t,
        subtasks: t.subtasks.map((s) => (s.id in o ? { ...s, points: o[s.id]! } : s)),
      })),
    },
  }
}
