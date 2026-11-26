import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { UploadError } from '@/lib/api'
import type { Attempt, StoredExam } from '@/types/attempt'
import NewExamView from '../NewExamView.vue'

const lib = vi.hoisted(() => ({
  importUpload: vi.fn(),
  recent: vi.fn(),
  running: vi.fn(),
}))
vi.mock('@/stores/library', () => ({ useLibraryStore: () => lib }))

const stub = { template: '<div />' }
function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'new', component: NewExamView },
      { path: '/exams/:examId/settings', name: 'exam-settings', component: stub },
      { path: '/attempts/:attemptId', name: 'exam', component: stub },
      { path: '/attempts/:attemptId/results', name: 'results', component: stub },
    ],
  })
}

async function setup() {
  const router = makeRouter()
  router.push('/')
  await router.isReady()
  const wrapper = mount(NewExamView, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

const pdf = new File(['x'], 'a.pdf', { type: 'application/pdf' })
async function pick(wrapper: Awaited<ReturnType<typeof setup>>['wrapper'], file = pdf) {
  const input = wrapper.find('input[type=file]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
}

const exam = (id: string, title: string) => ({ id, title }) as StoredExam
const attempt = (id: string, status: Attempt['status']) => ({ id, status }) as Attempt

describe('NewExamView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    lib.importUpload.mockReset()
    lib.recent.mockReset().mockResolvedValue([])
    lib.running.mockReset().mockResolvedValue(undefined)
  })

  it('shows the drop zone text', async () => {
    const { wrapper } = await setup()
    expect(wrapper.text()).toContain('Drop an old exam here')
    expect(wrapper.text()).toContain('PDF · exam or solution · stays on this device')
  })

  it('shows reading state while the upload is pending', async () => {
    lib.importUpload.mockReturnValue(new Promise(() => {}))
    const { wrapper } = await setup()
    await pick(wrapper)
    expect(wrapper.text()).toContain('Reading the exam…')
    expect(wrapper.text()).not.toContain('Drop an old exam here')
  })

  it('navigates to settings after a successful upload', async () => {
    lib.importUpload.mockResolvedValue('e1')
    const { wrapper, router } = await setup()
    await pick(wrapper)
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('exam-settings')
    expect(router.currentRoute.value.params.examId).toBe('e1')
  })

  it.each([
    ['not_pdf', "That file isn't a PDF."],
    ['scanned', "Scanned exams aren't supported yet."],
    ['no_tasks', 'No tasks found in this PDF.'],
    ['network', "Couldn't reach the server. Try again."],
    ['server', "Couldn't reach the server. Try again."],
  ] as const)('shows error for %s', async (code, message) => {
    lib.importUpload.mockRejectedValue(new UploadError(code))
    const { wrapper } = await setup()
    await pick(wrapper)
    await flushPromises()
    expect(wrapper.text()).toContain(message)
    expect(wrapper.text()).toContain('Drop an old exam here')
  })

  it('shows Continue exam link when an attempt is running', async () => {
    lib.running.mockResolvedValue(attempt('a1', 'running'))
    const { wrapper } = await setup()
    const link = wrapper.find('a[href="/attempts/a1"]')
    expect(link.text()).toContain('Continue exam')
  })

  it('has no Continue link without a running attempt', async () => {
    const { wrapper } = await setup()
    expect(wrapper.text()).not.toContain('Continue exam')
  })

  it('lists recent exams with links depending on the latest attempt', async () => {
    lib.recent.mockResolvedValue([
      { exam: exam('e1', 'Done exam'), latest: attempt('a1', 'handed_in') },
      { exam: exam('e2', 'Running exam'), latest: attempt('a2', 'running') },
      { exam: exam('e3', 'Fresh exam'), latest: undefined },
    ])
    const { wrapper } = await setup()
    expect(wrapper.find('a[href="/attempts/a1/results"]').text()).toContain('Done exam')
    expect(wrapper.find('a[href="/attempts/a2"]').text()).toContain('Running exam')
    expect(wrapper.find('a[href="/exams/e3/settings"]').text()).toContain('Fresh exam')
  })
})
