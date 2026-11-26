import { computed, reactive, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { attemptsForExam, getAttempt, getExam, putAttempt, putExam } from '@/lib/db'
import { withPointOverrides } from '@/lib/scoring'
import { examSolutionId } from '@/lib/solution'
import {
  elapsed,
  formatClock,
  formatOvertime,
  isOvertime as overtimeAt,
  remaining,
} from '@/lib/clock'
import { addTime } from '@/lib/timing'
import { emptyAnswer } from '@/lib/answers'
import { neighbors, orderedShown } from '@/lib/sheet'
import { GradeError, gradeErrorMessage, streamGrade, type GradeRequest, type LlmJob, type SkipReason } from '@/lib/grading'
import { lastPulled, pulled } from '@/lib/sync'
import { useSettingsStore } from './settings'
import type { Answer, Attempt, Grade, Provider, StoredExam } from '@/types/attempt'

export type AttemptModal = null | 'attendance' | 'timeup' | 'handin'

const SAVE_DELAY_MS = 500
const LLM_CONCURRENCY = 3
/** longest gap a single tick may credit to subtasks (sleep, closed tab) */
const MAX_TICK_MS = 5000

const toggle = (list: string[], id: string) =>
  list.includes(id) ? list.filter((x) => x !== id) : [...list, id]

const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v))

export const useAttemptStore = defineStore('attempt', () => {
  const attempt = ref<Attempt | null>(null)
  const exam = ref<StoredExam | null>(null)
  const now = ref(Date.now())
  const modal = ref<AttemptModal>(null)

  let lastTick: number | null = null
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function flush(): Promise<void> {
    if (saveTimer !== null) clearTimeout(saveTimer)
    saveTimer = null
    if (!attempt.value) return Promise.resolve()
    return putAttempt(clone(attempt.value))
  }

  function scheduleSave() {
    if (saveTimer !== null) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => void flush(), SAVE_DELAY_MS)
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden' && saveTimer !== null) void flush()
    })
    // pagehide also fires where visibilitychange doesn't (e.g. some mobile tab closes)
    window.addEventListener('pagehide', () => {
      if (saveTimer !== null) void flush()
    })
  }

  /** the attempt, only while it can still be changed (answers, view, hand-in) */
  const running = () => (attempt.value?.status === 'running' ? attempt.value : null)

  const openIds = computed(() => {
    const v = attempt.value?.view
    return v ? v.shown.filter((id) => !v.folded.includes(id)) : []
  })
  const isOvertime = computed(() => (attempt.value ? overtimeAt(attempt.value, now.value) : false))
  const clockText = computed(() => {
    const a = attempt.value
    if (!a) return ''
    return isOvertime.value
      ? formatOvertime(elapsed(a, now.value) - a.timeLimitMs)
      : formatClock(remaining(a, now.value))
  })

  let loading = 0
  async function load(attemptId: string): Promise<void> {
    const mine = ++loading // a newer load() makes this one drop its result
    stopLlm()
    if (saveTimer !== null) await flush()
    const a = await getAttempt(attemptId)
    if (mine !== loading) return
    if (!a) throw new Error('attempt not found')
    const e = await getExam(a.examId)
    if (mine !== loading) return
    if (!e) throw new Error('exam not found')
    // a solution uploaded with another attempt of this exam applies here too
    const inherited = a.solutionExamId || e.hasInk ? null : examSolutionId(await attemptsForExam(a.examId))
    if (mine !== loading) return
    if (inherited) {
      a.solutionExamId = inherited
      await putAttempt(a)
      if (mine !== loading) return
    }
    attempt.value = a
    exam.value = withPointOverrides(e)
    now.value = Date.now()
    modal.value = null
    lastTick = null
  }

  /** a pull replaced the open attempt (or its exam): re-read it, keep this device's view */
  async function reloadIfReplaced(ids: string[]): Promise<void> {
    const a = attempt.value
    if (!a || a.status === 'running') return
    const fresh = ids.includes(a.id) ? await getAttempt(a.id) : undefined
    const e = lastPulled.exams.includes(a.examId) ? await getExam(a.examId) : undefined
    if (attempt.value !== a) return // another attempt was opened meanwhile
    // an edit still waiting to be saved wins: its flush stamps a newer editedAt and the next push sends it
    if (fresh && saveTimer === null) attempt.value = { ...fresh, view: a.view }
    if (e) exam.value = withPointOverrides(e)
  }
  watch(pulled, () => void reloadIfReplaced(lastPulled.attempts))

  function tick(t = Date.now()) {
    now.value = t
    const a = attempt.value
    const prev = lastTick
    lastTick = t
    if (!a || a.status !== 'running') return
    if (prev !== null && document.visibilityState === 'visible' && modal.value === null) {
      const dt = Math.min(Math.max(0, t - prev), MAX_TICK_MS)
      if (dt > 0) a.time = addTime(a.time, openIds.value, dt, overtimeAt(a, prev))
    }
    const over = overtimeAt(a, t)
    if (over && a.snapshot === null) a.snapshot = clone(a.answers)
    if (modal.value === null) {
      if (over && !a.extended) modal.value = 'timeup'
      else if (
        !over &&
        a.attendanceAt !== null &&
        !a.attendanceDone &&
        elapsed(a, t) >= a.attendanceAt
      )
        modal.value = 'attendance'
    }
    scheduleSave()
  }

  function finishAttendance() {
    if (!running()) return
    attempt.value!.attendanceDone = true
    if (modal.value === 'attendance') modal.value = null
    scheduleSave()
  }

  function extend() {
    if (!running()) return
    attempt.value!.extended = true
    if (modal.value === 'timeup') modal.value = null
    scheduleSave()
  }

  function requestHandIn() {
    if (running() && modal.value === null) modal.value = 'handin'
  }

  function cancelHandIn() {
    if (modal.value === 'handin') modal.value = null
  }

  async function handIn(): Promise<void> {
    const a = running()
    if (!a) return
    const t = Date.now()
    if (overtimeAt(a, t) && a.snapshot === null) a.snapshot = clone(a.answers)
    a.status = 'handed_in'
    a.handedInAt = t
    now.value = a.handedInAt
    modal.value = null
    await flush()
  }

  function mutateView(fn: (v: Attempt['view']) => void) {
    const a = running()
    if (!a) return
    fn(a.view)
    scheduleSave()
  }

  function showOnly(subtaskId: string) {
    const taskId = exam.value?.structure.tasks.find((t) =>
      t.subtasks.some((s) => s.id === subtaskId),
    )?.id
    mutateView((v) => {
      v.shown = [subtaskId]
      if (taskId && !v.expandedTasks.includes(taskId))
        v.expandedTasks = [...v.expandedTasks, taskId]
    })
  }

  function toggleShown(subtaskId: string) {
    const e = exam.value
    if (!e) return
    mutateView((v) => {
      const next = toggle(v.shown, subtaskId)
      if (next.length > 0) v.shown = orderedShown(e.structure, next)
    })
  }

  function toggleFold(blockId: string) {
    mutateView((v) => (v.folded = toggle(v.folded, blockId)))
  }

  function toggleTask(taskId: string) {
    mutateView((v) => (v.expandedTasks = toggle(v.expandedTasks, taskId)))
  }

  function setOutlineCollapsed(value: boolean) {
    mutateView((v) => (v.outlineCollapsed = value))
  }

  function step(dir: 'prev' | 'next') {
    const a = attempt.value
    const e = exam.value
    if (!a || !e) return
    const ordered = orderedShown(e.structure, a.view.shown)
    const last = ordered[ordered.length - 1]
    if (last === undefined) return
    const target = neighbors(e.structure, a, last)[dir]
    if (target !== null) showOnly(target)
  }

  const goNext = () => step('next')
  const goPrev = () => step('prev')

  function setAnswer(subtaskId: string, patch: Partial<Answer>) {
    const a = running()
    if (!a) return
    const cur = a.answers[subtaskId] ?? emptyAnswer(useSettingsStore().defaultAnswerMode)
    a.answers[subtaskId] = { ...cur, ...patch }
    scheduleSave()
  }

  function setGrade(subtaskId: string, g: Grade) {
    const a = attempt.value
    if (!a) return
    a.grades[subtaskId] = { ...a.grades[subtaskId], ...g }
    scheduleSave()
  }

  /** remove one grade field, or the whole grade (back to automatic MC points) */
  function clearGrade(subtaskId: string, field?: keyof Grade) {
    const a = attempt.value
    if (!a || !a.grades[subtaskId]) return
    if (field === undefined) delete a.grades[subtaskId]
    else {
      const { [field]: _removed, ...rest } = a.grades[subtaskId]
      if (Object.keys(rest).length) a.grades[subtaskId] = rest
      else delete a.grades[subtaskId]
    }
    scheduleSave()
  }

  /** grading done: persist right away, the results page reads it next */
  async function finishGrading(): Promise<void> {
    if (!attempt.value) return
    attempt.value.gradedAt = Date.now()
    await flush()
  }

  /** link a solution exam to the loaded attempt and persist right away */
  async function setSolutionExam(examId: string): Promise<void> {
    if (!attempt.value) return
    attempt.value.solutionExamId = examId
    await flush()
  }

  // LLM grading run: not persisted
  const llm = reactive({
    pending: {} as Record<string, string>,
    errors: {} as Record<string, string>,
    skipped: {} as Record<string, SkipReason>,
    total: 0,
    done: 0,
  })
  interface Pass {
    ctl: AbortController
    id: string
    keys: Record<Provider, string>
    queue: LlmJob[]
    next: number
    active: number
    workers: Promise<void>[]
  }
  let pass: Pass | null = null
  let lastJobs = new Map<string, LlmJob>()
  // rubric saves read-modify-write the exam, so they go one at a time
  let rubricSave: Promise<unknown> = Promise.resolve()

  function stopLlm() {
    pass?.ctl.abort()
    pass = null
    llm.pending = {}
    llm.total = 0
    llm.done = 0
  }

  // a pass is dead once stopped or once another attempt is loaded
  const alive = (p: Pass) => !p.ctl.signal.aborted && attempt.value?.id === p.id

  async function runJob(p: Pass, job: LlmJob) {
    const grades = attempt.value!.grades
    llm.pending[job.key] = ''
    try {
      const req = await job.build()
      const result = await streamGrade(req, p.keys[req.provider], p.ctl.signal, (t) => {
        if (alive(p)) llm.pending[job.key] = t
      })
      if (!alive(p)) return
      setGrade(job.subtaskId, { llm: { ...grades[job.subtaskId]?.llm, [job.version]: result } })
      await flush()
      if (result.basis === 'solution' && job.rubricTarget) {
        const { examId, subtaskId } = job.rubricTarget
        const lines = result.rubric.map(({ item, max, source }) => ({ item, max, source }))
        const save = rubricSave.then(async () => {
          const e = await getExam(examId)
          if (!e) return
          const saved = { ...e, rubrics: { ...e.rubrics, [subtaskId]: lines } }
          await putExam(saved)
          if (exam.value?.id === examId) exam.value = withPointOverrides(saved)
        })
        rubricSave = save.catch(() => {})
        await save
      }
    } catch (err) {
      if (!alive(p)) return
      llm.errors[job.key] = gradeErrorMessage(err instanceof GradeError ? err.code : '')
    } finally {
      if (alive(p)) {
        delete llm.pending[job.key]
        llm.done++
      }
    }
  }

  async function work(p: Pass) {
    p.active++
    try {
      while (alive(p) && p.next < p.queue.length) await runJob(p, p.queue[p.next++]!)
    } finally {
      p.active--
    }
  }

  /** add jobs to the running pass, or start a new one */
  async function run(todo: LlmJob[], keys: Record<Provider, string>, join = false): Promise<void> {
    const a = attempt.value
    if (!a || todo.length === 0) return
    let p = pass
    if (join && p && p.active > 0 && alive(p)) {
      p.queue.push(...todo)
      llm.total += todo.length
    } else {
      stopLlm()
      p = pass = { ctl: new AbortController(), id: a.id, keys, queue: todo, next: 0, active: 0, workers: [] }
      llm.total = todo.length
    }
    const spawn = Math.min(LLM_CONCURRENCY - p.active, p.queue.length - p.next)
    for (let i = 0; i < spawn; i++) p.workers.push(work(p))
    await Promise.all(p.workers)
  }

  async function gradeWithLlm(
    jobs: LlmJob[],
    skipped: Record<string, SkipReason>,
    keys: Record<Provider, string>,
    opts: { force?: boolean } = {},
  ): Promise<void> {
    const a = attempt.value
    if (!a) return
    lastJobs = new Map(jobs.map((j) => [j.key, j]))
    llm.skipped = skipped
    llm.errors = {}
    await run(opts.force ? jobs : jobs.filter((j) => !a.grades[j.subtaskId]?.llm?.[j.version]), keys)
  }

  /** register the plan so regrade() works without a run (builds are lazy, nothing is sent) */
  function prepareLlm(jobs: LlmJob[], skipped: Record<string, SkipReason>) {
    lastJobs = new Map(jobs.map((j) => [j.key, j]))
    llm.skipped = skipped
  }

  /** the request a job would send, for the dev-only preview; null when the subtask isn't sent */
  async function buildLlmRequest(jobKey: string): Promise<GradeRequest | null> {
    const job = lastJobs.get(jobKey)
    return job ? job.build() : null
  }

  async function regrade(jobKey: string, keys: Record<Provider, string>): Promise<void> {
    const job = lastJobs.get(jobKey)
    if (!job) return
    delete llm.errors[jobKey]
    await run([job], keys, true)
  }

  return {
    attempt,
    llm,
    gradeWithLlm,
    prepareLlm,
    buildLlmRequest,
    regrade,
    stopLlm,
    exam,
    now,
    modal,
    openIds,
    isOvertime,
    clockText,
    load,
    reloadIfReplaced,
    flush,
    tick,
    finishAttendance,
    extend,
    requestHandIn,
    cancelHandIn,
    handIn,
    showOnly,
    toggleShown,
    toggleFold,
    toggleTask,
    setOutlineCollapsed,
    goNext,
    goPrev,
    setAnswer,
    setGrade,
    clearGrade,
    setSolutionExam,
    finishGrading,
  }
})
