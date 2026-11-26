import { defineStore } from 'pinia'
import { uploadExam } from '@/lib/api'
import { guessSubject } from '@/lib/stats'
import {
  attemptsForExam,
  getAttempt,
  emptyView,
  getExam,
  listAttempts,
  listExams,
  putAttempt,
  putExam,
  putImages,
  runningAttempt,
} from '@/lib/db'
import { withPointOverrides } from '@/lib/scoring'
import { examSolutionId } from '@/lib/solution'
import { useAttemptStore } from './attempt'
import type { Attempt, StoredExam } from '@/types/attempt'
import type { McRule } from '@/types/exam'

function readBytes(file: Blob): Promise<ArrayBuffer> {
  if (typeof file.arrayBuffer === 'function') return file.arrayBuffer()
  // older Blob implementations (jsdom in tests) only offer FileReader
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result as ArrayBuffer)
    r.onerror = () => reject(r.error)
    r.readAsArrayBuffer(file)
  })
}

async function sha256(file: Blob): Promise<string> {
  const bytes = new Uint8Array(await readBytes(file))
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))
  return Array.from(digest, (b) => b.toString(16).padStart(2, '0')).join('')
}

export const useLibraryStore = defineStore('library', () => {
  /** the same PDF again reuses its stored exam, so a retake is marked not fresh (spec 4.5) */
  async function importUpload(file: File): Promise<string> {
    const fingerprint = await sha256(file)
    const known = (await listExams()).find((e) => !e.solutionFor && e.fingerprint === fingerprint)
    if (known) return known.id
    const guess = guessSubject(file.name.replace(/\.pdf$/i, ''))
    // 'Other' is a display bucket, never a server course
    const res = await uploadExam(file, undefined, guess === 'Other' ? undefined : guess)
    const id = res.examId
    const hasInk = res.solution_images !== null
    await putImages(id, 'blank', res.images)
    if (res.solution_images) await putImages(id, 'ink', res.solution_images)
    await putExam({
      id,
      title: res.exam.source.replace(/\.pdf$/i, ''),
      structure: res.exam,
      createdAt: Date.now(),
      hasInk,
      fingerprint,
    })
    return id
  }

  /** upload a solution PDF after the exam: stored as its own exam (with ink), linked to the attempt and to the exam's
   * other attempts that have none, since it is the whole exam's solution */
  async function attachSolution(attemptId: string, file: File): Promise<void> {
    const res = await uploadExam(file, 'solution')
    const id = res.examId
    await putImages(id, 'blank', res.images)
    await putImages(id, 'ink', res.solution_images ?? res.images)
    await putExam({
      id,
      title: res.exam.source.replace(/\.pdf$/i, ''),
      structure: res.exam,
      createdAt: Date.now(),
      hasInk: true,
      solutionFor: attemptId,
    })
    const store = useAttemptStore()
    const a = await getAttempt(attemptId)
    if (!a) throw new Error('attempt not found')
    for (const other of await attemptsForExam(a.examId)) {
      if (other.id === attemptId || other.solutionExamId) continue
      if (other.id === store.attempt?.id) await store.setSolutionExam(id)
      else await putAttempt({ ...other, solutionExamId: id })
    }
    if (store.attempt?.id === attemptId) await store.setSolutionExam(id)
    else await putAttempt({ ...a, solutionExamId: id })
  }

  async function recent(limit = 5): Promise<{ exam: StoredExam; latest: Attempt | undefined }[]> {
    const exams = (await listExams()).filter((e) => !e.solutionFor && !e.hidden).slice(0, limit)
    return Promise.all(
      exams.map(async (exam) => {
        const attempts = await attemptsForExam(exam.id)
        const latest = attempts.sort((a, b) => b.startedAt - a.startedAt)[0]
        return { exam, latest }
      }),
    )
  }

  function running(): Promise<Attempt | undefined> {
    return runningAttempt()
  }

  async function startAttempt(
    examId: string,
    opts: {
      title: string
      subject?: string
      timeLimitMin: number
      includedTaskIds: string[]
      attendance: boolean
      mcRule: McRule
    },
  ): Promise<string> {
    if (await runningAttempt()) throw new Error('another exam is running')
    const exam = await getExam(examId)
    if (!exam) throw new Error('exam not found')
    const previous = await attemptsForExam(examId)
    const first = exam.structure.tasks.find((t) => opts.includedTaskIds.includes(t.id))
    const id = crypto.randomUUID()
    await putExam({ ...exam, title: opts.title, ...(opts.subject && { subject: opts.subject }) })
    await putAttempt({
      id,
      examId,
      status: 'running',
      fresh: !previous.some((a) => a.status === 'handed_in'),
      startedAt: Date.now(),
      timeLimitMs: opts.timeLimitMin * 60_000,
      includedTaskIds: opts.includedTaskIds,
      attendanceAt: opts.attendance ? 120_000 + Math.floor(Math.random() * 1_680_000) : null,
      attendanceDone: false,
      mcRule: opts.mcRule,
      extended: false,
      answers: {},
      snapshot: null,
      handedInAt: null,
      time: {},
      view: emptyView(first),
      grades: {},
      solutionExamId: examSolutionId(previous),
    })
    return id
  }

  /** every stored exam (solutions included, for their MC keys) and every attempt */
  async function catalog(): Promise<{ exams: StoredExam[]; attempts: Attempt[] }> {
    const [exams, attempts] = await Promise.all([listExams(), listAttempts()])
    return { exams: exams.map(withPointOverrides), attempts }
  }

  async function updateExam(id: string, patch: Pick<StoredExam, 'subject' | 'hidden'>) {
    const exam = await getExam(id)
    if (!exam) throw new Error('exam not found')
    await putExam({ ...exam, ...patch })
  }

  /** set (or, with null, remove) a subtask's max points on the exam; affects all its attempts */
  async function setPoints(examId: string, subtaskId: string, points: number | null) {
    if (points !== null && !(Number.isFinite(points) && points >= 0)) return
    const exam = await getExam(examId)
    if (!exam) throw new Error('exam not found')
    const { [subtaskId]: _, ...rest } = exam.pointOverrides ?? {}
    const saved = { ...exam, pointOverrides: points === null ? rest : { ...rest, [subtaskId]: points } }
    await putExam(saved)
    const attempt = useAttemptStore()
    if (attempt.exam?.id === examId) attempt.exam = withPointOverrides(saved)
  }

  return { importUpload, attachSolution, recent, running, startAttempt, catalog, updateExam, setPoints }
})
