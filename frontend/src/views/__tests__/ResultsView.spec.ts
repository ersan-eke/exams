import 'fake-indexeddb/auto'
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { putAttempt, putExam } from '@/lib/db'
import { ans, attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import type { Attempt } from '@/types/attempt'
import { UploadError } from '@/lib/api'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'
import ResultsView from '../ResultsView.vue'

const structure = exam([task('A1', '1', [sub('A1a', 'a)', 60), sub('A1b', 'b)', 30)])])

async function setup(extra: Partial<Attempt> = {}, hasInk = false) {
  setActivePinia(createPinia())
  const id = crypto.randomUUID()
  const examId = crypto.randomUUID()
  await putExam({ id: examId, title: 'X', structure, createdAt: 1, hasInk })
  await putAttempt(
    attempt({
      id,
      examId,
      status: 'handed_in',
      startedAt: 0,
      handedInAt: 1000,
      includedTaskIds: ['A1'],
      ...extra,
    }),
  )
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/attempts/:attemptId/results', name: 'results', component: ResultsView },
      { path: '/attempts/:attemptId/grade/:mode', name: 'grade', component: { template: '<i/>' } },
      { path: '/exams/:examId/settings', name: 'exam-settings', component: { template: '<i/>' } },
      { path: '/', name: 'new', component: { template: '<i/>' } },
    ],
  })
  await router.push(`/attempts/${id}/results`)
  const w = mount(ResultsView, { global: { plugins: [router] } })
  await vi.waitFor(() => expect(w.find('[data-section="grading"]').exists()).toBe(true))
  await flushPromises()
  return Object.assign(w, { router, id, examId })
}

const button = (w: Awaited<ReturnType<typeof setup>>, text: string) =>
  w.findAll('.actions button').find((b) => b.text().startsWith(text))!

describe('ResultsView redirect', () => {
  it('a running attempt opened at its results URL goes to the exam', async () => {
    setActivePinia(createPinia())
    const id = crypto.randomUUID()
    const examId = crypto.randomUUID()
    await putExam({ id: examId, title: 'X', structure, createdAt: 1, hasInk: false })
    await putAttempt(attempt({ id, examId, status: 'running', includedTaskIds: ['A1'] }))
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/attempts/:attemptId', name: 'exam', component: { template: '<i/>' } },
        { path: '/attempts/:attemptId/results', name: 'results', component: ResultsView },
      ],
    })
    await router.push(`/attempts/${id}/results`)
    const w = mount(ResultsView, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('exam'))
    expect(w.find('[data-section="grading"]').exists()).toBe(false)
  })
})

describe('ResultsView grading', () => {
  it('shows the main score and no overtime score without a snapshot', async () => {
    const w = await setup({ grades: { A1a: { main: 41.5 }, A1b: { main: 20 } } })
    expect(w.find('.score-main').text()).toBe('61.5 / 90')
    expect(w.find('.score-over').exists()).toBe(false)
  })

  it('shows the overtime score when a snapshot exists', async () => {
    const w = await setup({
      snapshot: { A1a: ans() },
      answers: { A1a: ans({ text: 'late' }) },
      grades: { A1a: { main: 0, over: 9 }, A1b: { main: 62 } },
    })
    expect(w.find('.score-main').text()).toBe('62 / 90')
    expect(w.find('.score-over').text()).toBe('With overtime 71 / 90')
  })

  it('counts MC points auto-graded with the attached solution key', async () => {
    const opts = [{ region: 0, bbox: { x0: 0, y0: 0, x1: 0, y1: 0 }, text: 'yes' }]
    const solId = crypto.randomUUID()
    await putExam({
      id: solId,
      title: 'S',
      structure: exam([task('A1', '1', [sub('A1b', 'b)', 30, { mc_options: opts, mc_key: [0] })])]),
      createdAt: 1,
      hasInk: true,
    })
    const w = await setup({
      solutionExamId: solId,
      answers: { A1b: ans({ ticks: [0] }) },
      grades: { A1a: { main: 10 } },
    })
    await vi.waitFor(() => expect(w.find('.score-main').text()).toBe('40 / 90'))
  })

  it('shows the main score before any grading', async () => {
    const w = await setup()
    expect(w.find('.score-main').text()).toBe('0 / 90')
  })

  it('uploads a solution from the drop zone and switches to solution mode', async () => {
    const w = await setup()
    const library = useLibraryStore()
    const attach = vi.spyOn(library, 'attachSolution').mockResolvedValue()
    await button(w, 'Compare with solution').trigger('click')
    expect(w.text()).toContain('Drop the solution PDF here')
    const input = w.find('[data-solution-drop] input[type=file]')
    const pdf = new File(['x'], 's.pdf', { type: 'application/pdf' })
    Object.defineProperty(input.element, 'files', { value: [pdf], configurable: true })
    await input.trigger('change')
    await flushPromises()
    expect(attach).toHaveBeenCalledWith(expect.any(String), pdf)
    await vi.waitFor(() =>
      expect(w.router.currentRoute.value.fullPath).toBe(`/attempts/${w.id}/grade/solution`),
    )
  })

  it('shows the upload error in the drop zone', async () => {
    const w = await setup()
    vi.spyOn(useLibraryStore(), 'attachSolution').mockRejectedValue(new UploadError('not_pdf'))
    await button(w, 'Compare with solution').trigger('click')
    const input = w.find('[data-solution-drop] input[type=file]')
    Object.defineProperty(input.element, 'files', {
      value: [new File(['x'], 'a.txt')],
      configurable: true,
    })
    await input.trigger('change')
    await flushPromises()
    expect(w.find('[data-solution-drop]').text()).toContain("That file isn't a PDF.")
  })

  describe('Ask an LLM to grade', () => {
    const llmGrade = {
      points: 1, min: 1, max: 1, certain: true, basis: 'solution' as const, provider: 'google' as const,
      model: 'm', rubric: [], feedback: '',
    }
    const hint = (w: Awaited<ReturnType<typeof setup>>) => w.find('[data-llm-hint]').text()

    it('is disabled without a key for the chosen provider', async () => {
      localStorage.clear()
      const w = await setup()
      const b = button(w, 'Ask an LLM to grade')
      expect(b.attributes('disabled')).toBeDefined()
      expect(hint(w)).toBe('Add an API key in settings')
    })

    it('with a key and a solution it grades in solution mode', async () => {
      const w = await setup({}, true)
      const s = useSettingsStore()
      s.keys[s.provider] = 'k'
      await w.vm.$nextTick()
      expect(hint(w)).toBe('using the solution')
      await button(w, 'Ask an LLM to grade').trigger('click')
      await vi.waitFor(() =>
        expect(w.router.currentRoute.value.fullPath).toBe(`/attempts/${w.id}/grade/solution?llm=1`),
      )
    })

    it('without a solution it grades in self mode and says the model solves it first', async () => {
      const w = await setup()
      const s = useSettingsStore()
      s.keys[s.provider] = 'k'
      await w.vm.$nextTick()
      expect(hint(w)).toBe('no solution: the model solves it first')
      await button(w, 'Ask an LLM to grade').trigger('click')
      await vi.waitFor(() =>
        expect(w.router.currentRoute.value.fullPath).toBe(`/attempts/${w.id}/grade/self?llm=1`),
      )
    })

    it('shows the LLM summary once LLM grades exist', async () => {
      expect((await setup()).find('.summary').exists()).toBe(false)
      const w = await setup({ grades: { A1a: { llm: { main: llmGrade } } } })
      expect(w.find('.summary').exists()).toBe(true)
    })

    it('a summary chip opens the grading page at that row', async () => {
      const w = await setup({ grades: { A1a: { llm: { main: llmGrade } } } })
      await w.find('.chip').trigger('click')
      await vi.waitFor(() =>
        expect(w.router.currentRoute.value.fullPath).toBe(`/attempts/${w.id}/grade/self#A1a`),
      )
    })
  })

  it('"Grade myself" goes to the grading page', async () => {
    const w = await setup()
    await button(w, 'Grade myself').trigger('click')
    await vi.waitFor(() =>
      expect(w.router.currentRoute.value.fullPath).toBe(`/attempts/${w.id}/grade/self`),
    )
  })

  it('"Compare with solution" without a solution opens the upload drop zone', async () => {
    const w = await setup()
    await button(w, 'Compare with solution').trigger('click')
    expect(w.find('[data-solution-drop]').exists()).toBe(true)
    expect(w.router.currentRoute.value.name).toBe('results')
  })

  it('"Compare with solution" with ink goes to the grading page in solution mode', async () => {
    const w = await setup({}, true)
    await button(w, 'Compare with solution').trigger('click')
    await vi.waitFor(() =>
      expect(w.router.currentRoute.value.fullPath).toBe(`/attempts/${w.id}/grade/solution`),
    )
  })

  it('Retry goes to the exam settings, Home to the start page', async () => {
    const w = await setup()
    expect(w.find('[data-retry]').attributes('href')).toBe(`/exams/${w.examId}/settings`)
    expect(w.find('[data-home]').attributes('href')).toBe('/')
  })

  it('once graded, the time bars show points and group by correct / incorrect', async () => {
    const w = await setup({ gradedAt: 5, grades: { A1a: { main: 60 }, A1b: { main: 10 } } })
    await w.find('.toggle button').trigger('click')
    expect(w.findAll('.bars .p').map((p) => p.text())).toEqual(['60 / 60 P', '10 / 30 P'])
    const group = w.findAll('.sort.group').find((b) => b.text() === 'correct / incorrect')!
    await group.trigger('click')
    const sections = w.findAll('[data-section-title]')
    expect(sections.map((sec) => sec.attributes('data-section-title'))).toEqual([
      'Correct',
      'Incorrect',
    ])
    expect(sections[0]!.text()).toContain('1 a)')
    expect(sections[1]!.text()).toContain('1 b)')
  })

  it('before grading, there is no points column and no correct / incorrect grouping', async () => {
    const w = await setup({ grades: { A1a: { main: 60 } } })
    await w.find('.toggle button').trigger('click')
    expect(w.find('.bars .p').exists()).toBe(false)
    expect(w.text()).not.toContain('correct / incorrect')
  })
})
