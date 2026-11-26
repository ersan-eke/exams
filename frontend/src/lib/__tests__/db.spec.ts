import 'fake-indexeddb/auto'
import { Blob as NodeBlob } from 'node:buffer'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { putExam, getExam, listExams, putImages, getImage, putAttempt, getAttempt, attemptsForExam, runningAttempt, dirtyIds, clearDirty, markAllDirty, onLocalEdit, storeRemoteAttempt, storeRemoteExam } from '../db'
import type { Attempt, StoredExam } from '@/types/attempt'
import type { ExamStructure } from '@/types/exam'

const exam = (id: string, createdAt: number): StoredExam => ({
  id, title: id, createdAt, hasInk: false,
  structure: { source: `${id}.pdf`, tasks: [] } as unknown as ExamStructure,
})
const attempt = (id: string, examId: string, status: Attempt['status']): Attempt =>
  ({ id, examId, status, startedAt: 1 }) as unknown as Attempt

describe('db', () => {
  it('round-trips an exam and lists newest first', async () => {
    await putExam(exam('a', 1))
    await putExam(exam('b', 3))
    await putExam(exam('c', 2))
    expect((await getExam('a'))?.title).toBe('a')
    expect(await getExam('zzz')).toBeUndefined()
    expect((await listExams()).map((e) => e.id)).toEqual(['b', 'c', 'a'])
  })

  it('round-trips images preserving size', async () => {
    await putImages('x', 'blank', { 'p1.png': // jsdom's Blob does not survive node's structuredClone (used by fake-indexeddb); real browsers do.
      new NodeBlob([new Uint8Array([1, 2, 3, 4])], { type: 'image/png' }) as unknown as Blob })
    const got = await getImage('x', 'blank', 'p1.png')
    expect(got?.size).toBe(4)
    expect(await getImage('x', 'ink', 'p1.png')).toBeUndefined()
  })

  it('round-trips attempts and finds running one', async () => {
    await putAttempt(attempt('t1', 'e1', 'handed_in'))
    await putAttempt(attempt('t2', 'e1', 'running'))
    await putAttempt(attempt('t3', 'e2', 'handed_in'))
    expect((await getAttempt('t1'))?.examId).toBe('e1')
    expect((await attemptsForExam('e1')).map((a) => a.id).sort()).toEqual(['t1', 't2'])
    expect((await runningAttempt())?.id).toBe('t2')
  })
})

describe('edit times and outbox', () => {
  const full = (id: string): Attempt => ({ ...attempt(id, 'e1', 'handed_in'), grades: {}, view: { shown: [], folded: [], expandedTasks: [], outlineCollapsed: false } }) as Attempt
  const listener = vi.fn()
  beforeEach(() => { localStorage.clear(); listener.mockClear(); onLocalEdit(listener) })

  it('stamps editedAt and marks dirty on a real change', async () => {
    const a = full('s1')
    await putAttempt(a)
    clearDirty('attempts', 's1')
    listener.mockClear()
    await putAttempt({ ...a, grades: { A1a: { main: 1 } } })
    expect((await getAttempt('s1'))?.editedAt).toBeGreaterThan(0)
    expect(dirtyIds('attempts')).toContain('s1')
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('running saves mark nothing; the hand-in save stamps and marks dirty', async () => {
    const a = attempt('run1', 'e1', 'running')
    await putAttempt(a)
    await putAttempt({ ...a, time: { A1a: { main: 5, over: 0 } } } as Attempt)
    expect(dirtyIds('attempts')).not.toContain('run1')
    expect(listener).not.toHaveBeenCalled()
    await putAttempt({ ...a, status: 'handed_in', handedInAt: 9 })
    expect(dirtyIds('attempts')).toContain('run1')
    expect((await getAttempt('run1'))!.editedAt).toBeGreaterThan(0)
  })

  it('view-only save marks nothing', async () => {
    const a = full('s2')
    await putAttempt(a)
    clearDirty('attempts', 's2')
    const before = (await getAttempt('s2'))?.editedAt
    listener.mockClear()
    await putAttempt({ ...a, view: { ...a.view, folded: ['x'] } })
    expect(dirtyIds('attempts')).not.toContain('s2')
    expect((await getAttempt('s2'))?.editedAt).toBe(before)
    expect((await getAttempt('s2'))?.view.folded).toEqual(['x'])
    expect(listener).not.toHaveBeenCalled()
  })

  it('remote writes do not mark dirty and keep local view', async () => {
    const a = full('s3')
    await putAttempt({ ...a, view: { ...a.view, folded: ['mine'] } })
    clearDirty('attempts', 's3')
    listener.mockClear()
    const theirs: Attempt = { ...a, editedAt: 5, grades: { B: { main: 2 } }, view: { ...a.view, folded: ['theirs'] } }
    await storeRemoteAttempt(theirs)
    const got = (await getAttempt('s3'))!
    expect(got.editedAt).toBe(5)
    expect(got.view.folded).toEqual(['mine'])
    await storeRemoteAttempt({ ...full('s4'), editedAt: 6 })
    expect((await getAttempt('s4'))?.view).toEqual(a.view)
    await storeRemoteExam({ ...exam('rx', 1), editedAt: 7 })
    expect(dirtyIds('attempts')).toEqual([])
    expect(dirtyIds('exams')).toEqual([])
    expect(listener).not.toHaveBeenCalled()
  })

  it('old records without editedAt read back and markAllDirty marks them', async () => {
    await storeRemoteExam(exam('old-e', 1))
    expect((await getExam('old-e'))?.editedAt).toBeUndefined()
    await markAllDirty()
    expect(dirtyIds('exams')).toContain('old-e')
    expect(dirtyIds('attempts')).toContain('s1')
  })

  it('a broken dirty value reads as empty', () => {
    localStorage.setItem('sync-dirty-exams', '{nope')
    expect(dirtyIds('exams')).toEqual([])
  })
})
