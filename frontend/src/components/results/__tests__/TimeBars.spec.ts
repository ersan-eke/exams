import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import type { StoredExam } from '@/types/attempt'
import TimeBars from '../TimeBars.vue'

const structure = exam([
  task('A1', '1', [sub('A1a', 'a)', 1), sub('A1b', 'b)', 1)]),
  task('A2', '2', [sub('A2a', '', 1)]),
  task('A3', '3', [sub('A3a', 'a)', 1)]),
])
const stored: StoredExam = { id: 'e', title: 'X', structure, createdAt: 1, hasInk: false }
const a = attempt({
  includedTaskIds: ['A1', 'A2'],
  time: {
    A1a: { main: 60_000, over: 0 },
    A1b: { main: 120_000, over: 120_000 },
    A2a: { main: 30_000, over: 0 },
    A3a: { main: 999_000, over: 0 },
  },
})

describe('TimeBars', () => {
  it('is collapsed until toggled', async () => {
    const w = mount(TimeBars, { props: { attempt: a, exam: stored } })
    expect(w.findAll('.row')).toHaveLength(0)
    await w.find('button').trigger('click')
    expect(w.findAll('.row')).toHaveLength(3)
  })

  it('sorts descending, labels rows, scales to the max, drops excluded tasks', async () => {
    const w = mount(TimeBars, { props: { attempt: a, exam: stored } })
    await w.find('button').trigger('click')
    const rows = w.findAll('.row')
    expect(rows.map((r) => r.find('.n').text())).toEqual(['1 b)', '1 a)', '2'])
    expect(rows.map((r) => r.find('.t').text())).toEqual(['04:00', '01:00', '00:30'])
    expect(rows[0]!.find('.b').attributes('style')).toContain('width: 100%')
    expect(rows[1]!.find('.b').attributes('style')).toContain('width: 25%')
    expect(w.text()).not.toContain('3 a)')
  })

  it('sorts by task order or ascending, keeping the slowest highlighted', async () => {
    const w = mount(TimeBars, { props: { attempt: a, exam: stored } })
    await w.find('button').trigger('click')
    const labels = () => w.findAll('.row .n').map((n) => n.text())
    const sortBtn = (t: string) => w.findAll('.sort').find((b) => b.text() === t)!

    await sortBtn('exam order').trigger('click')
    expect(labels()).toEqual(['1 a)', '1 b)', '2'])
    await sortBtn('time ↑').trigger('click')
    expect(labels()).toEqual(['2', '1 a)', '1 b)'])
    expect(w.findAll('.row .b').map((b) => b.classes('hot'))).toEqual([false, true, true])
  })

  it('groups subtasks by question, summing their time', async () => {
    const w = mount(TimeBars, { props: { attempt: a, exam: stored } })
    await w.find('button').trigger('click')
    await w
      .findAll('.group')
      .find((b) => b.text() === 'by question')!
      .trigger('click')
    const rows = w.findAll('.row')
    expect(rows.map((r) => r.find('.n').text())).toEqual(['1', '2'])
    expect(rows.map((r) => r.find('.t').text())).toEqual(['05:00', '00:30'])
    await w.find('[aria-label="Column chart"]').trigger('click')
    expect(w.findAll('.col .n').map((n) => n.text())).toEqual(['1', '2'])
  })

  it('switches to a column chart in the same order', async () => {
    const w = mount(TimeBars, { props: { attempt: a, exam: stored } })
    await w.find('button').trigger('click')
    await w.find('[aria-label="Column chart"]').trigger('click')
    expect(w.findAll('.row')).toHaveLength(0)
    const cols = w.findAll('.col')
    expect(cols.map((c) => c.find('.n').text())).toEqual(['1 b)', '1 a)', '2'])
    expect(cols[1]!.find('.c').attributes('style')).toContain('height: 25%')
    expect(w.find('.y').text()).toContain('04:00')
  })
})
