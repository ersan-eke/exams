import type { Attempt } from '@/types/attempt'
import type { ExamStructure, Subtask } from '@/types/exam'

/** an exam's uploaded solution: the newest one linked to any of its attempts (it applies to the whole exam) */
export function examSolutionId(attempts: Attempt[]): string | null {
  const linked = attempts.filter((a) => a.solutionExamId).sort((a, b) => b.startedAt - a.startedAt)
  return linked[0]?.solutionExamId ?? null
}

/** Map each exam subtask id to its solution subtask: same id, else same task number + label. */
export function matchSolution(
  exam: ExamStructure,
  solution: ExamStructure,
): Record<string, Subtask> {
  const byId = new Map<string, Subtask>()
  const byNumberLabel = new Map<string, Subtask>()
  for (const t of solution.tasks) {
    for (const s of t.subtasks) {
      byId.set(s.id, s)
      byNumberLabel.set(`${t.number}\u0000${s.label}`, s)
    }
  }
  const out: Record<string, Subtask> = {}
  for (const t of exam.tasks) {
    for (const s of t.subtasks) {
      const m = byId.get(s.id) ?? byNumberLabel.get(`${t.number}\u0000${s.label}`)
      if (m) out[s.id] = m
    }
  }
  return out
}

/** MC answer key per subtask id: the exam's own key, else the matched solution subtask's key */
export function mcKeys(
  exam: ExamStructure,
  solution: ExamStructure | null,
): Record<string, number[]> {
  const matches = solution ? matchSolution(exam, solution) : {}
  const out: Record<string, number[]> = {}
  for (const t of exam.tasks) {
    for (const s of t.subtasks) {
      const key = s.mc_key?.length ? s.mc_key : matches[s.id]?.mc_key
      if (key?.length) out[s.id] = key
    }
  }
  return out
}
