import 'fake-indexeddb/auto'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { putAttempt, putExam } from '@/lib/db'
import { useAttemptStore } from '@/stores/attempt'
import { attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import ExamModals from '../ExamModals.vue'

const structure = exam([task('A1', '1', [sub('A1a', 'a)', 1)])])

async function setup() {
  setActivePinia(createPinia())
  const id = crypto.randomUUID()
  await putExam({ id: 'ex', title: 'X', structure, createdAt: 1, hasInk: false })
  await putAttempt(
    attempt({ id, examId: 'ex', startedAt: Date.now(), timeLimitMs: 3_600_000, includedTaskIds: ['A1'] }),
  )
  const store = useAttemptStore()
  await store.load(id)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/attempts/:attemptId', name: 'exam', component: ExamModals },
      { path: '/attempts/:attemptId/results', name: 'results', component: { template: '<i/>' } },
    ],
  })
  await router.push(`/attempts/${id}`)
  const w = mount(ExamModals, { global: { plugins: [router] } })
  return { w, store, router, id }
}

const btn = (label: string) =>
  Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent === label)

describe('ExamModals', () => {
  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('attendance has no buttons, ignores Esc, and finishes after 5 s', async () => {
    const { w, store } = await setup()
    vi.useFakeTimers()
    const spy = vi.spyOn(store, 'finishAttendance')
    store.modal = 'attendance'
    await flushPromises()
    expect(document.body.textContent).toContain('Attendance check')
    expect(document.body.textContent).toContain('A tutor is checking your ID. Please wait.')
    expect(document.body.querySelectorAll('button')).toHaveLength(0)
    document.body.querySelector('.backdrop')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(store.modal).toBe('attendance')
    vi.advanceTimersByTime(4000)
    expect(spy).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1000)
    expect(spy).toHaveBeenCalledTimes(1)
    w.unmount()
  })

  it('time up: Keep going extends', async () => {
    const { w, store } = await setup()
    store.modal = 'timeup'
    await flushPromises()
    expect(document.body.textContent).toContain('The exam has ended. Please hand in.')
    btn('Keep going')!.click()
    await flushPromises()
    expect(store.attempt!.extended).toBe(true)
    expect(store.modal).toBeNull()
    w.unmount()
  })

  it('time up: Hand in ends at results', async () => {
    const { w, store, router, id } = await setup()
    store.modal = 'timeup'
    await flushPromises()
    btn('Hand in')!.click()
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('results'))
    expect(router.currentRoute.value.params.attemptId).toBe(id)
    expect(store.attempt!.status).toBe('handed_in')
    w.unmount()
  })

  it('hand in dialog: Back to exam cancels, Hand in ends at results', async () => {
    const { w, store, router } = await setup()
    store.requestHandIn()
    await flushPromises()
    expect(document.body.textContent).toContain("You can't change your answers afterwards.")
    btn('Back to exam')!.click()
    await flushPromises()
    expect(store.modal).toBeNull()
    store.requestHandIn()
    await flushPromises()
    const replace = vi.spyOn(router, 'replace')
    btn('Hand in')!.click()
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('results'))
    // replace, so browser Back can't return to the editable exam
    expect(replace).toHaveBeenCalled()
    w.unmount()
  })
})
