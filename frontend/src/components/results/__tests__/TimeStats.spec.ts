import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { ans, attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import type { StoredExam } from '@/types/attempt'
import TimeStats from '../TimeStats.vue'

const structure = exam([
  task('A1', '1', [sub('A1a', 'a)', 1), sub('A1b', 'b)', 1)]),
  task('A2', '2', [sub('A2a', 'a)', 1)]),
])
const stored: StoredExam = { id: 'e', title: 'X', structure, createdAt: 1, hasInk: false }
const LIMIT = 90 * 60_000

const mk = (handedAfter: number, extra = {}) =>
  attempt({
    startedAt: 0,
    timeLimitMs: LIMIT,
    handedInAt: handedAfter,
    status: 'handed_in',
    includedTaskIds: ['A1'],
    ...extra,
  })

describe('TimeStats', () => {
  it('a practice attempt from Claude shows what was practiced of the whole exam, no time', () => {
    const a = mk(2 * 60 * 60_000, { timeLimitMs: 0, grades: { A1a: { main: 1 }, A1b: { main: 0 } } })
    const w = mount(TimeStats, { props: { attempt: a, exam: stored } })
    expect(w.text()).toContain('2 / 3')
    expect(w.text()).toContain('practiced in Claude')
    expect(w.text()).not.toContain('overtime')
  })

  it('hides overtime when handed in before the limit', () => {
    const w = mount(TimeStats, { props: { attempt: mk(LIMIT - 5 * 60_000), exam: stored } })
    expect(w.text()).toContain('1:25:00')
    expect(w.text()).toContain('within the limit')
    expect(w.text()).not.toContain('overtime')
  })

  it('shows overtime in the over tone', () => {
    const w = mount(TimeStats, { props: { attempt: mk(LIMIT + 12 * 60_000 + 40_000), exam: stored } })
    expect(w.text()).toContain('1:30:00')
    expect(w.text()).toContain('+12:40')
    expect(w.text()).toContain('overtime')
    expect(w.find('.over').text()).toBe('+12:40')
  })

  it('counts answered subtasks from the snapshot, out of included ones', () => {
    const w = mount(TimeStats, {
      props: {
        attempt: mk(LIMIT + 1000, {
          snapshot: { A1a: ans({ text: 'x' }) },
          answers: { A1a: ans({ text: 'x' }), A1b: ans({ text: 'late' }) },
        }),
        exam: stored,
      },
    })
    expect(w.text()).toContain('1 / 2')
    expect(w.text()).toContain('subtasks answered in time')
  })

  it('falls back to answers without a snapshot', () => {
    const w = mount(TimeStats, {
      props: { attempt: mk(LIMIT - 1000, { answers: { A1a: ans({ done: true }), A1b: ans({ text: 'y' }) } }), exam: stored },
    })
    expect(w.text()).toContain('2 / 2')
  })
})
