import { describe, expect, it } from 'vitest'
import { changedInOvertime, formatPoints, maxPoints, mcPoints, scores, withPointOverrides } from '../scoring'
import { ans, attempt, exam, sub, task } from './fixtures'

const pt = { kind: 'per_tick', right: 1, wrong: -1, floor: 0 } as const

describe('mcPoints', () => {
  it('per_tick', () => {
    expect(mcPoints(pt, [0, 2], [0, 1], 2)).toBe(0)
    expect(mcPoints(pt, [0, 1], [0, 1], 2)).toBe(2)
    expect(mcPoints(pt, [0, 1, 3], [0, 1], 2)).toBe(1)
    expect(mcPoints(pt, [0, 1], [0, 1], 1)).toBe(1)
  })
  it('per_tick: a single-answer question worth more than one tick is all or nothing', () => {
    const half = { kind: 'per_tick', right: 0.5, wrong: -0.5, floor: 0 } as const
    expect(mcPoints(half, [1], [1], 1)).toBe(1)
    expect(mcPoints(half, [0, 1], [1], 1)).toBe(0)
    expect(mcPoints(half, [0], [1], 1)).toBe(0)
    expect(mcPoints(half, [0, 1], [0, 1], 1)).toBe(1) // two correct boxes: per tick as before
  })
  it('all_or_nothing', () => {
    const r = { kind: 'all_or_nothing' } as const
    expect(mcPoints(r, [1, 0], [0, 1], 1)).toBe(1)
    expect(mcPoints(r, [0], [0, 1], 1)).toBe(0)
  })
})

describe('scores', () => {
  const ex = exam([
    task('A1', '1', [sub('A1a', 'a)', 2), sub('A1b', 'b)', null), sub('A1c', 'c)', 3, { mc_key: [0] })]),
    task('A2', '2', [sub('A2a', 'a)', 5)]),
  ])
  it('a practice attempt from Claude (timeLimitMs 0) counts only the subtasks it graded', () => {
    const a = attempt({ timeLimitMs: 0, includedTaskIds: ['A1'], grades: { A1a: { main: 1 } } })
    expect(scores(a, ex)).toEqual({ main: 1, over: null, maxKnown: 2 })
  })
  it('over is null without snapshot', () => {

    const a = attempt({ includedTaskIds: ['A1'], grades: { A1a: { main: 2 } } })
    expect(scores(a, ex)).toEqual({ main: 2, over: null, maxKnown: 5 })
  })
  it('overtime grades, unchanged, null points, excluded tasks', () => {
    const a = attempt({
      includedTaskIds: ['A1'],
      grades: { A1a: { main: 2, over: 3 }, A1b: { main: 1 }, A2a: { main: 5 } },
      answers: { A1a: ans({ text: 'new' }), A1b: ans({ text: 'same' }) },
      snapshot: { A1a: ans({ text: 'old' }), A1b: ans({ text: 'same' }) },
    })
    expect(scores(a, ex)).toEqual({ main: 3, over: 4, maxKnown: 5 })
  })
  it('auto MC fallback on snapshot, over on final answers', () => {
    const a = attempt({
      includedTaskIds: ['A1'],
      answers: { A1c: ans({ ticks: [1] }) },
      snapshot: { A1c: ans({ ticks: [0] }) },
    })
    expect(scores(a, ex)).toEqual({ main: 3, over: 0, maxKnown: 5 })
  })
  it('uses the given keys for subtasks without their own key', () => {
    const a = attempt({ includedTaskIds: ['A2'], answers: { A2a: ans({ ticks: [1] }) } })
    expect(scores(a, ex, { A2a: [1] })).toEqual({ main: 5, over: null, maxKnown: 5 })
  })
  it('changedInOvertime', () => {
    expect(changedInOvertime(attempt(), 'x')).toBe(false)
    expect(changedInOvertime(attempt({ snapshot: {}, answers: { x: ans({ text: 'a' }) } }), 'x')).toBe(true)
  })
})

describe('task mc_rule', () => {
  const mc = (id: string, key: number[]) => sub(id, 'x)', 1, { mc_key: key, mc_options: [opt, opt, opt] })
  const opt = { region: 0, bbox: { x0: 0, y0: 0, x1: 0, y1: 0 }, text: '' }
  it("a task's own rule wins over the attempt's", () => {
    const t = { ...task('A1', '1', [mc('A1a', [0, 1])]), mc_rule: pt }
    const a = attempt({ includedTaskIds: ['A1'], answers: { A1a: ans({ ticks: [0, 1, 2] }) } })
    // all-or-nothing (attempt) would give 0; per tick (task) gives 2 right - 1 wrong, capped at max 1
    expect(scores(a, exam([t])).main).toBe(1)
  })
  it('no even split of the task total under a per-tick rule', () => {
    const open = (id: string) => sub(id, 'x)', null, { mc_options: [opt, opt] })
    const t = { ...task('A1', '1', [open('A1a'), open('A1b')]), points: 4 }
    expect(maxPoints(t, t.subtasks[0]!)).toBe(2)
    expect(maxPoints(t, t.subtasks[0]!, pt)).toBeNull()
    expect(maxPoints({ ...t, mc_rule: pt }, t.subtasks[0]!, { kind: 'all_or_nothing' })).toBeNull()
  })
  it('per-tick max from the key (e.g. an attached solution): correct boxes x right', () => {
    const open = (id: string) => sub(id, 'x)', null, { mc_options: [opt, opt, opt] })
    const t = { ...task('A1', '1', [open('A1a')]), points: 4 }
    const half = { kind: 'per_tick', right: 0.5, wrong: -0.5, floor: 0 } as const
    expect(maxPoints(t, t.subtasks[0]!, half, [0, 2])).toBe(1)
    expect(maxPoints(t, t.subtasks[0]!, half, [])).toBeNull()
  })
})

describe('single-answer points and uneven splits', () => {
  const opt = { region: 0, bbox: { x0: 0, y0: 0, x1: 0, y1: 0 }, text: '' }
  const grnvs = { kind: 'per_tick', right: 0.5, wrong: -0.5, floor: 0, single: 1 } as const
  const open = (id: string, n = 3) => sub(id, 'x)', null, { mc_options: Array(n).fill(opt) })
  it('per tick with a solution-only key: single answer is worth its stated points', () => {
    const t = { ...task('A1', '1', [open('A1a')]), points: 3 }
    const s = t.subtasks[0]!
    expect(maxPoints(t, s, grnvs, [1])).toBe(1)
    expect(maxPoints(t, s, grnvs, [0, 2])).toBe(1) // 2 x 0.5
    expect(maxPoints(t, s, grnvs, [0, 1, 2])).toBe(1.5)
    expect(mcPoints(grnvs, [1], [1], maxPoints(t, s, grnvs, [1])!)).toBe(1) // all or nothing
    expect(mcPoints(grnvs, [1, 2], [1], 1)).toBe(0)
  })
  it('even split only when the share is a multiple of 0.5', () => {
    const t = (n: number, points: number) => ({
      ...task('A1', '1', Array.from({ length: n }, (_, i) => open(`A1${i}`))),
      points,
    })
    expect(maxPoints(t(4, 8), t(4, 8).subtasks[0]!)).toBe(2)
    expect(maxPoints(t(4, 6), t(4, 6).subtasks[0]!)).toBe(1.5)
    expect(maxPoints(t(9, 12), t(9, 12).subtasks[0]!)).toBeNull()
  })
})

describe('formatPoints', () => {
  it('shows up to one decimal', () => {
    expect(formatPoints(62)).toBe('62')
    expect(formatPoints(61.5)).toBe('61.5')
    expect(formatPoints(1 / 3)).toBe('0.3')
  })
})

describe('withPointOverrides', () => {
  const stored = {
    id: 'e',
    title: 'X',
    createdAt: 1,
    hasInk: false,
    structure: exam([task('A1', '1', [sub('a', 'a)', 2), sub('b', 'b)', null)])]),
    pointOverrides: { a: 5, b: 1.5 },
  }
  it('replaces only overridden subtasks and does not mutate the input', () => {
    const out = withPointOverrides({ ...stored, pointOverrides: { b: 1.5 } })
    expect(out.structure.tasks[0]!.subtasks.map((s) => s.points)).toEqual([2, 1.5])
    const all = withPointOverrides(stored)
    expect(all.structure.tasks[0]!.subtasks.map((s) => s.points)).toEqual([5, 1.5])
    expect(stored.structure.tasks[0]!.subtasks.map((s) => s.points)).toEqual([2, null])
  })
})
