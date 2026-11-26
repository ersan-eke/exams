import type { ExamStructure, McRule } from './exam'

/** which layer takes input; typed text and drawing are both kept and shown */
export type AnswerMode = 'type' | 'draw'

export interface Stroke {
  /** 0..1 of canvas */
  points: [number, number][]
  erase: boolean
  /** CSS color; missing on old strokes (= ink) */
  color?: string
  /** line width ÷ canvas width; missing on old strokes (= 2px pen, 16px eraser) */
  size?: number
}

/** what was written in one printed answer box (an answer area split over two pages has two) */
export interface AnswerPart {
  text: string
  /** drawn over the part's crops, points relative to them */
  strokes: Stroke[]
}

export interface Answer {
  mode: AnswerMode
  /** one per answer box, see answerParts(); may be shorter than the subtask's box list */
  parts: AnswerPart[]
  /** set by the former "On paper" mode, still counts as answered */
  done: boolean
  ticks: number[]
}

/** milliseconds */
export interface SubtaskTime {
  main: number
  over: number
}

export type Provider = 'anthropic' | 'google' | 'openrouter'

export interface RubricLine {
  item: string
  max: number
  source: 'solution' | 'inferred'
}

export interface LlmGrade {
  points: number
  min: number
  max: number
  certain: boolean
  basis: 'solution' | 'own_solution'
  provider: Provider
  model: string
  rubric: (RubricLine & { hit: number; note: string })[]
  feedback: string
}

export interface Grade {
  main?: number
  over?: number
  comment?: string
  /** the grader's pen marks on each version, one stroke list per answer part */
  marks?: Partial<Record<'main' | 'over', Stroke[][]>>
  /** the LLM's suggestion per version */
  llm?: Partial<Record<'main' | 'over', LlmGrade>>
}

export interface ViewState {
  shown: string[]
  folded: string[]
  expandedTasks: string[]
  outlineCollapsed: boolean
}

export interface Attempt {
  id: string
  examId: string
  status: 'running' | 'handed_in'
  fresh: boolean
  startedAt: number
  timeLimitMs: number
  includedTaskIds: string[]
  /** ms after start */
  attendanceAt: number | null
  attendanceDone: boolean
  mcRule: McRule
  extended: boolean
  answers: Record<string, Answer>
  snapshot: Record<string, Answer> | null
  handedInAt: number | null
  time: Record<string, SubtaskTime>
  view: ViewState
  grades: Record<string, Grade>
  solutionExamId: string | null
  /** set by Finish grading; the results then show points per subtask */
  gradedAt?: number | null
  /** ms epoch of the last local or pulled edit; sync compares it across devices */
  editedAt?: number
}

export interface StoredExam {
  id: string
  title: string
  structure: ExamStructure
  createdAt: number
  hasInk: boolean
  /** set when uploaded as the solution for this attempt id (kept out of Recent) */
  solutionFor?: string
  /** SHA-256 (hex) of the uploaded PDF bytes; the same file again reuses this exam */
  fingerprint?: string
  /** max points set by hand per subtask id; wins over printed and derived points (see withPointOverrides) */
  pointOverrides?: Record<string, number>
  /** groups exams in My exams and Statistics; missing = guessed from the title (see subjectOf) */
  subject?: string
  /** moved to the Hidden section of My exams and left out of Recent and Statistics */
  hidden?: boolean
  /** rubric per subtask id (of a solution exam), reused when grading later answers */
  rubrics?: Record<string, RubricLine[]>
  /** ms epoch of the last local or pulled edit; sync compares it across devices */
  editedAt?: number
}
