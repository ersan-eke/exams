import { describe, expect, it } from 'vitest'
import { attempt, exam, sub, task } from './fixtures'
import { examSolutionId, matchSolution, mcKeys } from '../solution'

describe('matchSolution', () => {
  it('matches by identical subtask id', () => {
    const e = exam([task('A1', '1', [sub('A1a', 'a)', 2), sub('A1b', 'b)', 2)])])
    const s = exam([
      task('A1', '1', [
        sub('A1b', 'b)', 2, { text: 'sol b' }),
        sub('A1a', 'a)', 2, { text: 'sol a' }),
      ]),
    ])
    const m = matchSolution(e, s)
    expect(m.A1a?.text).toBe('sol a')
    expect(m.A1b?.text).toBe('sol b')
  })

  it('falls back to same task number and label', () => {
    const e = exam([task('A1', '1', [sub('A1a', 'a)', 2)]), task('A2', '2', [sub('A2a', 'a)', 2)])])
    const s = exam([
      task('T1', '1', [sub('x1', 'a)', 2, { text: 'one' })]),
      task('T2', '2', [sub('x2', 'a)', 2, { text: 'two' })]),
    ])
    const m = matchSolution(e, s)
    expect(m.A1a?.text).toBe('one')
    expect(m.A2a?.text).toBe('two')
  })

  it('leaves unmatched subtasks out', () => {
    const e = exam([task('A1', '1', [sub('A1a', 'a)', 2), sub('A1c', 'c)', 2)])])
    const s = exam([task('T1', '1', [sub('x', 'a)', 2)]), task('T3', '3', [sub('y', 'c)', 2)])])
    const m = matchSolution(e, s)
    expect(m.A1a?.id).toBe('x')
    expect(m.A1c).toBeUndefined()
  })
})

describe('mcKeys', () => {
  it("uses the exam's own key, else the matched solution key", () => {
    const e = exam([
      task('A1', '1', [sub('A1a', 'a)', 1, { mc_key: [1] }), sub('A1b', 'b)', 1), sub('A1c', 'c)', 1)]),
    ])
    const s = exam([
      task('T1', '1', [sub('x', 'a)', 1, { mc_key: [0] }), sub('y', 'b)', 1, { mc_key: [2] })]),
    ])
    expect(mcKeys(e, s)).toEqual({ A1a: [1], A1b: [2] })
    expect(mcKeys(e, null)).toEqual({ A1a: [1] })
  })
})

describe('examSolutionId', () => {
  it('is the newest solution linked to any attempt of the exam', () => {
    const as = [
      attempt({ id: '1', startedAt: 1, solutionExamId: 'old' }),
      attempt({ id: '2', startedAt: 3, solutionExamId: null }),
      attempt({ id: '3', startedAt: 2, solutionExamId: 'new' }),
    ]
    expect(examSolutionId(as)).toBe('new')
    expect(examSolutionId([attempt()])).toBeNull()
  })
})
