import 'fake-indexeddb/auto'
import { Blob as NodeBlob } from 'node:buffer'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { dirtyIds, getAttempt, getExam, getImage, markDirty, putAttempt, putExam, putImages, storeRemoteAttempt, storeRemoteExam } from '../db'
vi.mock('../db', async (importOriginal) => {
  const m = await importOriginal<typeof import('../db')>()
  return { ...m, storeRemoteExam: vi.fn(m.storeRemoteExam) } // pass-through, so a test can edit right after a pull's store
})
import { lastPulled, pulled, sync, toWire } from '../sync'
import { attempt, exam as structure } from './fixtures'
import type { Attempt, StoredExam } from '@/types/attempt'

const exam = (id: string, p: Partial<StoredExam> = {}): StoredExam => ({
  id, title: id, createdAt: 1, hasInk: false, structure: structure([]), ...p,
})
const blob = (bytes: number[]) => new NodeBlob([new Uint8Array(bytes)], { type: 'image/png' }) as unknown as Blob

type Reply = number | { status: number; body?: unknown } | (() => Promise<Response> | Response)
interface Call { method: string; url: string; body: Record<string, unknown> | null }

/** routes `METHOD url` to a reply; a list of replies is used in order, the last one repeats */
function route(routes: Record<string, Reply | Reply[]>) {
  const calls: Call[] = []
  const used: Record<string, number> = {}
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    calls.push({ method, url, body: init?.body ? JSON.parse(init.body as string) : null })
    const key = `${method} ${url}`
    const r = routes[key] ?? routes[`${method} ${url.split('?')[0]}`]
    if (r === undefined) return new Response(null, { status: 404 })
    const list = Array.isArray(r) ? r : [r]
    const reply = list[Math.min((used[key] = (used[key] ?? -1) + 1), list.length - 1)]!
    if (typeof reply === 'function') return reply()
    const { status, body } = typeof reply === 'number' ? { status: reply, body: undefined } : reply
    return new Response(body === undefined ? null : JSON.stringify(body), { status })
  }))
  return calls
}
const empty = { status: 200, body: { cursor: 'c1', exams: [], attempts: [] } }
const puts = (calls: Call[]) => calls.filter((c) => c.method === 'PUT').map((c) => c.url)

describe('sync', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('Blob', NodeBlob) // jsdom's Blob does not survive fake-indexeddb's structuredClone
  })
  afterEach(() => vi.unstubAllGlobals())

  it('pushes exams before attempts', async () => {
    await putAttempt(attempt({ id: 'o-a', examId: 'o-e', status: 'handed_in' }))
    await putExam(exam('o-e'))
    const calls = route({ 'PUT /api/exams/o-e': 204, 'PUT /api/attempts/o-a': 204, 'GET /api/sync': empty })
    await sync()
    expect(puts(calls)).toEqual(['/api/exams/o-e', '/api/attempts/o-a'])
    expect(dirtyIds('exams')).toEqual([])
    expect(dirtyIds('attempts')).toEqual([])
  })

  it('retries an exam once with content on need_content', async () => {
    await putExam(exam('c-e', { hasInk: true }))
    await putImages('c-e', 'blank', { 'p1.png': blob([1, 2]) })
    await putImages('c-e', 'ink', { 'p1.png': blob([3]) })
    const calls = route({
      'PUT /api/exams/c-e': [{ status: 409, body: { detail: { code: 'need_content' } } }, 204],
      'GET /api/sync': empty,
    })
    await sync()
    const [first, second] = calls.filter((c) => c.method === 'PUT')
    expect(first!.body!.structure).toBeUndefined()
    expect(second!.body!.structure).toEqual(structure([]))
    expect(second!.body!.images).toEqual({ 'p1.png': btoa('\x01\x02') })
    expect(second!.body!.solutionImages).toEqual({ 'p1.png': btoa('\x03') })
    expect(dirtyIds('exams')).toEqual([])
  })

  it('on need_exam pushes the exam (and the solution exam) then retries the attempt once', async () => {
    await putExam(exam('n-e'))
    await putExam(exam('n-s'))
    localStorage.clear()
    await putAttempt(attempt({ id: 'n-a', examId: 'n-e', solutionExamId: 'n-s', status: 'handed_in' }))
    const calls = route({
      'PUT /api/attempts/n-a': [{ status: 409, body: { detail: { code: 'need_exam' } } }, 204],
      'PUT /api/exams/n-e': 204,
      'PUT /api/exams/n-s': 204,
      'GET /api/sync': empty,
    })
    await sync()
    expect(puts(calls)).toEqual(['/api/attempts/n-a', '/api/exams/n-e', '/api/exams/n-s', '/api/attempts/n-a'])
    expect(dirtyIds('attempts')).toEqual([])
  })

  it('running attempts stay dirty and are not sent', async () => {
    await putAttempt(attempt({ id: 'r-a', status: 'running' }))
    markDirty('attempts', 'r-a') // e.g. markAllDirty on first sign-in
    const calls = route({ 'GET /api/sync': empty })
    await sync()
    expect(puts(calls)).toEqual([])
    expect(dirtyIds('attempts')).toEqual(['r-a'])
  })

  it('422 and 413 drop the record from the outbox, network errors keep it', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    await putExam(exam('d-1'))
    await putExam(exam('d-2'))
    route({ 'PUT /api/exams/d-1': 422, 'PUT /api/exams/d-2': 413, 'GET /api/sync': empty })
    await sync()
    expect(dirtyIds('exams')).toEqual([])
    expect(warn).toHaveBeenCalledTimes(2)
    warn.mockRestore()

    await putExam(exam('d-3'))
    route({ 'PUT /api/exams/d-3': () => Promise.reject(new TypeError('offline')) })
    await sync()
    expect(dirtyIds('exams')).toEqual(['d-3'])

    route({ 'PUT /api/exams/d-3': 503 })
    await sync()
    expect(dirtyIds('exams')).toEqual(['d-3'])

    // a 404 keeps it dirty but the run goes on to the pull
    const warn404 = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const calls = route({ 'PUT /api/exams/d-3': 404, 'GET /api/sync': empty })
    await sync()
    expect(dirtyIds('exams')).toEqual(['d-3'])
    expect(calls.some((c) => c.url.startsWith('/api/sync'))).toBe(true)
    warn404.mockRestore()
  })

  it('an attempt whose exam the server rejects is dropped too, the exam uploaded once per run', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    await putExam(exam('l-e'))
    await putAttempt(attempt({ id: 'l-a', examId: 'l-e', status: 'handed_in' }))
    const calls = route({
      'PUT /api/exams/l-e': [{ status: 409, body: { detail: { code: 'need_content' } } }, 413],
      'PUT /api/attempts/l-a': { status: 409, body: { detail: { code: 'need_exam' } } },
      'GET /api/sync': empty,
    })
    await sync()
    expect(puts(calls)).toEqual(['/api/exams/l-e', '/api/exams/l-e', '/api/attempts/l-a'])
    expect(dirtyIds('exams')).toEqual([])
    expect(dirtyIds('attempts')).toEqual([])
    // next time, with the exam already out of the outbox: one more upload try, then the attempt is gone
    markDirty('attempts', 'l-a')
    const again = route({
      'PUT /api/exams/l-e': [{ status: 409, body: { detail: { code: 'need_content' } } }, 413],
      'PUT /api/attempts/l-a': { status: 409, body: { detail: { code: 'need_exam' } } },
      'GET /api/sync': empty,
    })
    await sync()
    expect(puts(again)).toEqual(['/api/attempts/l-a', '/api/exams/l-e', '/api/exams/l-e'])
    expect(dirtyIds('attempts')).toEqual([])
    warn.mockRestore()
  })

  it('pull writes newer remote records, keeps newer local ones, clears dirty for replaced ones', async () => {
    await storeRemoteExam({ ...exam('p-new', { title: 'old' }), editedAt: 10 })
    await storeRemoteExam({ ...exam('p-old', { title: 'mine' }), editedAt: 50 })
    // running here, so the push skips it and leaves it dirty; the other device handed it in
    await storeRemoteAttempt({ ...attempt({ id: 'p-a', examId: 'p-new', status: 'running' }), editedAt: 10 })
    markDirty('attempts', 'p-a')
    const meta = (id: string, title: string, editedAt: number) => ({
      id, title, hasInk: false, hidden: false, subject: 'Math', pointOverrides: null, rubrics: null,
      solutionFor: null, fingerprint: null, createdAt: 1, editedAt,
    })
    const remoteAttempt = toWire({ ...attempt({ id: 'p-a', examId: 'p-new', status: 'handed_in' }), editedAt: 20 })
    route({
      'GET /api/sync': { status: 200, body: { cursor: 'c', exams: [meta('p-new', 'theirs', 20), meta('p-old', 'theirs', 40)], attempts: [remoteAttempt] } },
    })
    const before = pulled.value
    await sync()
    const pNew = (await getExam('p-new'))!
    expect(pNew.title).toBe('theirs')
    expect(pNew.subject).toBe('Math')
    expect(pNew.structure).toEqual(structure([]))
    expect((await getExam('p-old'))!.title).toBe('mine')
    const a = (await getAttempt('p-a'))!
    expect(a.status).toBe('handed_in')
    expect(a.view).toBeDefined()
    expect(dirtyIds('attempts')).toEqual([])
    expect(pulled.value).toBe(before + 1)
    expect(lastPulled).toEqual({ exams: ['p-new'], attempts: ['p-a'] })
  })

  it('pull fetches structure + crops for unknown exams via GET /api/exams/{id}', async () => {
    const s = structure([])
    route({
      'GET /api/sync': { status: 200, body: { cursor: 'c', attempts: [], exams: [{
        id: 'u-e', title: 'U', hasInk: true, hidden: false, subject: null, pointOverrides: null, rubrics: null,
        solutionFor: null, fingerprint: null, createdAt: 5, editedAt: 7,
      }] } },
      'GET /api/exams/u-e': { status: 200, body: { exam: s, images: { 'a.png': btoa('ab') }, solution_images: { 'a.png': btoa('c') } } },
    })
    await sync()
    const e = (await getExam('u-e'))!
    expect(e).toMatchObject({ title: 'U', hasInk: true, createdAt: 5, editedAt: 7, structure: s })
    expect(e.subject).toBeUndefined()
    expect((await getImage('u-e', 'blank', 'a.png'))?.size).toBe(2)
    expect((await getImage('u-e', 'ink', 'a.png'))?.size).toBe(1)
    expect(dirtyIds('exams')).toEqual([])
  })

  it('pull saves the cursor and sends it as since next time', async () => {
    const cursor = '2026-11-02T10:00:00.123+00:00'
    const calls = route({ 'GET /api/sync': { status: 200, body: { cursor, exams: [], attempts: [] } } })
    await sync()
    await sync()
    const gets = calls.filter((c) => c.url.startsWith('/api/sync')).map((c) => c.url)
    expect(gets).toEqual(['/api/sync', `/api/sync?since=${encodeURIComponent(cursor)}`])
    expect(localStorage.getItem('sync-cursor')).toBe(cursor)
  })

  it('pull follows `more` through every page and keeps the first page cursor', async () => {
    await putExam(exam('pg-e'))
    const wire = (id: string) => toWire({ ...attempt({ id, examId: 'pg-e', status: 'handed_in' }), editedAt: 20 })
    const next = `/api/sync?since=${encodeURIComponent('2026-11-02T10:00:00.5+00:00')}&after=a1`
    const calls = route({
      'GET /api/sync': { status: 200, body: { cursor: 'c-first', more: true, after: 'a1', pageSince: '2026-11-02T10:00:00.5+00:00', exams: [], attempts: [wire('pg-a1')] } },
      [`GET ${next}`]: { status: 200, body: { cursor: 'c-second', more: false, after: null, pageSince: null, exams: [], attempts: [wire('pg-a2')] } },
    })
    await sync()
    expect(calls.filter((c) => c.url.startsWith('/api/sync')).map((c) => c.url)).toEqual(['/api/sync', next])
    expect((await getAttempt('pg-a1'))!.status).toBe('handed_in')
    expect((await getAttempt('pg-a2'))!.status).toBe('handed_in')
    expect(localStorage.getItem('sync-cursor')).toBe('c-first')
  })

  it('concurrent sync() calls run one at a time', async () => {
    await putExam(exam('s-e'))
    let inFlight = 0
    let maxInFlight = 0
    const calls = route({
      'PUT /api/exams/s-e': async () => {
        maxInFlight = Math.max(maxInFlight, ++inFlight)
        await new Promise((r) => setTimeout(r, 5))
        inFlight--
        return new Response(null, { status: 204 })
      },
      'GET /api/sync': empty,
    })
    const first = sync()
    while (!inFlight) await new Promise((r) => setTimeout(r, 1)) // wait until the first run is inside its PUT
    await putExam(exam('s-e', { title: 'edited' }))
    const second = sync()
    await Promise.all([first, second])
    expect(maxInFlight).toBe(1)
    expect(puts(calls)).toEqual(['/api/exams/s-e', '/api/exams/s-e'])
    expect(calls.filter((c) => c.url.startsWith('/api/sync'))).toHaveLength(2)
    expect(dirtyIds('exams')).toEqual([])
  })

  it('a pull whose body fails to parse ends the run quietly and keeps the cursor', async () => {
    localStorage.setItem('sync-cursor', 'old')
    route({ 'GET /api/sync': () => new Response('{"cursor": "new", "exa', { status: 200 }) })
    await expect(sync()).resolves.toBeUndefined()
    expect(localStorage.getItem('sync-cursor')).toBe('old')
  })

  it('an exam whose content fetch fails is skipped, the rest is stored, the cursor kept', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    localStorage.setItem('sync-cursor', 'old')
    const meta = (id: string) => ({
      id, title: id, hasInk: false, hidden: false, subject: null, pointOverrides: null, rubrics: null,
      solutionFor: null, fingerprint: null, createdAt: 1, editedAt: 3,
    })
    route({
      'GET /api/sync': { status: 200, body: { cursor: 'new', exams: [meta('f-bad'), meta('f-ok')], attempts: [] } },
      'GET /api/exams/f-bad': 500,
      'GET /api/exams/f-ok': { status: 200, body: { exam: structure([]), images: {}, solution_images: null } },
    })
    await sync()
    expect(await getExam('f-bad')).toBeUndefined()
    expect((await getExam('f-ok'))?.title).toBe('f-ok')
    expect(localStorage.getItem('sync-cursor')).toBe('old')
    expect(warn).toHaveBeenCalledOnce()
    warn.mockRestore()
  })

  it('a pulled record edited locally right after the store stays dirty', async () => {
    const real = (await vi.importActual<typeof import('../db')>('../db')).storeRemoteExam
    vi.mocked(storeRemoteExam).mockImplementationOnce(async (e) => {
      await real(e)
      await putExam({ ...e, title: 'edited right after the pull' })
    })
    markDirty('exams', 'g-e') // dirty, but gone locally, so the push drops it; the pull brings it back
    route({
      'GET /api/sync': { status: 200, body: { cursor: 'c', attempts: [], exams: [
        { id: 'g-e', title: 'theirs', hasInk: false, hidden: false, subject: null, pointOverrides: null, rubrics: null,
          solutionFor: null, fingerprint: null, createdAt: 1, editedAt: 5 },
      ] } },
      'GET /api/exams/g-e': { status: 200, body: { exam: structure([]), images: {}, solution_images: null } },
    })
    await sync()
    expect((await getExam('g-e'))?.title).toBe('edited right after the pull')
    expect(dirtyIds('exams')).toEqual(['g-e'])
  })

  it('missing hidden/subject/editedAt on old records push as defaults', async () => {
    await storeRemoteExam(exam('m-e')) // an old record: no hidden, subject or editedAt
    markDirty('exams', 'm-e')
    const old = attempt({ id: 'm-a', examId: 'm-e', status: 'handed_in' })
    await storeRemoteAttempt(old)
    markDirty('attempts', 'm-a')
    const calls = route({ 'PUT /api/exams/m-e': 204, 'PUT /api/attempts/m-a': 204, 'GET /api/sync': empty })
    await sync()
    const [e, a] = calls.filter((c) => c.method === 'PUT').map((c) => c.body!)
    expect(e).toEqual({
      id: 'm-e', title: 'm-e', hasInk: false, hidden: false, subject: null, pointOverrides: null, rubrics: null,
      solutionFor: null, fingerprint: null, createdAt: 1, editedAt: 0,
    })
    expect(a!.editedAt).toBe(0)
    expect(a!.view).toBeUndefined()
    expect(a!.mcRule).toEqual(old.mcRule)
  })
})
