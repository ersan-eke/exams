import 'fake-indexeddb/auto'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { getAttempt, putAttempt, putExam } from '@/lib/db'
import { ans, attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import { useAttemptStore } from '@/stores/attempt'
import { useSettingsStore } from '@/stores/settings'
import GradingView from '../GradingView.vue'

async function open(grades = {}, extra = {}) {
  setActivePinia(createPinia())
  const id = crypto.randomUUID()
  const examId = crypto.randomUUID()
  const structure = exam([task('A1', '1', [sub('A1a', 'a)', 2)])])
  await putExam({ id: examId, title: 'X', structure, createdAt: 1, hasInk: false })
  await putAttempt(
    attempt({
      id, examId, status: 'handed_in', handedInAt: 2000, includedTaskIds: ['A1'],
      answers: { A1a: ans({ text: 'my answer' }) }, grades, ...extra,
    }),
  )
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/attempts/:attemptId/grade/:mode', name: 'grade', component: GradingView }],
  })
  await router.push(`/attempts/${id}/grade/self`)
  const w = mount(GradingView, { global: { plugins: [router] }, attachTo: document.body })
  await vi.waitFor(() => expect(w.find('[data-grade-row="A1a"]').exists()).toBe(true))
  return w
}
const llmGrade = {
  points: 1, min: 1, max: 1, certain: true, basis: 'solution', provider: 'google', model: 'm',
  rubric: [], feedback: '',
}

describe('GradingView', () => {
  it('lists the subtasks and Finish grading saves and goes back to the results', async () => {
    setActivePinia(createPinia())
    const id = crypto.randomUUID()
    const examId = crypto.randomUUID()
    const structure = exam([task('A1', '1', [sub('A1a', 'a)', 2)])])
    await putExam({ id: examId, title: 'X', structure, createdAt: 1, hasInk: false })
    await putAttempt(
      attempt({ id, examId, status: 'handed_in', handedInAt: 2000, includedTaskIds: ['A1'] }),
    )
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/attempts/:attemptId/grade/:mode', name: 'grade', component: GradingView },
        { path: '/attempts/:attemptId/results', name: 'results', component: { template: '<i/>' } },
      ],
    })
    await router.push(`/attempts/${id}/grade/self`)
    const w = mount(GradingView, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(w.find('[data-grade-row="A1a"]').exists()).toBe(true))
    expect(w.find('[data-solution]').exists()).toBe(false)
    await w.find('[data-finish]').trigger('click')
    await vi.waitFor(() =>
      expect(router.currentRoute.value.fullPath).toBe(`/attempts/${id}/results`),
    )
    expect((await getAttempt(id))!.gradedAt).toBeGreaterThan(0)
  })

  it('shows progress and Stop while grading, nothing when idle', async () => {
    const w = await open()
    expect(w.find('[role=progressbar]').exists()).toBe(false)
    const store = useAttemptStore()
    useSettingsStore().provider = 'google'
    const stop = vi.spyOn(store, 'stopLlm')
    store.llm.total = 5
    store.llm.done = 2
    await w.vm.$nextTick()
    expect(w.find('[data-llm-progress]').text()).toContain('Gemini is grading · 2 / 5')
    const bar = w.find('[role=progressbar]')
    expect(bar.attributes('aria-valuenow')).toBe('2')
    expect(bar.attributes('aria-valuemax')).toBe('5')
    await w.findAll('button').find((b) => b.text() === 'Stop')!.trigger('click')
    expect(stop).toHaveBeenCalled()
    store.llm.done = 5
    await w.vm.$nextTick()
    expect(w.find('[role=progressbar]').exists()).toBe(false)
  })

  it('shows the LLM summary above the list; a chip scrolls its row into view', async () => {
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    const w = await open({ A1a: { llm: { main: llmGrade } } })
    await w.find('.summary .chip').trigger('click')
    expect(scroll).toHaveBeenCalled()
  })

  it('has no summary without LLM grades', async () => {
    const w = await open()
    expect(w.find('.summary').exists()).toBe(false)
  })

  describe('eval export', () => {
    afterEach(() => vi.unstubAllGlobals())

    it('downloads cases.jsonl for versions with a self-grade', async () => {
      const w = await open({ A1a: { main: 2 } })
      const blobs: Blob[] = []
      URL.createObjectURL = (b: Blob | MediaSource) => (blobs.push(b as Blob), 'blob:x')
      URL.revokeObjectURL = () => {}
      const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
      await w.find('[data-export-eval]').trigger('click')
      await vi.waitFor(() => expect(click).toHaveBeenCalled())
      const lines = (await blobs[0]!.text()).trim().split('\n').map((l) => JSON.parse(l))
      expect(lines).toHaveLength(1)
      expect(lines[0]).toMatchObject({ id: 'A1a:main', expected: 2 })
    })
  })
})
