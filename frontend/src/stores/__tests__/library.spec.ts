import 'fake-indexeddb/auto'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { UploadError } from '@/lib/api'
import { guessSubject } from '@/lib/stats'
import * as api from '@/lib/api'
import { getExam, getImage, listExams, putExam, putAttempt } from '@/lib/db'
import { useLibraryStore } from '../library'
import { attempt, exam as examFixture, sub, task } from '@/lib/__tests__/fixtures'
import { useAttemptStore } from '../attempt'
import type { ExamStructure } from '@/types/exam'

vi.mock('@/lib/api', async (orig) => ({ ...(await orig<typeof api>()), uploadExam: vi.fn() }))

const png = () => new Blob([new Uint8Array([1, 2, 3])], { type: 'image/png' })
const file = new File(['x'], 'Klausur.pdf', { type: 'application/pdf' })
/** distinct bytes per test, since uploads of the same bytes reuse the stored exam */
const pdf = (bytes: string, name = 'Klausur.pdf') => new File([bytes], name, { type: 'application/pdf' })

describe('library store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('sends the subject guessed from the filename with the upload', async () => {
    vi.mocked(api.uploadExam).mockResolvedValue({
      exam: { source: 'x.pdf', tasks: [] } as unknown as ExamStructure,
      images: { 'p1.png': png() },
      solution_images: null,
      examId: crypto.randomUUID(),
    })
    const f = pdf('subject bytes', 'Analysis 1 Klausur WS2023.pdf')
    await useLibraryStore().importUpload(f)
    expect(api.uploadExam).toHaveBeenLastCalledWith(f, undefined, guessSubject('Analysis 1 Klausur WS2023'))
  })

  it('stores an upload under the exam id the server assigned', async () => {
    vi.mocked(api.uploadExam).mockResolvedValue({
      exam: { source: 'x.pdf', tasks: [] } as unknown as ExamStructure,
      images: { 'p1.png': png() },
      solution_images: null,
      examId: 'server-id-1',
    })
    const id = await useLibraryStore().importUpload(pdf('server id bytes'))
    expect(id).toBe('server-id-1')
    expect(await getExam('server-id-1')).toBeDefined()
  })

  it('sends no subject when the filename has none', async () => {
    vi.mocked(api.uploadExam).mockResolvedValue({
      exam: { source: 'x.pdf', tasks: [] } as unknown as ExamStructure,
      images: { 'p1.png': png() },
      solution_images: null,
      examId: crypto.randomUUID(),
    })
    const f = pdf('no subject bytes', '2024 Endterm.pdf')
    await useLibraryStore().importUpload(f)
    expect(api.uploadExam).toHaveBeenLastCalledWith(f, undefined, undefined)
  })

  it('stores structure and both image variants for a solution exam', async () => {
    vi.mocked(api.uploadExam).mockResolvedValue({
      exam: { source: 'Klausur.pdf', tasks: [] } as unknown as ExamStructure,
      images: { 'p1.png': png() },
      solution_images: { 'p1.png': png() },
      examId: crypto.randomUUID(),
    })
    const id = await useLibraryStore().importUpload(file)
    const stored = await getExam(id)
    expect(stored?.title).toBe('Klausur')
    expect(stored?.hasInk).toBe(true)
    expect(stored?.structure.source).toBe('Klausur.pdf')
    expect(await getImage(id, 'blank', 'p1.png')).toBeDefined()
    expect(await getImage(id, 'ink', 'p1.png')).toBeDefined()
    const recent = await useLibraryStore().recent()
    expect(recent[0]!.exam.id).toBe(id)
    expect(recent[0]!.latest).toBeUndefined()
    expect(await useLibraryStore().running()).toBeUndefined()
  })

  it('sets hasInk false without solution images', async () => {
    vi.mocked(api.uploadExam).mockResolvedValue({
      exam: { source: 'A.pdf', tasks: [] } as unknown as ExamStructure,
      images: { 'p1.png': png() },
      solution_images: null,
      examId: crypto.randomUUID(),
    })
    const id = await useLibraryStore().importUpload(pdf('no ink'))
    expect((await getExam(id))?.hasInk).toBe(false)
    expect(await getImage(id, 'ink', 'p1.png')).toBeUndefined()
  })

  it('stores nothing and propagates when upload fails', async () => {
    const before = (await listExams()).length
    vi.mocked(api.uploadExam).mockRejectedValue(new UploadError('scanned'))
    await expect(useLibraryStore().importUpload(pdf('scanned'))).rejects.toMatchObject({
      code: 'scanned',
    })
    expect((await listExams()).length).toBe(before)
  })

  it('reuses the stored exam when the same file is uploaded again, so a retake is not fresh', async () => {
    vi.mocked(api.uploadExam).mockClear()
    vi.mocked(api.uploadExam).mockResolvedValue({
      exam: { source: 'R.pdf', tasks: [{ id: 't1', subtasks: [{ id: 't1a' }] }], issues: [] } as unknown as ExamStructure,
      images: { 'p1.png': png() },
      solution_images: null,
      examId: crypto.randomUUID(),
    })
    const lib = useLibraryStore()
    const before = (await listExams()).length
    const id = await lib.importUpload(pdf('retake bytes', 'R.pdf'))
    expect((await getExam(id))?.fingerprint).toMatch(/^[0-9a-f]{64}$/)
    const again = await lib.importUpload(pdf('retake bytes', 'R copy.pdf'))
    expect(again).toBe(id)
    expect(api.uploadExam).toHaveBeenCalledTimes(1)
    expect((await listExams()).length).toBe(before + 1)
    expect((await lib.recent(100)).filter((r) => r.exam.id === id)).toHaveLength(1)

    const { getAttempt, putAttempt } = await import('@/lib/db')
    const opts = { title: 'R', timeLimitMin: 90, includedTaskIds: ['t1'], attendance: false, mcRule: { kind: 'all_or_nothing' } as const }
    const first = await lib.startAttempt(id, opts)
    expect((await getAttempt(first))!.fresh).toBe(true)
    await putAttempt({ ...(await getAttempt(first))!, status: 'handed_in' })
    const second = await lib.startAttempt(await lib.importUpload(pdf('retake bytes', 'R.pdf')), opts)
    expect((await getAttempt(second))!.fresh).toBe(false)
    await putAttempt({ ...(await getAttempt(second))!, status: 'handed_in' })
  })

  it('a different file is stored as a new exam', async () => {
    vi.mocked(api.uploadExam).mockResolvedValue({
      exam: { source: 'D.pdf', tasks: [] } as unknown as ExamStructure,
      images: {},
      solution_images: null,
      examId: 'id-one',
    })
    const a = await useLibraryStore().importUpload(pdf('one'))
    vi.mocked(api.uploadExam).mockResolvedValue({
      exam: { source: 'D.pdf', tasks: [] } as unknown as ExamStructure,
      images: {},
      solution_images: null,
      examId: 'id-two',
    })
    const b = await useLibraryStore().importUpload(pdf('two'))
    expect(a).not.toBe(b)
  })
})

describe('startAttempt', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    // earlier attempts from other tests must not count as running
    const { runningAttempt, getAttempt, putAttempt } = await import('@/lib/db')
    const r = await runningAttempt()
    if (r) await putAttempt({ ...(await getAttempt(r.id))!, status: 'handed_in' })
  })

  const structure = {
    source: 'S.pdf',
    tasks: [
      { id: 't1', subtasks: [{ id: 't1a' }, { id: 't1b' }] },
      { id: 't2', subtasks: [{ id: 't2a' }] },
    ],
    issues: [],
  } as unknown as ExamStructure
  const opts = (over = {}) => ({
    title: 'New title',
    timeLimitMin: 90,
    includedTaskIds: ['t2'],
    attendance: true,
    mcRule: { kind: 'all_or_nothing' } as const,
    ...over,
  })
  async function seed(id: string) {
    const { putExam } = await import('@/lib/db')
    await putExam({ id, title: 'Old', structure, createdAt: 1, hasInk: false })
  }

  it('hides an exam from recent and sets its subject', async () => {
    await seed('eh')
    const lib = useLibraryStore()
    await lib.updateExam('eh', { hidden: true, subject: 'GBS' })
    const { getExam: ge } = await import('@/lib/db')
    expect(await ge('eh')).toMatchObject({ hidden: true, subject: 'GBS', title: 'Old' })
    expect((await lib.recent(100)).some((r) => r.exam.id === 'eh')).toBe(false)
    expect((await lib.catalog()).exams.some((e) => e.id === 'eh')).toBe(true)
  })

  it('creates a running attempt with initial view and updates title', async () => {
    await seed('e1')
    const id = await useLibraryStore().startAttempt('e1', opts())
    const { getAttempt, getExam: ge, putAttempt } = await import('@/lib/db')
    const a = (await getAttempt(id))!
    expect(a.status).toBe('running')
    expect(a.fresh).toBe(true)
    expect(a.timeLimitMs).toBe(90 * 60_000)
    expect(a.view.shown).toEqual(['t2a'])
    expect(a.view.expandedTasks).toEqual(['t2'])
    expect(a.attendanceAt).toBeGreaterThanOrEqual(120_000)
    expect(a.attendanceAt).toBeLessThan(1_800_000)
    expect(a.snapshot).toBeNull()
    expect(a.extended).toBe(false)
    expect((await ge('e1'))?.title).toBe('New title')
    await putAttempt({ ...a, status: 'handed_in' })
    const id2 = await useLibraryStore().startAttempt('e1', opts({ attendance: false }))
    const b = (await getAttempt(id2))!
    expect(b.fresh).toBe(false)
    expect(b.attendanceAt).toBeNull()
  })

  it('links an uploaded solution to every attempt of the exam, and new attempts start with it', async () => {
    await seed('es')
    const { getAttempt } = await import('@/lib/db')
    await putAttempt(attempt({ id: 'es-1', examId: 'es', status: 'handed_in', startedAt: 1 }))
    await putAttempt(attempt({ id: 'es-2', examId: 'es', status: 'handed_in', startedAt: 2 }))
    vi.mocked(api.uploadExam).mockResolvedValue({
      examId: 'es-sol', exam: { ...structure, source: 'S-sol.pdf' }, images: {}, solution_images: {},
    } as unknown as Awaited<ReturnType<typeof api.uploadExam>>)
    await useLibraryStore().attachSolution('es-1', new File(['x'], 'S-sol.pdf'))
    expect((await getAttempt('es-1'))?.solutionExamId).toBe('es-sol')
    expect((await getAttempt('es-2'))?.solutionExamId).toBe('es-sol')
    const id = await useLibraryStore().startAttempt('es', opts())
    expect((await getAttempt(id))?.solutionExamId).toBe('es-sol')
  })

  it('rejects while another exam is running', async () => {
    await seed('e2')
    await seed('e3')
    await useLibraryStore().startAttempt('e2', opts())
    await expect(useLibraryStore().startAttempt('e3', opts())).rejects.toThrow(
      'another exam is running',
    )
  })
})

describe('attachSolution', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('stores the solution as its own exam with ink images and links it to the attempt', async () => {
    const { putAttempt, getAttempt } = await import('@/lib/db')
    const { attempt } = await import('@/lib/__tests__/fixtures')
    const attemptId = crypto.randomUUID()
    await putAttempt(attempt({ id: attemptId, status: 'handed_in', grades: { x: { main: 1 } } }))
    vi.mocked(api.uploadExam).mockResolvedValue({
      exam: { source: 'Loesung.pdf', tasks: [] } as unknown as ExamStructure,
      images: { 'p1.png': png() },
      solution_images: { 'p1.png': png() },
      examId: crypto.randomUUID(),
    })
    await useLibraryStore().attachSolution(attemptId, file)
    expect(api.uploadExam).toHaveBeenLastCalledWith(file, 'solution')
    const a = (await getAttempt(attemptId))!
    expect(a.solutionExamId).not.toBeNull()
    expect(a.grades).toEqual({ x: { main: 1 } })
    const sol = (await getExam(a.solutionExamId!))!
    expect(sol.hasInk).toBe(true)
    expect(sol.title).toBe('Loesung')
    expect(await getImage(sol.id, 'ink', 'p1.png')).toBeDefined()
    expect(sol.solutionFor).toBe(attemptId)
    const recent = await useLibraryStore().recent(100)
    expect(recent.some((r) => r.exam.id === sol.id)).toBe(false)
  })

  it('updates the loaded attempt in the attempt store', async () => {
    const { putAttempt, putExam } = await import('@/lib/db')
    const { attempt } = await import('@/lib/__tests__/fixtures')
    const { useAttemptStore } = await import('../attempt')
    const attemptId = crypto.randomUUID()
    await putExam({ id: 'ex-sol', title: 'X', structure: { tasks: [] } as unknown as ExamStructure, createdAt: 1, hasInk: false })
    await putAttempt(attempt({ id: attemptId, examId: 'ex-sol', status: 'handed_in' }))
    const store = useAttemptStore()
    await store.load(attemptId)
    vi.mocked(api.uploadExam).mockResolvedValue({
      exam: { source: 'L.pdf', tasks: [] } as unknown as ExamStructure,
      images: {},
      solution_images: {},
      examId: crypto.randomUUID(),
    })
    await useLibraryStore().attachSolution(attemptId, file)
    expect(store.attempt?.solutionExamId).not.toBeNull()
  })

  it('setPoints persists, null removes, invalid input is ignored, later loads see it', async () => {
    setActivePinia(createPinia())
    const structure = examFixture([task('A1', '1', [sub('a', 'a)', 2), sub('b', 'b)', null)])])
    await putExam({ id: 'pe', title: 'X', structure, createdAt: 1, hasInk: false })
    await putAttempt(attempt({ id: 'pa1', examId: 'pe' }))
    await putAttempt(attempt({ id: 'pa2', examId: 'pe' }))
    const lib = useLibraryStore()
    const store = useAttemptStore()
    await store.load('pa1')
    await lib.setPoints('pe', 'b', 3)
    expect((await getExam('pe'))!.pointOverrides).toEqual({ b: 3 })
    expect(store.exam!.structure.tasks[0]!.subtasks[1]!.points).toBe(3) // refreshed at once
    await lib.setPoints('pe', 'b', -1)
    await lib.setPoints('pe', 'b', NaN)
    expect((await getExam('pe'))!.pointOverrides).toEqual({ b: 3 })
    await store.load('pa2')
    expect(store.exam!.structure.tasks[0]!.subtasks[1]!.points).toBe(3)
    await lib.setPoints('pe', 'b', null)
    expect((await getExam('pe'))!.pointOverrides).toEqual({})
    expect(store.exam!.structure.tasks[0]!.subtasks[1]!.points).toBeNull()
  })
})
