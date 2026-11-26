import 'fake-indexeddb/auto'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { putAttempt, putExam } from '@/lib/db'
import { useAttemptStore } from '@/stores/attempt'
import { attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import ExamView from '../ExamView.vue'

const structure = exam([
  task('A1', '1', [sub('A1a', 'a)', 1), sub('A1b', 'b)', 1)], [
    { id: 'c0', applies_from: null, regions: [], text: '' },
  ]),
])

function mockWidth(narrow: boolean) {
  vi.stubGlobal(
    'matchMedia',
    (q: string) =>
      ({
        matches: narrow,
        media: q,
        addEventListener: () => {},
        removeEventListener: () => {},
      }) as unknown as MediaQueryList,
  )
}

async function setup(outlineCollapsed: boolean) {
  setActivePinia(createPinia())
  const id = crypto.randomUUID()
  await putExam({ id: 'ex', title: 'X', structure, createdAt: 1, hasInk: false })
  await putAttempt(
    attempt({
      id,
      examId: 'ex',
      startedAt: Date.now(),
      timeLimitMs: 3_600_000,
      includedTaskIds: ['A1'],
      view: { shown: ['A1a'], folded: [], expandedTasks: ['A1'], outlineCollapsed },
    }),
  )
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/attempts/:attemptId', name: 'exam', component: ExamView }],
  })
  await router.push(`/attempts/${id}`)
  const w = mount(ExamView, { global: { plugins: [router] } })
  await vi.waitFor(() => expect(w.find('.body').exists()).toBe(true))
  await flushPromises()
  return w
}

describe('ExamView', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('a handed-in attempt redirects to its results', async () => {
    setActivePinia(createPinia())
    const id = crypto.randomUUID()
    await putExam({ id: 'ex', title: 'X', structure, createdAt: 1, hasInk: false })
    await putAttempt(attempt({ id, examId: 'ex', status: 'handed_in', includedTaskIds: ['A1'] }))
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/attempts/:attemptId', name: 'exam', component: ExamView },
        { path: '/attempts/:attemptId/results', name: 'results', component: { template: '<i/>' } },
      ],
    })
    await router.push(`/attempts/${id}`)
    const replace = vi.spyOn(router, 'replace')
    const w = mount(ExamView, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('results'))
    expect(replace).toHaveBeenCalled()
    expect(w.find('.body').exists()).toBe(false)
    w.unmount()
  })

  it('wide: shows the outline unless collapsed', async () => {
    mockWidth(false)
    const w = await setup(false)
    expect(w.find('.tree').exists()).toBe(true)
    expect(w.find('.rail').exists()).toBe(false)
    w.unmount()
  })

  it('narrow: the drawer starts closed, opens from the rail and closes on pick', async () => {
    mockWidth(true)
    const w = await setup(false)
    expect(w.find('.tree').exists()).toBe(false)
    await w.get('.rail button').trigger('click')
    expect(w.find('.tree').exists()).toBe(true)
    await w.get('[data-id="A1b"]').trigger('click')
    expect(w.find('.tree').exists()).toBe(false)
    expect(w.find('.rail').exists()).toBe(true)
    await w.get('.rail button').trigger('click')
    await w.get('[data-id="c0"]').trigger('click')
    expect(w.find('.tree').exists()).toBe(false)
    expect(useAttemptStore().attempt!.view.outlineCollapsed).toBe(false)
    w.unmount()
  })
})
