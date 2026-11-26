import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import type { LlmGrade } from '@/types/attempt'
import LlmCard from '../LlmCard.vue'

const grade = (p: Partial<LlmGrade> = {}): LlmGrade => ({
  points: 4,
  min: 4,
  max: 4,
  certain: true,
  basis: 'solution',
  provider: 'google',
  model: 'gemini-2.5-flash',
  rubric: [
    { item: 'names the steps', max: 2, hit: 2, note: '', source: 'solution' },
    { item: 'sequence numbers', max: 2, hit: 1, note: 'only half', source: 'inferred' },
    { item: 'timeouts', max: 2, hit: 0, note: 'No word on retransmission.', source: 'solution' },
  ],
  feedback: 'Solid on the steps.\nMissing losses.',
  ...p,
})
const card = (props: Record<string, unknown>) => mount(LlmCard, { props: { max: 6, ...props } })

describe('LlmCard', () => {
  it('shows a certain grade with basis and short model name', () => {
    const w = card({ grade: grade() })
    expect(w.find('.points').text()).toBe('4 / 6 P')
    expect(w.text()).toContain('from the solution')
    expect(w.text()).toContain('gemini-2.5-flash')
    expect(w.text()).not.toContain('unsure')
  })

  it('shows the range for an uncertain grade, the model id after the last slash', () => {
    const w = card({
      grade: grade({ certain: false, min: 3, max: 5, basis: 'own_solution', model: 'google/gemini-2.5-flash' }),
    })
    expect(w.find('.points').text()).toBe('3–5 / 6 P · unsure')
    expect(w.text()).toContain('own solution')
    expect(w.text()).not.toContain('google/')
  })

  it('marks lines by hit, tags the source and shows notes and feedback', () => {
    const w = card({ grade: grade() })
    const rows = w.findAll('[data-rubric-line]')
    expect(rows.map((r) => r.find('.mark').text())).toEqual(['✓', '◐', '✗'])
    expect(rows[1]!.text()).toContain('1 / 2')
    expect(rows[0]!.text()).toContain('guide')
    expect(rows[1]!.text()).toContain('inferred')
    expect(rows[2]!.text()).toContain('No word on retransmission.')
    expect(w.find('.feedback').text()).toContain('Solid on the steps.')
    expect(w.find('.feedback').text()).toContain('Missing losses.')
  })

  it('Re-grade emits regrade', async () => {
    const w = card({ grade: grade() })
    await w.findAll('button').find((b) => b.text() === 'Re-grade')!.trigger('click')
    expect(w.emitted('regrade')).toHaveLength(1)
  })

  it('pending shows grading… and the thinking text, without retry links', () => {
    const w = card({ grade: grade(), pending: 'comparing the steps' })
    expect(w.text()).toContain('grading…')
    expect(w.text()).toContain('comparing the steps')
    expect(w.find('button').exists()).toBe(false)
  })

  it('an error shows the message and Retry emits regrade', async () => {
    const w = card({ error: 'Rate limited' })
    expect(w.text()).toContain('Rate limited')
    await w.findAll('button').find((b) => b.text() === 'Retry')!.trigger('click')
    expect(w.emitted('regrade')).toHaveLength(1)
  })

  it('shows why a row was skipped, and nothing for automatic points', () => {
    expect(card({ skipped: 'no_answer' }).text()).toContain('No answer, not sent')
    expect(card({ skipped: 'auto' }).find('.llm').exists()).toBe(false)
  })

  it('renders nothing without a grade, error, pending or skip', () => {
    expect(card({}).find('.llm').exists()).toBe(false)
  })

  it('shows a verdict instead of points when the exam states none', () => {
    const v = (points: number, extra = {}) =>
      card({ max: null, grade: grade({ points, min: points, max: points, rubric: [], ...extra }) }).find('.points').text()
    expect(v(1)).toBe('✓ correct')
    expect(v(0)).toBe('✗ wrong')
    expect(v(0.5)).toBe('◐ partly (50%)')
    expect(v(0.5, { min: 0.25, max: 0.75, certain: false })).toBe('◐ partly (50%) · unsure')
  })
})
