import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { attempt, exam } from '@/lib/__tests__/fixtures'
import type { StoredExam } from '@/types/attempt'
import MyExamsView from '../MyExamsView.vue'

const lib = vi.hoisted(() => ({ catalog: vi.fn(), updateExam: vi.fn() }))
vi.mock('@/stores/library', () => ({ useLibraryStore: () => lib }))

const stub = { template: '<div />' }
const stored = (id: string, title: string, p: Partial<StoredExam> = {}): StoredExam => ({
  id, title, structure: exam([]), createdAt: 0, hasInk: false, ...p,
})

async function setup() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/my-exams', name: 'my-exams', component: MyExamsView },
      { path: '/exams/:examId/view', name: 'exam-view', component: stub },
      { path: '/attempts/:attemptId', name: 'exam', component: stub },
      { path: '/attempts/:attemptId/results', name: 'results', component: stub },
    ],
  })
  router.push('/my-exams')
  await router.isReady()
  const wrapper = mount(MyExamsView, { global: { plugins: [router, createPinia()] } })
  await flushPromises()
  return wrapper
}

describe('MyExamsView', () => {
  beforeEach(() => {
    lib.updateExam.mockReset().mockResolvedValue(undefined)
    lib.catalog.mockReset().mockResolvedValue({
      exams: [
        stored('e1', 'GRNVS 2019', { hasInk: true }),
        stored('e2', 'GRNVS 2020'),
        stored('e3', 'GBS 2021', { hidden: true }),
        stored('s1', 'GRNVS 2020 Lösung', { solutionFor: 'a1', hasInk: true }),
      ],
      attempts: [
        attempt({ id: 'a1', examId: 'e2', status: 'handed_in', handedInAt: 61_000, solutionExamId: 's1' }),
      ],
    })
  })

  it('groups exams by subject in folded bars, hidden ones in their own section', async () => {
    const w = await setup()
    const bars = w.findAll('.fold-bar').map((b) => b.text())
    expect(bars[0]).toContain('GRNVS')
    expect(bars[0]).toContain('2 exams')
    expect(bars[1]).toContain('Hidden')
    expect(w.find('[data-exam]').exists()).toBe(false)

    await w.findAll('.fold-bar')[0]!.trigger('click')
    const rows = w.findAll('[data-exam]')
    expect(rows.map((r) => r.attributes('data-exam'))).toEqual(['e1', 'e2'])
    // own ink, then an attached solution
    expect(rows[0]!.find('[data-solution]').attributes('href')).toBe('/exams/e1/view?ink=1')
    expect(rows[1]!.find('[data-solution]').attributes('href')).toBe('/exams/s1/view?ink=1')
    expect(rows[1]!.text()).toContain('not graded')
    expect(w.text()).not.toContain('Lösung')

    await rows[1]!.find('button.chev').trigger('click')
    expect(rows[1]!.find('.attempt').attributes('href')).toBe('/attempts/a1/results')
  })

  it('hides an exam and reloads', async () => {
    const w = await setup()
    await w.findAll('.fold-bar')[0]!.trigger('click')
    await w.find('[data-exam=e1] button.act').trigger('click')
    await flushPromises()
    expect(lib.updateExam).toHaveBeenCalledWith('e1', { hidden: true })
    expect(lib.catalog).toHaveBeenCalledTimes(2)
  })
})
