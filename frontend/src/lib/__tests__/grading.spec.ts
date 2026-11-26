import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ans, attempt, exam, sub, task } from './fixtures'
import type { StoredExam, Stroke } from '@/types/attempt'
import type { ExamStructure } from '@/types/exam'

vi.mock('@/lib/db', () => ({
  getImage: vi.fn(async (examId: string, variant: string, name: string) => new Blob([`${examId}/${variant}/${name}`])),
}))

import { getImage } from '@/lib/db'
import {
  GradeError,
  gradeErrorMessage,
  planGrading,
  similarSubtasks,
  skipReason,
  sseEvents,
  streamGrade,
  evalCasesJsonl,
  sheetLayout,
  type GradeRequest,
} from '../grading'

const region = (image: string | null) => ({ page: 0, bbox: { x0: 0, y0: 0, x1: 1, y1: 1 }, image })
const stored = (id: string, structure: ExamStructure, extra: Partial<StoredExam> = {}): StoredExam => ({
  id, title: 'Mathe ' + id, structure, createdAt: 0, hasInk: false, subject: 'Mathe', ...extra,
})
const stroke: Stroke = { points: [[0, 0], [1, 1]], erase: false }

beforeEach(() => {
  vi.mocked(getImage).mockClear()
  vi.stubGlobal('createImageBitmap', async () => ({ width: 10, height: 5, close() {} }))
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    new Proxy({}, { get: () => () => undefined, set: () => true }) as unknown as CanvasRenderingContext2D,
  )
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,PNG')
})

describe('skipReason', () => {
  const s = sub('s', 'a', 2, { mc_options: [{ region: 0, bbox: { x0: 0, y0: 0, x1: 1, y1: 1 }, text: 'A' }] })
  const t = task('t', '1', [s])
  it('classifies', () => {
    expect(skipReason(t, sub('n', '', null), ans({ text: 'x' }), null)).toBeNull() // graded on a 1-point scale
    expect(skipReason(t, s, undefined, null)).toBe('no_answer')
    expect(skipReason(t, s, ans({ ticks: [0] }), [0])).toBe('auto')
    expect(skipReason(t, s, ans({ ticks: [0] }), null)).toBeNull()
  })
})

describe('similarSubtasks', () => {
  const mk = (id: string, text: string, extra: Partial<StoredExam> = {}, is_solution = false) =>
    stored(id, { ...exam([task('t' + id, '1', [sub('s' + id, '', 1, { text })])]), is_solution }, extra)
  const target = sub('q', '', 1, { text: 'Berechnen Sie die Ableitung der Funktion' })
  const lib = [
    mk('a', 'Berechnen Sie die Ableitung der Funktion', { hasInk: true }),
    mk('b', 'Berechnen Sie die Ableitung dieser Funktion nochmal', {}, true),
    mk('c', 'Berechnen Sie die Ableitung der Funktion', { hasInk: true, subject: 'Physik' }),
    mk('d', 'Berechnen Sie die Ableitung der Funktion', {}),
    mk('e', 'Völlig anderer Text über Integrale', { hasInk: true }),
    mk('f', 'Berechnen Sie die Ableitung der Funktion', { hasInk: true }),
    mk('g', 'Berechnen Sie die Ableitung der Funktion', { hasInk: true }),
  ]
  it('same subject, solutions only, ranked, max 2, threshold, excludes', () => {
    const r = similarSubtasks(target, lib, 'Mathe', ['f'])
    expect(r.map((x) => x.exam.id)).toEqual(['a', 'g'])
    expect(similarSubtasks(target, lib, 'Mathe', ['a', 'f', 'g']).map((x) => x.exam.id)).toEqual(['b'])
  })
})

describe('planGrading', () => {
  const q = sub('q1', 'a', 3, { text: 'Frage', regions: [region('q.png')] })
  const t = task('t1', '1', [q])
  const base = (over = {}) => ({
    exam: stored('e', exam([t])),
    attempt: attempt({ includedTaskIds: ['t1'], answers: { q1: ans({ text: 'Antwort' }) } }),
    solutionExam: null,
    mcKeys: {},
    library: [],
    provider: 'google' as const,
    model: 'm1',
    ...over,
  })
  const solSub = sub('q1', 'a', 3, { solution_text: 'Lösung', regions: [region('s.png')] })
  const solExam = stored('sol', exam([task('t1', '1', [solSub])]), { rubrics: { q1: [{ item: 'x', max: 3, source: 'solution' }] } })

  it('matched solution', async () => {
    const { jobs } = planGrading(base({ solutionExam: solExam }))
    expect(jobs).toHaveLength(1)
    const j = jobs[0]!
    expect(j.key).toBe('q1:main')
    expect(j.rubricTarget).toEqual({ examId: 'sol', subtaskId: 'q1' })
    const r = await j.build()
    expect(r).toMatchObject({ provider: 'google', model: 'm1', points: 3, references: [] })
    expect(r.solution!.rubric).toEqual([{ item: 'x', max: 3, source: 'solution' }])
    expect(r.solution!.images).toHaveLength(1)
    expect(getImage).toHaveBeenCalledWith('sol', 'ink', 's.png')
    expect(getImage).toHaveBeenCalledWith('e', 'blank', 'q.png')
    expect(r.answer).toEqual({ text: 'Antwort', images: [] })
  })

  it('ink exam uses itself', async () => {
    const own = stored('e', exam([task('t1', '1', [{ ...q, solution_text: 'L' }])]), { hasInk: true })
    const j = planGrading(base({ exam: own })).jobs[0]!
    expect(j.rubricTarget).toEqual({ examId: 'e', subtaskId: 'q1' })
    const r = await j.build()
    // the ink crop already shows the question, so the blank one isn't sent too
    expect(getImage).toHaveBeenCalledWith('e', 'ink', 'q.png')
    expect(getImage).not.toHaveBeenCalledWith('e', 'blank', 'q.png')
    expect(r.question.images).toEqual([])
    expect(r.solution!.images).toHaveLength(1)
  })

  it('no solution: references', async () => {
    const refEx = stored('r', exam([task('tr', '1', [sub('rq', '', 2, { text: 'Frage', solution_text: 'RL', regions: [region('r.png')] })])]), { hasInk: true })
    const j = planGrading(base({ library: [refEx] })).jobs[0]!
    expect(j.rubricTarget).toBeNull()
    const r = await j.build()
    expect(r.solution).toBeNull()
    expect(r.references).toHaveLength(1)
    expect(r.references[0]!.points).toBe(2)
    // a solution exam that matches nothing behaves the same
    const other = stored('o', exam([task('tx', '9', [sub('zz', 'z', 1)])]))
    const j2 = planGrading(base({ library: [refEx], solutionExam: other })).jobs[0]!
    expect((await j2.build()).solution).toBeNull()
  })

  it('signed in: no reference images, the subject goes along so the server adds material as text', async () => {
    const refEx = stored('r', exam([task('tr', '1', [sub('rq', '', 2, { text: 'Frage', solution_text: 'RL' })])]), { hasInk: true })
    const r = await planGrading({ ...base({ library: [refEx] }), material: true }).jobs[0]!.build()
    expect(r.references).toEqual([])
    expect(r.subject).toBeTruthy()
    expect(r.exclude_exams).toEqual(['e'])
    const withSol = await planGrading({ ...base({ library: [refEx], solutionExam: solExam }), material: true }).jobs[0]!.build()
    expect(withSol.exclude_exams).toEqual(['e', 'sol'])
    expect((await planGrading(base({ library: [refEx] })).jobs[0]!.build()).subject).toBeUndefined()
  })

  it('withReferences adds both', async () => {
    const refEx = stored('r', exam([task('tr', '1', [sub('rq', '', 2, { text: 'Frage' })])]), { hasInk: true })
    const r = await planGrading({ ...base({ solutionExam: solExam, library: [refEx] }), withReferences: true }).jobs[0]!.build()
    expect(r.solution).not.toBeNull()
    expect(r.references).toHaveLength(1)
  })

  it('overtime gives two jobs from snapshot and answers', async () => {
    const a = attempt({
      includedTaskIds: ['t1'],
      snapshot: { q1: ans({ text: 'alt' }) },
      answers: { q1: ans({ text: 'neu' }) },
    })
    const { jobs } = planGrading(base({ attempt: a }))
    expect(jobs.map((j) => j.key)).toEqual(['q1:main', 'q1:over'])
    expect((await jobs[0]!.build()).answer.text).toBe('alt')
    expect((await jobs[1]!.build()).answer.text).toBe('neu')
  })

  it('MC without key lists ticked texts; drawing gives one image; skipped separate', async () => {
    const opt = (text: string) => ({ region: 0, bbox: { x0: 0, y0: 0, x1: 1, y1: 1 }, text })
    const mc = sub('m', '', 1, { mc_options: [opt('eins'), opt('zwei')] })
    const mcKeyed = sub('k', '', 1, { mc_options: [opt('x')] })
    const nopts = sub('n', '', null)
    const t2 = task('t1', '1', [q, mc, mcKeyed, nopts])
    const a = attempt({
      includedTaskIds: ['t1'],
      answers: { q1: ans({ strokes: [stroke] }), m: ans({ ticks: [1] }), k: ans({ ticks: [0] }), n: ans({ text: 'x' }) },
    })
    const { jobs, skipped } = planGrading(base({ exam: stored('e', exam([t2])), attempt: a, mcKeys: { k: [0] } }))
    expect(skipped).toEqual({ k: 'auto' })
    const [drawn, mcJob, noPoints] = await Promise.all(jobs.map((j) => j.build()))
    expect(noPoints!.points).toBe(1)
    expect(drawn!.answer.images).toHaveLength(1)
    expect(drawn!.answer.images[0]).toBe('PNG')
    expect(mcJob!.answer.text).toBe('zwei')
  })
})

describe('what the model gets', () => {
  const vis = (image: string, visual: boolean | undefined) => ({ ...region(image), visual })
  const plan = (q: ReturnType<typeof sub>, answer = ans({ text: 'Antwort' }), extra = {}) =>
    planGrading({
      exam: stored('e', exam([task('t1', '1', [q], extra && 'context' in extra ? (extra as { context: never }).context : [])])),
      attempt: attempt({ includedTaskIds: ['t1'], answers: { [q.id]: answer } }),
      solutionExam: null, mcKeys: {}, library: [], provider: 'google', model: 'm',
    }).jobs[0]!.build()

  it('sends plain-text regions as text only', async () => {
    const r = await plan(sub('q1', 'a', 2, { text: 'Erklären Sie X.', regions: [vis('q.png', false)] }))
    expect(r.question.images).toEqual([])
    expect(r.question.text).toContain('Erklären Sie X.')
  })

  it('sends crops of visual regions and of exams processed before the flag', async () => {
    const r = await plan(sub('q1', 'a', 2, { regions: [vis('a.png', true), vis('b.png', false), vis('c.png', undefined)] }))
    expect(r.question.images).toHaveLength(2)
    expect(getImage).not.toHaveBeenCalledWith('e', 'blank', 'b.png')
  })

  it('skips the question crops when the drawn answer already shows them', async () => {
    const ctx = [{ id: 'c1', applies_from: null, text: 'Gegeben ist die Tabelle', regions: [vis('ctx.png', true)] }]
    const q = sub('q1', 'a', 2, { regions: [vis('q.png', true)] })
    const r = await plan(q, ans({ strokes: [stroke] }), { context: ctx })
    expect(r.answer.images).toHaveLength(1)
    expect(r.question.images).toHaveLength(1) // only the context table
  })

  it('grades subtasks without a point value on a 1-point scale', async () => {
    const r = await plan(sub('q1', 'a', null, { text: 'Frage', regions: [vis('q.png', false)] }))
    expect(r.points).toBe(1)
  })
})

describe('sheetLayout', () => {
  // the answer image must match the sheet the strokes were drawn on: crops scaled to one width, plus the 3:1 box below
  it('scales crops to the widest and adds the text box below', () => {
    const l = sheetLayout([{ width: 1000, height: 300 }, { width: 500, height: 100 }], true)
    expect(l.width).toBe(1000)
    expect(l.rects).toEqual([{ y: 0, height: 300 }, { y: 300, height: 200 }])
    expect(l.height).toBeCloseTo(500 + 1000 / 3)
  })

  it('has no extra space when the answer box is printed on the crop', () => {
    expect(sheetLayout([{ width: 800, height: 400 }], false).height).toBe(400)
  })
})

describe('image cap', () => {
  const regions = (n: number) => Array.from({ length: n }, (_, i) => region(`i${i}.png`))
  const refEx = (id: string) =>
    stored(id, exam([task('tr' + id, '1', [sub('r' + id, '', 2, { text: 'Frage', regions: regions(4) })])]), { hasInk: true })
  const plan = (n: number) =>
    planGrading({
      exam: stored('e', exam([task('t1', '1', [sub('q1', 'a', 3, { text: 'Frage', regions: regions(n) })])])),
      attempt: attempt({ includedTaskIds: ['t1'], answers: { q1: ans({ text: 'A' }) } }),
      solutionExam: null, mcKeys: {}, library: [refEx('a'), refEx('b')], provider: 'google', model: 'm',
    }).jobs[0]!.build()

  it('drops references until it fits', async () => {
    // ink references send only their solution crops (4 each): 12 question + 2 x 4 = 20 fits;
    // 14 question + 8 > 20 keeps one ref (18 total)
    expect((await plan(12)).references).toHaveLength(2)
    const r = await plan(14)
    expect(r.references).toHaveLength(1)
  })
  it('rejects when it cannot fit', async () => {
    await expect(plan(21)).rejects.toMatchObject({ code: 'too_many_images' })
    expect(gradeErrorMessage('too_many_images')).toBe('This subtask has too many images to send.')
  })
})

describe('sseEvents', () => {
  it('keeps the partial rest', () => {
    const a = sseEvents('data: {"a":1}\n\ndata: {"b"')
    expect(a).toEqual({ events: [{ a: 1 }], rest: 'data: {"b"' })
    expect(sseEvents(a.rest + ':2}\n\n').events).toEqual([{ b: 2 }])
  })
})

describe('streamGrade', () => {
  const body = {} as GradeRequest
  const stream = (chunks: string[], status = 200) => {
    const enc = new TextEncoder()
    return new Response(
      new ReadableStream({
        start(c) {
          chunks.forEach((x) => c.enqueue(enc.encode(x)))
          c.close()
        },
      }),
      { status },
    )
  }
  const ev = (o: object) => `data: ${JSON.stringify(o)}\n\n`
  const grade = { points: 2, points_min: 1, points_max: 3, certain: false, basis: 'solution', provider: 'google', model: 'm', rubric: [], feedback: 'f' }

  it('streams thinking, maps done, trims key', async () => {
    const f = vi.fn(async () => stream([ev({ type: 'thinking', text: 'hm' }).slice(0, 10), ev({ type: 'thinking', text: 'hm' }).slice(10) + ev({ type: 'done', grade })]))
    vi.stubGlobal('fetch', f)
    const th: string[] = []
    const g = await streamGrade(body, ' k\n', new AbortController().signal, (t) => th.push(t))
    expect(th).toEqual(['hm'])
    expect(g).toMatchObject({ points: 2, min: 1, max: 3, feedback: 'f' })
    expect((f.mock.calls[0] as unknown as [string, RequestInit])[1].headers).toMatchObject({ 'X-LLM-Key': 'k' })
  })

  it('rejects with GradeError codes', async () => {
    vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ detail: { code: 'no_key' } }), { status: 400 }))
    await expect(streamGrade(body, 'k', new AbortController().signal, () => {})).rejects.toMatchObject({ code: 'no_key' })
    vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ detail: { code: 'rate_limited' } }), { status: 429 }))
    await expect(streamGrade(body, 'k', new AbortController().signal, () => {})).rejects.toBeInstanceOf(GradeError)
    for (const code of ['bad_key', 'no_credits']) {
      vi.stubGlobal('fetch', async () => stream([ev({ type: 'error', code })]))
      await expect(streamGrade(body, 'k', new AbortController().signal, () => {})).rejects.toMatchObject({ code })
    }
  })

  it('resolves a final done without a trailing blank line, ignoring pings', async () => {
    vi.stubGlobal('fetch', async () => stream([': ping\n\n', `data:${JSON.stringify({ type: 'done', grade })}`]))
    const g = await streamGrade(body, 'k', new AbortController().signal, () => {})
    expect(g.min).toBe(1)
  })

  it('rejects malformed JSON with llm_failed; 413 is too_many_images', async () => {
    vi.stubGlobal('fetch', async () => stream(['data: {oops\n\n']))
    await expect(streamGrade(body, 'k', new AbortController().signal, () => {})).rejects.toMatchObject({ code: 'llm_failed' })
    vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ detail: { code: 'sign_in' } }), { status: 401 }))
    const err = await streamGrade(body, 'k', new AbortController().signal, () => {}).catch((e) => e)
    expect(err).toBeInstanceOf(GradeError)
    expect(err.code).toBe('sign_in')
    expect(gradeErrorMessage(err.code)).toBe('Sign in to grade answers.')
    vi.stubGlobal('fetch', async () => new Response('{}', { status: 413 }))
    await expect(streamGrade(body, 'k', new AbortController().signal, () => {})).rejects.toMatchObject({ code: 'too_many_images' })
  })

  it('aborts', async () => {
    const ctl = new AbortController()
    ctl.abort()
    vi.stubGlobal('fetch', async (_u: string, init: RequestInit) => {
      init.signal?.throwIfAborted()
      return stream([])
    })
    await expect(streamGrade(body, 'k', ctl.signal, () => {})).rejects.toMatchObject({ name: 'AbortError' })
  })
})

describe('messages and jsonl', () => {
  it('maps codes', () => {
    expect(gradeErrorMessage('bad_key')).toBe('Your API key was rejected.')
    expect(gradeErrorMessage('no_credits')).toBe('Your OpenRouter account has no credits left.')
    expect(gradeErrorMessage('rate_limited')).toBe(
      'The provider is rate-limiting this model. Wait a minute, or pick another model in settings.',
    )
    expect(gradeErrorMessage('overloaded')).toBe(
      'The model is overloaded right now. Try again later, or pick another model or provider in settings.',
    )
    expect(gradeErrorMessage('timeout')).toBe(
      'No answer from the model for 2 minutes, it is probably overloaded. Try again, or pick another model in settings.',
    )
    expect(gradeErrorMessage('refused')).toBe('The model declined to grade this subtask.')
    expect(gradeErrorMessage('no_key')).toBe('Add an API key in settings.')
    expect(gradeErrorMessage('zzz')).toBe("The LLM couldn't grade this. Try Re-grade, or pick another model in settings.")
  })
  it('writes one line per case', () => {
    const out = evalCasesJsonl([{ id: 'a', expected: 1, request: {} as GradeRequest }, { id: 'b', expected: 2, request: {} as GradeRequest }])
    expect(out.trim().split('\n').map((l) => JSON.parse(l).id)).toEqual(['a', 'b'])
  })
})
