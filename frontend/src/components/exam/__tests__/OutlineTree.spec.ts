import 'fake-indexeddb/auto'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAttemptStore } from '@/stores/attempt'
import { ans, attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import type { Attempt } from '@/types/attempt'
import OutlineTree from '../OutlineTree.vue'

const ctx = (id: string, applies_from: string | null) => ({ id, applies_from, regions: [], text: '' })
const t1 = {
  ...task('A1', '1', [sub('A1a', 'a)', 3), sub('A1b', 'b)', 1), sub('A1c', 'c)', 2)], [
    ctx('c0', null),
  ]),
  title: 'Wireshark',
  points: 6,
}
const t2 = { ...task('A2', '2', [sub('A2x', '', 4)]), title: 'IPv6', points: 4 }
const t3 = { ...task('A3', '3', [sub('A3a', 'a)', 1)]), title: 'Excluded', points: 1 }

function setup(p: Partial<Attempt> = {}) {
  setActivePinia(createPinia())
  const s = useAttemptStore()
  s.exam = { id: 'ex', title: 'X', structure: exam([t1, t2, t3]), createdAt: 1, hasInk: false }
  s.attempt = attempt({
    examId: 'ex',
    includedTaskIds: ['A1', 'A2'],
    view: { shown: ['A1b'], folded: [], expandedTasks: ['A1'], outlineCollapsed: false },
    ...p,
  })
  return { s, w: mount(OutlineTree) }
}

const row = (w: ReturnType<typeof mount>, id: string) => w.get(`[data-id="${id}"]`)

describe('OutlineTree', () => {
  beforeEach(() => localStorage.clear())

  it('renders included tasks with points; excluded tasks are absent', () => {
    const { w } = setup()
    expect(row(w, 'A1').text()).toContain('1 Wireshark')
    expect(row(w, 'A1').text()).toContain('6')
    expect(w.find('[data-id="A3"]').exists()).toBe(false)
    expect(w.text()).not.toContain('Excluded')
  })

  it('clicking the chevron toggles the subtasks', async () => {
    const { w } = setup()
    expect(w.find('[data-id="A1a"]').exists()).toBe(true)
    await row(w, 'A1').get('.chev').trigger('click')
    expect(w.find('[data-id="A1a"]').exists()).toBe(false)
    await row(w, 'A1').get('.chev').trigger('click')
    expect(w.find('[data-id="A1a"]').exists()).toBe(true)
  })

  it('clicking a subtask row shows only that subtask', async () => {
    const { s, w } = setup()
    const spy = vi.spyOn(s, 'showOnly')
    await row(w, 'A1c').trigger('click')
    expect(spy).toHaveBeenCalledWith('A1c')
  })

  it('hovering a row reveals an eye; the eye toggles shown without showOnly', async () => {
    const { s, w } = setup()
    const only = vi.spyOn(s, 'showOnly')
    const toggle = vi.spyOn(s, 'toggleShown')
    expect(row(w, 'A1c').get('button.eye').classes()).not.toContain('visible')
    await row(w, 'A1c').trigger('mouseenter')
    expect(row(w, 'A1c').get('button.eye').classes()).toContain('visible')
    await row(w, 'A1c').get('button.eye').trigger('click')
    expect(toggle).toHaveBeenCalledWith('A1c')
    expect(only).not.toHaveBeenCalled()
  })

  it('every subtask row has a clickable eye without hover (touch, pen)', async () => {
    const { s, w } = setup()
    const only = vi.spyOn(s, 'showOnly')
    const toggle = vi.spyOn(s, 'toggleShown')
    for (const id of ['A1a', 'A1b', 'A1c', 'A2x']) {
      await row(w, id).get('button.eye').trigger('click')
      expect(toggle).toHaveBeenLastCalledWith(id)
    }
    expect(only).not.toHaveBeenCalled()
    expect(w.emitted('pick')).toBeUndefined()
  })

  it('emits pick after a subtask or context row is chosen', async () => {
    const { w } = setup()
    await row(w, 'A1a').trigger('click')
    await row(w, 'c0').trigger('click')
    expect(w.emitted('pick')).toHaveLength(2)
  })

  it('marks answered and shown rows', () => {
    const { w } = setup({ answers: { A1a: ans({ text: 'x' }), A1c: ans() } })
    expect(row(w, 'A1a').classes()).toContain('answered')
    expect(row(w, 'A1c').classes()).not.toContain('answered')
    expect(row(w, 'A1b').classes()).toContain('shown')
    expect(row(w, 'A1a').classes()).not.toContain('shown')
  })

  it('a task with a single unlabeled subtask is one row titled with the task title', async () => {
    const { s, w } = setup()
    const spy = vi.spyOn(s, 'showOnly')
    expect(w.find('[data-id="A2"]').exists()).toBe(false)
    const r = row(w, 'A2x')
    expect(r.text()).toContain('2 IPv6')
    expect(r.text()).toContain('4')
    expect(r.find('.chev').exists()).toBe(false)
    await r.trigger('click')
    expect(spy).toHaveBeenCalledWith('A2x')
  })

  it('lists context under an expanded task; clicking jumps there and unfolds it', async () => {
    const { s, w } = setup({
      view: { shown: ['A1c'], folded: ['c0'], expandedTasks: ['A1'], outlineCollapsed: false },
    })
    const fold = vi.spyOn(s, 'toggleFold')
    await row(w, 'c0').trigger('click')
    expect(s.attempt!.view.shown).toEqual(['A1a'])
    expect(fold).toHaveBeenCalledWith('c0')
  })
  it('a subtask without label in a task without title is called Question', () => {
    setActivePinia(createPinia())
    const s = useAttemptStore()
    const t = task('B1', '1', [sub('B1x', '', 1), sub('B1y', 'b)', 1)])
    s.exam = { id: 'ex', title: 'X', structure: exam([t]), createdAt: 1, hasInk: false }
    s.attempt = attempt({
      examId: 'ex',
      includedTaskIds: ['B1'],
      view: { shown: ['B1x'], folded: [], expandedTasks: ['B1'], outlineCollapsed: false },
    })
    const w = mount(OutlineTree)
    expect(row(w, 'B1x').find('.name').text()).toBe('Question')
  })
})
