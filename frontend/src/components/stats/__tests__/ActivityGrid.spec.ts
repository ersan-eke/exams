import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { attemptRows } from '@/lib/stats'
import { attempt, exam } from '@/lib/__tests__/fixtures'
import ActivityGrid from '../ActivityGrid.vue'

describe('ActivityGrid', () => {
  it('ends today, starts on a Sunday and lists the day\'s exams on hover', () => {
    const now = new Date(2026, 9, 22, 12).getTime() // a Thursday
    const e = { id: 'e', title: 'GRNVS 2019', structure: exam([]), createdAt: 0, hasInk: false }
    const at = (id: string, d: number) =>
      attempt({ id, examId: 'e', status: 'handed_in', startedAt: new Date(2026, 9, d, 10).getTime(), handedInAt: 1 })
    const rows = attemptRows([e], [at('1', 20), at('2', 20), at('3', 22)])
    const days = mount(ActivityGrid, { props: { rows, now } }).findAll('.day')
    expect(days).toHaveLength(52 * 7 + 5)
    expect(new Date(days[0]!.attributes('data-day')! + 'T00:00').getDay()).toBe(0)
    expect(days[days.length - 1]!.attributes('data-day')).toBe('2026-10-22')
    const tue = days.find((d) => d.attributes('data-day') === '2026-10-20')!
    expect(tue.classes()).toContain('l2')
    expect(tue.attributes('title')).toContain('GRNVS 2019 · not graded')
  })
})
