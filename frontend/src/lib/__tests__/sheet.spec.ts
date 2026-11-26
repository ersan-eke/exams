import { describe, expect, it } from 'vitest'
import {
  answerParts,
  includedTasks,
  neighbors,
  orderedShown,
  sheetBlocks,
  subtaskTitle,
} from '../sheet'
import type { Subtask } from '@/types/exam'
import { attempt, exam, sub, task } from './fixtures'

const ctx = (id: string, applies_from: string | null) => ({
  id,
  applies_from,
  regions: [],
  text: '',
})
const t1 = task(
  'A1',
  '1',
  [sub('A1a', 'a)', 1), sub('A1b', 'b)', 1), sub('A1c', 'c)', 1)],
  [ctx('c0', null), ctx('c1', 'A1b'), ctx('c2', 'A1c')],
)
const t2 = task('A2', '2', [sub('A2a', '', 1), sub('A2b', 'b)', 1)])
const t3 = task('A3', '3', [sub('A3a', 'a)', 1)])
const ex = exam([t1, t2, t3])

describe('sheet', () => {
  it('includedTasks', () => {
    expect(includedTasks(ex, attempt({ includedTaskIds: ['A3', 'A1'] }))).toEqual([t1, t3])
  })
  it('orderedShown', () => {
    expect(orderedShown(ex, ['A2b', 'A1c', 'A1a'])).toEqual(['A1a', 'A1c', 'A2b'])
  })
  it('sheetBlocks: contexts interleaved in document order', () => {
    const ids = (shown: string[]) =>
      sheetBlocks(t1, shown).map((b) => (b.kind === 'context' ? b.context.id : b.subtask.id))
    expect(ids(['A1a'])).toEqual(['c0', 'A1a'])
    expect(ids(['A1c'])).toEqual(['c0', 'c1', 'c2', 'A1c'])
    expect(ids(['A1b', 'A2a'])).toEqual(['c0', 'c1', 'A1b'])
    expect(ids(['A1a', 'A1c'])).toEqual(['c0', 'A1a', 'c1', 'c2', 'A1c'])
    expect(ids(['A2a'])).toEqual([])
  })
  it('subtaskTitle', () => {
    expect(subtaskTitle(t2, t2.subtasks[1]!)).toBe('Aufgabe 2 · b)')
    expect(subtaskTitle(t2, t2.subtasks[0]!)).toBe('Aufgabe 2')
  })
  it('neighbors over included tasks', () => {
    const a = attempt({ includedTaskIds: ['A1', 'A3'] })
    expect(neighbors(ex, a, 'A1a')).toEqual({ prev: null, next: 'A1b' })
    expect(neighbors(ex, a, 'A1c')).toEqual({ prev: 'A1b', next: 'A3a' })
    expect(neighbors(ex, a, 'A3a')).toEqual({ prev: 'A1c', next: null })
  })
})

describe('answerParts', () => {
  const r = (image: string | null) => ({ page: 0, bbox: { x0: 0, y0: 0, x1: 1, y1: 1 }, image })
  const box = (region: number) => ({ region, bbox: { x0: 0, y0: 0, x1: 1, y1: 1 } })
  const names = (s: Subtask) =>
    answerParts(s).map((p) => [p.crops.map((c) => c.name), p.box?.region ?? null])

  it('no box: one part with all crops', () => {
    expect(names(sub('A1a', 'a)', 1, { regions: [r('a'), r('b')] }))).toEqual([[['a', 'b'], null]])
  })
  it('a box split over two pages: two parts', () => {
    const s = sub('A1a', 'a)', 1, { regions: [r('a'), r('b')], answer_boxes: [box(0), box(1)] })
    expect(names(s)).toEqual([
      [['a'], 0],
      [['b'], 1],
    ])
  })
  it('crops before a box join it, crops after the last box join the last part', () => {
    const s = sub('A1a', 'a)', 1, { regions: [r('q'), r('a'), r('z')], answer_boxes: [box(1)] })
    expect(names(s)).toEqual([[['q', 'a', 'z'], 1]])
  })
})
