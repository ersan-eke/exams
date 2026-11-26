import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { ans, attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import type { LlmGrade, StoredExam } from '@/types/attempt'
import LlmSummary from '../LlmSummary.vue'

const llm = (points: number): LlmGrade => ({
  points, min: points, max: points, certain: true, basis: 'solution',
  provider: 'google', model: 'm', rubric: [], feedback: '',
})
const stored: StoredExam = {
  id: 'e', title: 'X', createdAt: 1, hasInk: false,
  structure: exam([
    task('A1', '1', [sub('A1a', 'a)', 6), sub('A1b', 'b)', 3), sub('A1c', 'c)', 2)]),
    task('A2', '2', [sub('A2a', 'a)', 4)]),
  ]),
}
const mount_ = (a: Partial<Parameters<typeof attempt>[0]>) =>
  mount(LlmSummary, { props: { exam: stored, attempt: attempt({ status: 'handed_in', includedTaskIds: ['A1', 'A2'], ...a }) } })

describe('LlmSummary', () => {
  it('renders nothing before any LLM grade exists', () => {
    expect(mount_({ grades: { A1a: { main: 3 } } }).find('.summary').exists()).toBe(false)
  })

  it('lists chips and totals per task; no LLM grade shows – and adds nothing', () => {
    const w = mount_({ grades: { A1a: { main: 5, llm: { main: llm(4) } }, A1b: { main: 2 }, A1c: { main: 1, llm: { main: llm(2) } } } })
    const line = w.find('[data-task="A1"]')
    expect(line.findAll('.chip').map((c) => c.text())).toEqual(['a) 4/6', 'b) –', 'c) 2/2'])
    expect(line.text()).toContain('you: 8 P')
    expect(line.text()).toContain('LLM: 6 P')
  })

  it('shows a verdict for subtasks without a point value and leaves them out of the LLM total', () => {
    const noPoints: StoredExam = { ...stored, structure: exam([task('A1', '1', [sub('A1a', 'a)', 2), sub('A1b', 'b)', null)])]) }
    const w = mount(LlmSummary, {
      props: {
        exam: noPoints,
        attempt: attempt({ status: 'handed_in', includedTaskIds: ['A1'], grades: { A1a: { llm: { main: llm(2) } }, A1b: { llm: { main: llm(1) } } } }),
      },
    })
    const line = w.find('[data-task="A1"]')
    expect(line.findAll('.chip').map((c) => c.text())).toEqual(['a) 2/2', 'b) ✓'])
    expect(line.text()).toContain('LLM: 2 P')
  })

  it('counts the overtime version when the answer changed in overtime', () => {
    const w = mount_({
      snapshot: { A1a: ans({ text: 'early' }) },
      answers: { A1a: ans({ text: 'late' }) },
      grades: { A1a: { main: 1, over: 5, llm: { main: llm(2), over: llm(4) } } },
    })
    const line = w.find('[data-task="A1"]')
    expect(line.text()).toContain('LLM: 4 P')
    expect(line.text()).toContain('you: 5 P')
  })

  it('a chip click emits jump with the subtask id', async () => {
    const w = mount_({ grades: { A1a: { llm: { main: llm(4) } } } })
    await w.find('[data-task="A1"] .chip').trigger('click')
    expect(w.emitted('jump')).toEqual([['A1a']])
  })
})
