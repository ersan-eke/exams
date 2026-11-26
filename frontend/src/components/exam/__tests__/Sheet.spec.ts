import 'fake-indexeddb/auto'
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAttemptStore } from '@/stores/attempt'
import { attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import Sheet from '../Sheet.vue'

const ctx = (id: string, applies_from: string | null) => ({
  id,
  applies_from,
  regions: [],
  text: '',
})
const t1 = task(
  'A1',
  '1',
  [sub('A1a', 'a)', 1), sub('A1b', 'b)', 1), sub('A1c', 'c)', 2)],
  [ctx('ctx0', null), ctx('ctx1', 'A1b'), ctx('ctx2', 'A1c')],
)
const t2 = task('A2', '2', [sub('A2a', 'a)', 1)], [ctx('ctx3', null)])

function setup(shown: string[], folded: string[] = []) {
  setActivePinia(createPinia())
  const s = useAttemptStore()
  s.exam = { id: 'ex', title: 'X', structure: exam([t1, t2]), createdAt: 1, hasInk: false }
  s.attempt = attempt({
    examId: 'ex',
    includedTaskIds: ['A1', 'A2'],
    view: { shown, folded, expandedTasks: [], outlineCollapsed: false },
  })
  return { s, w: mount(Sheet) }
}

describe('Sheet', () => {
  it('renders contexts and shown subtasks interleaved in exam order', () => {
    const { w } = setup(['A1c', 'A1a'])
    expect(w.findAll('[data-block]').map((b) => b.attributes('data-block'))).toEqual([
      'ctx0',
      'A1a',
      'ctx1',
      'ctx2',
      'A1c',
    ])
    expect(w.text()).toContain('Context · Aufgabe 1')
    expect(w.text()).toContain('Aufgabe 1 · c)')
    expect(w.text()).toContain('2 P')
  })

  it('only includes the contexts that apply', () => {
    const { w } = setup(['A1a'])
    expect(w.findAll('[data-block]').map((b) => b.attributes('data-block'))).toEqual([
      'ctx0',
      'A1a',
    ])
  })

  it('toggling a fold bar calls toggleFold with the block id', async () => {
    const { s, w } = setup(['A1c', 'A1a'])
    const spy = vi.spyOn(s, 'toggleFold')
    await w.get('[data-block="ctx1"] .fold-bar').trigger('click')
    expect(spy).toHaveBeenCalledWith('ctx1')
    await w.get('[data-block="A1c"] .fold-bar').trigger('click')
    expect(spy).toHaveBeenCalledWith('A1c')
  })

  it('a folded block hides its body', () => {
    const { w } = setup(['A1a'], ['A1a'])
    expect(w.get('[data-block="A1a"] .fold-bar').attributes('aria-expanded')).toBe('false')
    expect(w.find('[data-block="A1a"] .fold-body').exists()).toBe(false)
    expect(w.find('[data-block="ctx0"] .fold-body').exists()).toBe(true)
  })
})
