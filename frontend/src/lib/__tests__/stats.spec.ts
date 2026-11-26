import { describe, expect, it } from 'vitest'
import { attemptRows, bySubject, dayKey, guessSubject, subjectOf, summarize } from '../stats'
import { ans, attempt, exam, sub, task } from './fixtures'
import type { StoredExam } from '@/types/attempt'

const stored = (id: string, title: string, p: Partial<StoredExam> = {}): StoredExam => ({
  id,
  title,
  createdAt: 0,
  hasInk: false,
  structure: exam([
    task('t1', '1', [
      sub('mc', 'a)', 2, { mc_options: [{ region: 0, bbox: { x0: 0, y0: 0, x1: 0, y1: 0 }, text: 'A' }], mc_key: [0] }),
      sub('l1', 'b)', 4),
      sub('l2', 'c)', 4),
      sub('l3', 'd)', 1),
    ]),
  ]),
  ...p,
})

describe('stats', () => {
  it('guesses the subject from the filename and prefers a set one', () => {
    const cases: [string, string][] = [
      ['2024_Retake_GRNVS', 'GRNVS'],
      ['Endterm 2023 GBS', 'GBS'],
      ['GRNVS_2019 retake', 'GRNVS'],
      ['Wiederholungsklausur_2022_Analysis', 'Analysis'],
      ['Klausur_WS23_Lösung', 'Other'],
      ['Analysis 1 Endterm', 'Analysis 1'],
      ['SS2024 Musterlösung GBS', 'GBS'],
      ['GBS 15.07.2023', 'GBS'],
      ['  ', 'Other'],
      ['Klausur_Lo\u0308sung_GBS', 'GBS'], // NFD umlaut, as macOS stores filenames
      ['Eidi_wdh_losung', 'Eidi'],
      ['IN0009_RT_TSK', 'IN0009'],
      ['grnvs_quiz_3', 'grnvs'],
      ['quiz1', 'Other'],
      ['endterm2025_1', 'Other'],
      ['ds_sol', 'ds'],
      ["endterm'", 'Other'],
      ['numprog-lsg2', 'numprog'],
    ]
    for (const [title, subject] of cases) expect(guessSubject(title)).toBe(subject)
    expect(subjectOf(stored('e', 'GBS 2020', { subject: 'Betriebssysteme' }))).toBe('Betriebssysteme')
    expect(bySubject([stored('a', 'X 2020'), stored('b', 'A 2020'), stored('c', 'X 2021')]).map(([s, es]) => [s, es.length])).toEqual([
      ['A', 1],
      ['X', 2],
    ])
  })

  it('keeps handed-in attempts of the given exams, scores only graded ones', () => {
    const exams = [stored('e', 'A'), stored('s', 'S', { solutionFor: 'x' })]
    const base = { includedTaskIds: ['t1'], status: 'handed_in' as const, handedInAt: 61_000 }
    const rows = attemptRows(exams, [
      attempt({ ...base, id: '1', examId: 'e', startedAt: 1000 }),
      attempt({ ...base, id: '2', examId: 'e', startedAt: 2000, gradedAt: 1, grades: { l1: { main: 3 } }, answers: { mc: ans({ ticks: [0] }) } }),
      attempt({ ...base, id: '3', examId: 'e', status: 'running' }),
      attempt({ ...base, id: '4', examId: 'unknown' }),
      attempt({ ...base, id: '5', examId: 's' }),
    ])
    expect(rows.map((r) => r.attempt.id)).toEqual(['2', '1'])
    expect(rows[0]!.score).toEqual({ main: 5, max: 11 })
    expect(rows[0]!.usedMs).toBe(59_000)
    expect(rows[1]!.score).toBeNull()
  })

  it('a practice attempt from Claude has no time and scores only what it graded', () => {
    const [r] = attemptRows([stored('e', 'A')], [
      attempt({ id: 'p', examId: 'e', status: 'handed_in', timeLimitMs: 0, startedAt: 0, handedInAt: 7_000_000,
        gradedAt: 1, includedTaskIds: ['t1'], grades: { l1: { main: 3 } } }),
    ])
    expect(r).toMatchObject({ practice: true, usedMs: 0, score: { main: 3, max: 4 } })
  })

  it('summarizes totals, MC and long questions grouped by points', () => {
    const e = stored('e', 'A')
    const base = { examId: 'e', includedTaskIds: ['t1'], status: 'handed_in' as const, startedAt: 0, handedInAt: 600_000 }
    const rows = attemptRows([e], [
      attempt({
        ...base,
        id: '1',
        gradedAt: 1,
        answers: { mc: ans({ ticks: [0] }), l1: ans({ text: 'x' }) },
        grades: { l1: { main: 3 }, l2: { main: 1 } },
        time: { mc: { main: 1000, over: 0 }, l1: { main: 4000, over: 2000 }, l2: { main: 2000, over: 0 } },
      }),
      attempt({ ...base, id: '2', answers: { mc: ans({ ticks: [1] }) }, time: { mc: { main: 3000, over: 0 } } }),
    ])
    const s = summarize(rows, [e])
    expect(s.exams).toBe(2)
    expect(s.questions).toBe(3)
    expect(s.timeMs).toBe(1_200_000)
    expect(s.points).toEqual({ main: 6, max: 11, graded: 1 })
    // MC counts in both attempts: one right, one wrong
    expect(s.mc).toEqual({ points: null, count: 2, avgTimeMs: 2000, avgScore: 1, avgMax: 2 })
    expect(s.long.map((g) => [g.points, g.count, g.avgTimeMs, g.avgScore])).toEqual([
      [1, 2, 0, 0],
      [4, 4, 2000, 2],
    ])
  })

  it('uses the local calendar day', () => {
    expect(dayKey(new Date(2026, 0, 5, 23, 59).getTime())).toBe('2026-01-05')
  })
})
