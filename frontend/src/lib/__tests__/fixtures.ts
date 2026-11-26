import type { ExamStructure, Subtask, Task } from '@/types/exam'
import type { Answer, Attempt, Stroke } from '@/types/attempt'

export function sub(id: string, label: string, points: number | null, extra: Partial<Subtask> = {}): Subtask {
  return { id, label, points, independent: false, regions: [], text: '', solution_text: '', ...extra }
}

export function task(id: string, number: string, subtasks: Subtask[], context: Task['context'] = []): Task {
  return { id, number, title: '', points: null, context, subtasks }
}

export function exam(tasks: Task[]): ExamStructure {
  return {
    source: 'x.pdf', page_count: 1, page_sizes: [[1, 1]], kind: 'digital', is_solution: false,
    total_points_stated: null, tasks, issues: [],
  }
}

/** text / strokes are shorthand for a single answer part */
export function ans(p: Partial<Answer> & { text?: string; strokes?: Stroke[] } = {}): Answer {
  const { text, strokes, ...rest } = p
  const parts = text !== undefined || strokes ? [{ text: text ?? '', strokes: strokes ?? [] }] : []
  return { mode: 'type', parts, done: false, ticks: [], ...rest }
}

export function attempt(p: Partial<Attempt> = {}): Attempt {
  return {
    id: 'a', examId: 'e', status: 'running', fresh: true, startedAt: 1000, timeLimitMs: 10_000,
    includedTaskIds: [], attendanceAt: null, attendanceDone: false, mcRule: { kind: 'all_or_nothing' },
    extended: false, answers: {}, snapshot: null, handedInAt: null, time: {},
    view: { shown: [], folded: [], expandedTasks: [], outlineCollapsed: false },
    grades: {}, solutionExamId: null, ...p,
  }
}
