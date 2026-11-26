import type { Attempt, StoredExam } from '@/types/attempt'
import { isAnswered } from './answers'
import { counted, formatPoints, isPractice, maxPoints, scores, subtaskScore } from './scoring'
import { includedTasks } from './sheet'
import { examSolutionId, mcKeys } from './solution'

const NOISE = new Set(
  'endterm midterm final retake repeat exam solution solutions sample mock klausur wiederholungsklausur wiederholung nachholklausur lösung lösungen loesung loesungen musterlösung musterloesung probeklausur probe hauptklausur semestralklausur mit with sol lsg quiz wdh tsk et mt rt lösungsvorschlag lösungvorschlag loesungsvorschlag losung losungen erklärungen erklarungen'.split(' '),
)

// shortcut: filename-only, and et/mt/rt count as noise anywhere; prefer the PDF's first-page course title once the pipeline extracts it
/** filename minus years, semesters and exam-kind words: "2024_Retake_GRNVS" → "GRNVS" */
export function guessSubject(title: string): string {
  const isNoise = (t: string) => NOISE.has(t.toLowerCase().replace(/[\d'’]+$/, ''))
  const tokens = title.normalize('NFC').split(/[\s_\-.]+/).filter(Boolean)
  const keep = tokens.filter(
    // a number right after an exam-kind word is its index ("quiz 3")
    (t, i) => !/^\d{2,}$/.test(t) && !/^(ws|ss|wise|sose)\d{0,4}(\/\d{2,4})?$/i.test(t) && !isNoise(t) && !(/^\d$/.test(t) && i > 0 && isNoise(tokens[i - 1]!)),
  )
  return keep.some((t) => /\p{L}/u.test(t)) ? keep.join(' ') : 'Other'
}

export const subjectOf = (e: StoredExam) => e.subject?.trim() || guessSubject(e.title)

/** exams the user uploaded as exams (solutions attached later are kept out) */
export const ownExams = (exams: StoredExam[]) => exams.filter((e) => !e.solutionFor)

/** subject → its exams, subjects sorted by name */
export function bySubject(exams: StoredExam[]): [string, StoredExam[]][] {
  const m = new Map<string, StoredExam[]>()
  for (const e of exams) m.set(subjectOf(e), [...(m.get(subjectOf(e)) ?? []), e])
  return [...m].sort(([a], [b]) => a.localeCompare(b))
}

export interface Row {
  attempt: Attempt
  exam: StoredExam
  /** main score, null until grading is finished */
  score: { main: number; max: number } | null
  /** 0 for a practice attempt from Claude, which is not timed */
  usedMs: number
  practice: boolean
}

/** each exam's solution (see examSolutionId), for attempts that were never linked to it */
function solutionsByExam(attempts: Attempt[]): Map<string, string | null> {
  const byExam = new Map<string, Attempt[]>()
  for (const a of attempts) byExam.set(a.examId, [...(byExam.get(a.examId) ?? []), a])
  return new Map([...byExam].map(([id, as]) => [id, examSolutionId(as)]))
}

function keysFor(a: Attempt, exam: StoredExam, all: Map<string, StoredExam>, solutions: Map<string, string | null>) {
  const id = a.solutionExamId ?? solutions.get(a.examId)
  const solution = id ? all.get(id) : undefined
  return mcKeys(exam.structure, solution?.structure ?? null)
}

/** handed-in attempts of the given exams (not of solutions), newest first */
export function attemptRows(exams: StoredExam[], attempts: Attempt[]): Row[] {
  const all = new Map(exams.map((e) => [e.id, e]))
  const solutions = solutionsByExam(attempts)
  return attempts
    .filter((a) => a.status === 'handed_in')
    .flatMap((attempt) => {
      const exam = all.get(attempt.examId)
      if (!exam || exam.solutionFor) return []
      const s = attempt.gradedAt ? scores(attempt, exam.structure, keysFor(attempt, exam, all, solutions)) : null
      return [
        {
          attempt,
          exam,
          score: s && { main: s.main, max: s.maxKnown },
          usedMs: isPractice(attempt) ? 0 : Math.max(0, (attempt.handedInAt ?? attempt.startedAt) - attempt.startedAt),
          practice: isPractice(attempt),
        },
      ]
    })
    .sort((x, y) => y.attempt.startedAt - x.attempt.startedAt)
}

export interface Group {
  /** max points of the questions in this group; null = unknown */
  points: number | null
  count: number
  avgTimeMs: number
  /** null when none of them is graded yet */
  avgScore: number | null
  avgMax: number | null
}

export interface Summary {
  exams: number
  questions: number
  timeMs: number
  /** summed over graded attempts; null when none is graded */
  points: { main: number; max: number; graded: number } | null
  mc: Group | null
  /** non-MC questions grouped by their points, smallest first, unknown last */
  long: Group[]
}

interface Acc {
  count: number
  /** questions with a time: not from a practice attempt */
  timed: number
  time: number
  scored: number
  score: number
  max: number
}

const toGroup = (points: number | null, g: Acc): Group => ({
  points,
  count: g.count,
  avgTimeMs: g.timed ? g.time / g.timed : 0,
  avgScore: g.scored ? g.score / g.scored : null,
  avgMax: g.scored ? g.max / g.scored : null,
})

export function summarize(rows: Row[], exams: StoredExam[]): Summary {
  const all = new Map(exams.map((e) => [e.id, e]))
  const mc: Acc = { count: 0, timed: 0, time: 0, scored: 0, score: 0, max: 0 }
  const long = new Map<number | null, Acc>()
  let questions = 0
  const solutions = solutionsByExam(rows.map((r) => r.attempt))
  for (const { attempt: a, exam } of rows) {
    const keys = keysFor(a, exam, all, solutions)
    for (const task of includedTasks(exam.structure, a)) {
      for (const s of task.subtasks) {
        if (!counted(a, s)) continue
        if (isAnswered(a.answers[s.id])) questions++
        const isMc = (s.mc_options?.length ?? 0) > 0
        const max = maxPoints(task, s, a.mcRule, keys[s.id])
        const acc = isMc ? mc : long.get(max) ?? { count: 0, timed: 0, time: 0, scored: 0, score: 0, max: 0 }
        if (!isMc) long.set(max, acc)
        const t = a.time[s.id]
        acc.count++
        if (!isPractice(a)) {
          acc.timed++
          acc.time += (t?.main ?? 0) + (t?.over ?? 0)
        }
        // MC is graded automatically; the rest only counts once grading is finished
        if (max !== null && (isMc || a.gradedAt)) {
          acc.scored++
          acc.score += subtaskScore(a, task, s, keys[s.id]).main
          acc.max += max
        }
      }
    }
  }
  const graded = rows.filter((r) => r.score)
  return {
    exams: rows.length,
    questions,
    timeMs: rows.reduce((sum, r) => sum + r.usedMs, 0),
    points: graded.length
      ? {
          main: graded.reduce((sum, r) => sum + r.score!.main, 0),
          max: graded.reduce((sum, r) => sum + r.score!.max, 0),
          graded: graded.length,
        }
      : null,
    mc: mc.count ? toGroup(null, mc) : null,
    long: [...long]
      .sort(([a], [b]) => (a ?? Infinity) - (b ?? Infinity))
      .map(([points, g]) => toGroup(points, g)),
  }
}

/** local calendar day, e.g. "2026-10-22" */
export function dayKey(ts: number): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export const scoreText = (r: Row | undefined) =>
  !r
    ? 'not taken'
    : r.score
      ? `${formatPoints(r.score.main)} / ${formatPoints(r.score.max)} P`
      : 'not graded'

export const formatDate = (ts: number) =>
  new Date(ts).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

/** "1 h 05 min", "12 min" */
export function formatDuration(ms: number): string {
  const min = Math.round(ms / 60_000)
  const h = Math.floor(min / 60)
  return h ? `${h} h ${String(min % 60).padStart(2, '0')} min` : `${min} min`
}
