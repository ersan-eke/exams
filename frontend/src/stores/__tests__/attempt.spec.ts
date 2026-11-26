import 'fake-indexeddb/auto'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { dirtyIds, getAttempt, getExam, putAttempt, putExam, storeRemoteAttempt } from '@/lib/db'
import { GradeError, streamGrade, type LlmJob } from '@/lib/grading'
import { useAttemptStore } from '../attempt'
import { ans, attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import type { Attempt, LlmGrade } from '@/types/attempt'

vi.mock('@/lib/db', async (orig) => {
  const db = await orig<typeof import('@/lib/db')>()
  return { ...db, getAttempt: vi.fn(db.getAttempt) }
})
vi.mock('@/lib/grading', async (orig) => ({
  ...(await orig<typeof import('@/lib/grading')>()),
  streamGrade: vi.fn(),
}))

const T0 = 1_000_000_000_000
const LIMIT = 60_000

const structure = exam([
  task('A1', '1', [sub('A1a', 'a', 1)]),
  task('A2', '2', [sub('A2a', 'a', 1), sub('A2b', 'b', 1), sub('A2c', 'c', 1)]),
])

async function seed(p: Partial<Attempt> = {}): Promise<string> {
  const id = crypto.randomUUID()
  await putExam({ id: 'ex', title: 'X', structure, createdAt: 1, hasInk: false })
  await putAttempt(
    attempt({
      id,
      examId: 'ex',
      startedAt: T0,
      timeLimitMs: LIMIT,
      includedTaskIds: ['A1', 'A2'],
      view: { shown: ['A1a'], folded: [], expandedTasks: ['A1'], outlineCollapsed: false },
      ...p,
    }),
  )
  return id
}

describe('attempt store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
    vi.setSystemTime(T0)
  })
  afterEach(() => vi.useRealTimers())

  it('a load that finishes after a newer one does not replace it', async () => {
    const real = (await vi.importActual<typeof import('@/lib/db')>('@/lib/db')).getAttempt
    const first = await seed()
    const second = await seed()
    let release!: () => void
    vi.mocked(getAttempt).mockImplementationOnce(async (id) => {
      await new Promise<void>((r) => (release = r))
      return real(id)
    })
    const s = useAttemptStore()
    const slow = s.load(first)
    await s.load(second)
    release()
    await slow
    expect(s.attempt?.id).toBe(second)
  })

  it('adds tick time only to shown, unfolded subtasks', async () => {
    const id = await seed({
      view: {
        shown: ['A2b', 'A2c'],
        folded: ['A2b'],
        expandedTasks: ['A2'],
        outlineCollapsed: false,
      },
    })
    const s = useAttemptStore()
    await s.load(id)
    expect(s.openIds).toEqual(['A2c'])
    for (let i = 0; i <= 3; i++) s.tick(T0 + i * 1000)
    expect(s.attempt!.time.A2c!.main).toBe(3000)
    expect(s.attempt!.time.A2b).toBeUndefined()
  })

  it('caps a single tick delta at 5 s', async () => {
    const id = await seed()
    const s = useAttemptStore()
    await s.load(id)
    s.tick(T0)
    s.tick(T0 + 30_000)
    expect(s.attempt!.time.A1a!.main).toBe(5000)
  })

  it('snapshots and opens timeup at the limit; extend sends time to overtime', async () => {
    const id = await seed()
    const s = useAttemptStore()
    await s.load(id)
    s.tick(T0)
    s.setAnswer('A1a', { parts: [{ text: 'hello', strokes: [] }] })
    s.tick(LIMIT - 1000 + T0)
    expect(s.modal).toBeNull()
    expect(s.attempt!.snapshot).toBeNull()
    s.tick(T0 + LIMIT)
    expect(s.attempt!.snapshot).toEqual({ A1a: ans({ text: 'hello' }) })
    expect(s.modal).toBe('timeup')
    s.setAnswer('A1a', { parts: [{ text: 'changed', strokes: [] }] })
    expect(s.attempt!.snapshot!.A1a!.parts[0]!.text).toBe('hello')
    s.extend()
    expect(s.modal).toBeNull()
    expect(s.attempt!.extended).toBe(true)
    const main = s.attempt!.time.A1a!.main
    s.tick(T0 + LIMIT + 1000)
    s.tick(T0 + LIMIT + 2000)
    expect(s.modal).toBeNull()
    expect(s.attempt!.time.A1a!.main).toBe(main)
    expect(s.attempt!.time.A1a!.over).toBe(2000)
    expect(s.isOvertime).toBe(true)
    expect(s.clockText).toBe('+0:02')
  })

  it('takes the snapshot on the first tick when reopened past the limit', async () => {
    vi.setSystemTime(T0 + LIMIT + 600_000)
    const id = await seed({ answers: { A1a: ans({ text: 'x' }) } })
    const s = useAttemptStore()
    await s.load(id)
    s.tick()
    expect(s.attempt!.snapshot).toEqual({ A1a: ans({ text: 'x' }) })
    expect(s.modal).toBe('timeup')
    expect(s.clockText.startsWith('+')).toBe(true)
  })

  it('opens attendance at attendanceAt, pauses time, and finishes', async () => {
    const id = await seed({ attendanceAt: 2000 })
    const s = useAttemptStore()
    await s.load(id)
    s.tick(T0)
    s.tick(T0 + 1000)
    expect(s.modal).toBeNull()
    s.tick(T0 + 2000)
    expect(s.modal).toBe('attendance')
    const t = s.attempt!.time.A1a!.main
    s.tick(T0 + 3000)
    s.tick(T0 + 4000)
    expect(s.attempt!.time.A1a!.main).toBe(t)
    s.finishAttendance()
    expect(s.attempt!.attendanceDone).toBe(true)
    expect(s.modal).toBeNull()
    s.tick(T0 + 5000)
    expect(s.modal).toBeNull()
    expect(s.attempt!.time.A1a!.main).toBe(t + 1000)
  })

  it('never opens a pending attendance in overtime', async () => {
    vi.setSystemTime(T0 + LIMIT + 1000)
    const id = await seed({ attendanceAt: 2000, extended: true })
    const s = useAttemptStore()
    await s.load(id)
    s.tick()
    expect(s.modal).toBeNull()
  })

  it('toggleShown keeps exam order and never empties shown', async () => {
    const id = await seed({
      view: { shown: ['A2b'], folded: [], expandedTasks: ['A2'], outlineCollapsed: false },
    })
    const s = useAttemptStore()
    await s.load(id)
    s.toggleShown('A1a')
    s.toggleShown('A2a')
    expect(s.attempt!.view.shown).toEqual(['A1a', 'A2a', 'A2b'])
    s.toggleShown('A1a')
    s.toggleShown('A2b')
    expect(s.attempt!.view.shown).toEqual(['A2a'])
    s.toggleShown('A2a')
    expect(s.attempt!.view.shown).toEqual(['A2a'])
  })

  it('view actions: showOnly, goNext/goPrev, folds, tasks, outline', async () => {
    const id = await seed()
    const s = useAttemptStore()
    await s.load(id)
    s.showOnly('A2a')
    expect(s.attempt!.view.shown).toEqual(['A2a'])
    expect(s.attempt!.view.expandedTasks).toEqual(['A1', 'A2'])
    s.toggleShown('A2b')
    s.goNext()
    expect(s.attempt!.view.shown).toEqual(['A2c'])
    s.goNext()
    expect(s.attempt!.view.shown).toEqual(['A2c'])
    s.goPrev()
    s.goPrev()
    s.goPrev()
    s.goPrev()
    expect(s.attempt!.view.shown).toEqual(['A1a'])
    s.toggleFold('A1a')
    expect(s.attempt!.view.folded).toEqual(['A1a'])
    s.toggleFold('A1a')
    expect(s.attempt!.view.folded).toEqual([])
    s.toggleTask('A1')
    expect(s.attempt!.view.expandedTasks).toEqual(['A2'])
    s.setOutlineCollapsed(true)
    expect(s.attempt!.view.outlineCollapsed).toBe(true)
  })

  it('setAnswer patches an empty answer; setGrade merges', async () => {
    const id = await seed()
    const s = useAttemptStore()
    await s.load(id)
    s.setAnswer('A1a', { ticks: [1] })
    expect(s.attempt!.answers.A1a).toEqual(ans({ ticks: [1] }))
    s.setGrade('A1a', { main: 1 })
    s.setGrade('A1a', { over: 0.5 })
    expect(s.attempt!.grades.A1a).toEqual({ main: 1, over: 0.5 })
  })

  it('hand-in flow persists immediately; before the limit leaves snapshot null', async () => {
    const id = await seed()
    const s = useAttemptStore()
    await s.load(id)
    s.requestHandIn()
    expect(s.modal).toBe('handin')
    s.cancelHandIn()
    expect(s.modal).toBeNull()
    s.requestHandIn()
    await s.handIn()
    expect(s.modal).toBeNull()
    const stored = (await getAttempt(id))!
    expect(stored.status).toBe('handed_in')
    expect(stored.handedInAt).toBe(T0)
    expect(stored.snapshot).toBeNull()
  })

  it('persists debounced and survives a reload', async () => {
    const id = await seed()
    const s = useAttemptStore()
    await s.load(id)
    s.setAnswer('A1a', { parts: [{ text: 'saved', strokes: [] }] })
    vi.advanceTimersByTime(400)
    expect((await getAttempt(id))!.answers.A1a).toBeUndefined()
    vi.advanceTimersByTime(200)
    await vi.waitFor(async () => expect((await getAttempt(id))!.answers.A1a).toBeDefined())
    setActivePinia(createPinia())
    const s2 = useAttemptStore()
    await s2.load(id)
    expect(s2.attempt!.answers.A1a!.parts[0]!.text).toBe('saved')
  })

  it('flushes when the page becomes hidden', async () => {
    const id = await seed()
    const s = useAttemptStore()
    await s.load(id)
    s.tick(T0)
    s.setAnswer('A1a', { parts: [{ text: 'now', strokes: [] }] })
    const spy = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.waitFor(async () => expect((await getAttempt(id))!.answers.A1a?.parts[0]?.text).toBe('now'))
    // hidden tab adds no time
    s.tick(T0 + 1000)
    expect(s.attempt!.time.A1a).toBeUndefined()
    spy.mockRestore()
  })
  it('a handed-in attempt is locked: answers, view and hand-in are no-ops', async () => {
    const id = await seed({ status: 'handed_in', handedInAt: T0 - 5 })
    const s = useAttemptStore()
    await s.load(id)
    s.setAnswer('A1a', { parts: [{ text: 'late', strokes: [] }] })
    s.showOnly('A2a')
    s.toggleFold('A1a')
    s.setOutlineCollapsed(true)
    s.extend()
    s.finishAttendance()
    await s.handIn()
    expect(s.attempt!.answers.A1a).toBeUndefined()
    expect(s.attempt!.view.shown).toEqual(['A1a'])
    expect(s.attempt!.view.folded).toEqual([])
    expect(s.attempt!.view.outlineCollapsed).toBe(false)
    expect(s.attempt!.extended).toBe(false)
    expect(s.attempt!.handedInAt).toBe(T0 - 5)
    // grading still works on handed-in attempts
    s.setGrade('A1a', { main: 1 })
    expect(s.attempt!.grades.A1a).toEqual({ main: 1 })
  })

  it('clearGrade removes one field or the whole grade', async () => {
    const id = await seed({ status: 'handed_in', grades: { A1a: { main: 1, over: 0.5 } } })
    const s = useAttemptStore()
    await s.load(id)
    s.clearGrade('A1a', 'over')
    expect(s.attempt!.grades.A1a).toEqual({ main: 1 })
    s.clearGrade('A1a')
    expect(s.attempt!.grades.A1a).toBeUndefined()
  })

  it('hand-in over the limit takes the snapshot first when no tick did', async () => {
    const id = await seed({ answers: { A1a: ans({ text: 'x' }) } })
    const s = useAttemptStore()
    await s.load(id)
    vi.setSystemTime(T0 + LIMIT + 1000)
    await s.handIn()
    const stored = (await getAttempt(id))!
    expect(stored.snapshot).toEqual({ A1a: ans({ text: 'x' }) })
  })

  it('flushes pending saves on pagehide', async () => {
    const id = await seed()
    const s = useAttemptStore()
    await s.load(id)
    s.setAnswer('A1a', { parts: [{ text: 'bye', strokes: [] }] })
    window.dispatchEvent(new Event('pagehide'))
    // no timer advance: only the pagehide flush can have saved it
    let saved
    for (let i = 0; i < 50 && !saved; i++) {
      await new Promise((r) => setImmediate(r))
      saved = (await getAttempt(id))!.answers.A1a
    }
    expect(saved?.parts[0]?.text).toBe('bye')
  })
  it('keeps a handed-in attempt locally when localStorage refuses the outbox mark', async () => {
    const id = await seed()
    const s = useAttemptStore()
    await s.load(id)
    s.setAnswer('A1a', { parts: [{ text: 'typed', strokes: [] }] })
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError')
    })
    try {
      await s.handIn()
    } finally {
      spy.mockRestore()
    }
    const saved = (await getAttempt(id))!
    expect(saved.status).toBe('handed_in')
    expect(saved.answers.A1a?.parts[0]?.text).toBe('typed')
    expect(dirtyIds('attempts')).not.toContain(id) // stays on this device until edited again (db.ts shortcut)
  })
})

describe('attempt store LLM grading', () => {
  const stream = vi.mocked(streamGrade)
  const grade = (p: Partial<LlmGrade> = {}): LlmGrade => ({
    points: 1, min: 1, max: 1, certain: true, basis: 'own_solution', provider: 'anthropic', model: 'm',
    rubric: [{ item: 'r', max: 1, source: 'inferred', hit: 1, note: '' }], feedback: 'ok', ...p,
  })
  const job = (id: string, version: 'main' | 'over' = 'main', rubricTarget: LlmJob['rubricTarget'] = null, provider = 'anthropic'): LlmJob => ({
    key: `${id}:${version}`, subtaskId: id, version, rubricTarget, build: async () => ({ provider }) as never,
  })
  const KEYS = { anthropic: 'k', google: 'kg', openrouter: 'ko' }
  const tick = async () => { for (let i = 0; i < 20; i++) await new Promise((r) => setImmediate(r)) }
  /** every streamGrade call waits on its own deferred */
  let calls: { key: string; signal: AbortSignal; resolve: (g: LlmGrade) => void; reject: (e: unknown) => void }[]
  let inFlight: number
  let maxInFlight: number
  beforeEach(() => {
    setActivePinia(createPinia())
    calls = []
    inFlight = maxInFlight = 0
    stream.mockReset()
    stream.mockImplementation((body, key, signal, onThinking) => {
      onThinking('hm')
      inFlight++
      maxInFlight = Math.max(maxInFlight, inFlight)
      return new Promise<LlmGrade>((resolve, reject) => {
        const end = () => inFlight--
        calls.push({ key, signal, resolve: (g) => (end(), resolve(g)), reject: (e) => (end(), reject(e)) })
      })
    })
  })

  it('runs at most 3 at a time and counts progress', async () => {
    const id = await seed()
    const s = useAttemptStore()
    await s.load(id)
    const ids = ['A1a', 'A2a', 'A2b', 'A2c', 'A1a']
    const jobs = ids.map((x, i) => job(x, i === 4 ? 'over' : 'main'))
    const run = s.gradeWithLlm(jobs, {}, KEYS)
    await tick()
    expect(calls.length).toBe(3)
    expect(s.llm.total).toBe(5)
    expect(Object.keys(s.llm.pending).length).toBe(3)
    expect(s.llm.pending['A1a:main']).toBe('hm')
    for (let i = 0; i < 5; i++) {
      calls[i]!.resolve(grade())
      await tick()
    }
    await run
    expect(maxInFlight).toBe(3)
    expect(s.llm.done).toBe(5)
    expect(s.llm.pending).toEqual({})
  })

  it('stores the result next to the self-grade and saves it', async () => {
    const id = await seed({ grades: { A1a: { main: 1, llm: { over: grade({ feedback: 'old' }) } } } })
    const s = useAttemptStore()
    await s.load(id)
    const run = s.gradeWithLlm([job('A1a')], {}, KEYS)
    await tick()
    calls[0]!.resolve(grade({ feedback: 'new' }))
    await run
    const g = (await getAttempt(id))!.grades.A1a!
    expect(g.main).toBe(1)
    expect(g.llm!.main!.feedback).toBe('new')
    expect(g.llm!.over!.feedback).toBe('old')
  })

  it('saves a solution rubric to the target exam, but not for own_solution', async () => {
    const id = await seed()
    await putExam({ id: 'sol', title: 'S', structure, createdAt: 1, hasInk: true })
    const s = useAttemptStore()
    await s.load(id)
    const target = { examId: 'sol', subtaskId: 'A1a' }
    const run = s.gradeWithLlm([job('A1a', 'main', target), job('A2a', 'main', { examId: 'sol', subtaskId: 'A2a' })], {}, KEYS)
    await tick()
    calls[0]!.resolve(grade({ basis: 'solution', rubric: [{ item: 'x', max: 2, source: 'inferred', hit: 1, note: 'n' }] }))
    calls[1]!.resolve(grade({ basis: 'own_solution' }))
    await run
    const e = (await getExam('sol'))!
    expect(e.rubrics).toEqual({ A1a: [{ item: 'x', max: 2, source: 'inferred' }] })
  })

  it('records a GradeError as the message and carries on', async () => {
    const id = await seed()
    const s = useAttemptStore()
    await s.load(id)
    const run = s.gradeWithLlm([job('A1a'), job('A2a')], {}, KEYS)
    await tick()
    calls[0]!.reject(new GradeError('bad_key'))
    calls[1]!.resolve(grade())
    await run
    expect(s.llm.errors['A1a:main']).toBe('Your API key was rejected.')
    expect(s.attempt!.grades.A2a!.llm!.main).toBeDefined()
    expect(s.llm.done).toBe(2)
  })

  it('stop aborts in-flight jobs silently, never starts queued ones, keeps finished grades', async () => {
    const id = await seed()
    const s = useAttemptStore()
    await s.load(id)
    const jobs = ['A1a', 'A2a', 'A2b', 'A2c'].map((x) => job(x))
    const run = s.gradeWithLlm(jobs, {}, KEYS)
    await tick()
    calls[0]!.resolve(grade())
    await tick() // 4th starts
    s.stopLlm()
    expect(calls.slice(1).every((c) => c.signal.aborted)).toBe(true)
    calls.slice(1).forEach((c) => c.reject(new DOMException('x', 'AbortError')))
    await run
    expect(calls.length).toBe(4)
    expect(s.llm.pending).toEqual({})
    expect(s.llm.errors).toEqual({})
    expect(s.llm.total).toBe(0)
    expect(s.attempt!.grades.A1a!.llm!.main).toBeDefined()
  })

  it('writes nothing when another attempt was loaded meanwhile', async () => {
    const id = await seed()
    const other = await seed()
    const s = useAttemptStore()
    await s.load(id)
    const run = s.gradeWithLlm([job('A1a')], {}, KEYS)
    await tick()
    await s.load(other)
    calls[0]!.resolve(grade())
    await run
    expect((await getAttempt(id))!.grades.A1a).toBeUndefined()
    expect((await getAttempt(other))!.grades.A1a).toBeUndefined()
    expect(s.attempt!.grades.A1a).toBeUndefined()
  })

  it('skips graded versions without force; regrade sends them again', async () => {
    const id = await seed({ grades: { A1a: { llm: { main: grade() } } } })
    const s = useAttemptStore()
    await s.load(id)
    await s.gradeWithLlm([job('A1a')], {}, KEYS)
    expect(calls.length).toBe(0)
    const run = s.regrade('A1a:main', KEYS)
    await tick()
    expect(calls.length).toBe(1)
    calls[0]!.resolve(grade({ feedback: 'again' }))
    await run
    expect(s.attempt!.grades.A1a!.llm!.main!.feedback).toBe('again')
  })

  it('sends the key of the provider the request was built for', async () => {
    const id = await seed()
    const s = useAttemptStore()
    await s.load(id)
    const run = s.gradeWithLlm([job('A1a', 'main', null, 'google')], {}, KEYS)
    await tick()
    expect(calls[0]!.key).toBe('kg')
    calls[0]!.resolve(grade())
    await run
  })

  it('regrade works after prepareLlm, without a prior gradeWithLlm', async () => {
    const id = await seed({ grades: { A1a: { llm: { main: grade() } } } })
    const s = useAttemptStore()
    await s.load(id)
    s.prepareLlm([job('A1a')], { A1b: 'auto' })
    expect(s.llm.skipped).toEqual({ A1b: 'auto' })
    expect(calls.length).toBe(0)
    const run = s.regrade('A1a:main', KEYS)
    await tick()
    expect(calls.length).toBe(1)
    calls[0]!.resolve(grade({ feedback: 'fresh' }))
    await run
    expect(s.attempt!.grades.A1a!.llm!.main!.feedback).toBe('fresh')
  })

  it('regrade during a run joins it instead of stopping it', async () => {
    // A2c is already graded, so the pass runs 3 jobs; regrade adds it as a 4th
    const id = await seed({ grades: { A2c: { llm: { main: grade() } } } })
    const s = useAttemptStore()
    await s.load(id)
    const run = s.gradeWithLlm(['A1a', 'A2a', 'A2b', 'A2c'].map((x) => job(x)), {}, KEYS)
    await tick()
    expect(calls.length).toBe(3)
    const again = s.regrade('A2c:main', KEYS)
    await tick()
    expect(calls.every((c) => !c.signal.aborted)).toBe(true)
    expect(s.llm.total).toBe(4)
    calls[0]!.resolve(grade()) // frees a slot for the joined job
    await tick()
    expect(calls.length).toBe(4)
    calls.slice(1).forEach((c) => c.resolve(grade()))
    await run
    await again
    expect(calls.every((c) => !c.signal.aborted)).toBe(true)
    expect(s.llm.done).toBe(4)
  })

  it('saves rubrics of concurrent results for one solution exam without losing lines', async () => {
    const id = await seed()
    await putExam({ id: 'sol', title: 'S', structure, createdAt: 1, hasInk: true })
    const s = useAttemptStore()
    await s.load(id)
    const run = s.gradeWithLlm(
      ['A1a', 'A2a'].map((x) => job(x, 'main', { examId: 'sol', subtaskId: x })),
      {},
      KEYS,
    )
    await tick()
    const sol = (item: string) => grade({ basis: 'solution', rubric: [{ item, max: 1, source: 'inferred', hit: 1, note: '' }] })
    calls[0]!.resolve(sol('a'))
    calls[1]!.resolve(sol('b'))
    await run
    expect(Object.keys((await getExam('sol'))!.rubrics!).sort()).toEqual(['A1a', 'A2a'])
  })

  it('load adopts the solution another attempt of the exam has', async () => {
    await seed({ status: 'handed_in', handedInAt: T0 + 1, startedAt: T0 + 5, solutionExamId: 'sol-x' })
    const id = await seed({ status: 'handed_in', handedInAt: T0 + 1 })
    const store = useAttemptStore()
    await store.load(id)
    expect(store.attempt!.solutionExamId).toBe('sol-x')
    expect((await getAttempt(id))!.solutionExamId).toBe('sol-x')
  })

  it('reloadIfReplaced reloads the open attempt keeping its view', async () => {
    const id = await seed({ status: 'handed_in', handedInAt: T0 + 1 })
    const store = useAttemptStore()
    await store.load(id)
    store.attempt!.view.expandedTasks = ['A1', 'A2'] // in-memory view change, not saved
    const remote = { ...(await getAttempt(id))!, grades: { A1a: { main: 1 } }, editedAt: 5 } as Attempt
    const { view: _v, ...wire } = remote
    await storeRemoteAttempt(wire)
    await store.reloadIfReplaced([id])
    expect(store.attempt!.grades).toEqual({ A1a: { main: 1 } })
    expect(store.attempt!.view.expandedTasks).toEqual(['A1', 'A2'])
    const before = dirtyIds('attempts')
    await store.flush()
    expect(dirtyIds('attempts')).toEqual(before)
  })

  it('reloadIfReplaced keeps a pending unsaved edit, which then goes out as the newer one', async () => {
    const id = await seed({ status: 'handed_in', handedInAt: T0 + 1 })
    const store = useAttemptStore()
    await store.load(id)
    store.setGrade('A1a', { main: 2 }) // schedules a save, not flushed yet
    const { view: _v, ...wire } = { ...(await getAttempt(id))!, grades: { A1a: { main: 1 } }, editedAt: 5 } as Attempt
    await storeRemoteAttempt(wire)
    await store.reloadIfReplaced([id])
    expect(store.attempt!.grades.A1a!.main).toBe(2)
    await store.flush()
    const saved = (await getAttempt(id))!
    expect(saved.grades.A1a!.main).toBe(2)
    expect(saved.editedAt!).toBeGreaterThan(5)
    expect(dirtyIds('attempts')).toContain(id)
  })

  it('reloadIfReplaced leaves a running attempt and other ids alone', async () => {
    const id = await seed()
    const store = useAttemptStore()
    await store.load(id)
    store.attempt!.grades = { A1a: { main: 1 } }
    await store.reloadIfReplaced([id])
    expect(store.attempt!.grades).toEqual({ A1a: { main: 1 } })
  })
})
