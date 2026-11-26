import 'fake-indexeddb/auto'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ans, attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import { useAttemptStore } from '@/stores/attempt'
import type { Attempt, StoredExam } from '@/types/attempt'
import DrawCanvas from '@/components/exam/DrawCanvas.vue'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'
import { reactive } from 'vue'
import { putExam } from '@/lib/db'
import GradingList from '../GradingList.vue'

const route = reactive<{ query: Record<string, string> }>({ query: {} })
const replace = vi.fn()
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ replace }) }))

const mcOptions = [
  { region: 0, bbox: { x0: 0, y0: 0, x1: 0, y1: 0 }, text: 'yes' },
  { region: 0, bbox: { x0: 0, y0: 0, x1: 0, y1: 0 }, text: 'no' },
]
const structure = exam([
  task('A1', '1', [
    sub('A1a', 'a)', 2),
    sub('A1b', 'b)', 3),
    sub('A1c', 'c)', 1, { mc_options: mcOptions, mc_key: [0] }),
    sub('A1d', 'd)', null),
  ]),
])
const stored: StoredExam = { id: 'e', title: 'X', structure, createdAt: 1, hasInk: false }

function setup(extra: Partial<Attempt> = {}, mode: 'solution' | 'self' = 'self') {
  setActivePinia(createPinia())
  const store = useAttemptStore()
  store.exam = stored
  store.attempt = attempt({
    status: 'handed_in',
    includedTaskIds: ['A1'],
    answers: {
      A1a: ans({ text: 'final a' }),
      A1b: ans({ text: 'late b' }),
      A1c: ans({ ticks: [0] }),
    },
    snapshot: {
      A1a: ans({ text: 'final a' }),
      A1b: ans({ text: 'early b' }),
      A1c: ans({ ticks: [0] }),
    },
    ...extra,
  })
  const setGrade = vi.spyOn(store, 'setGrade')
  const w = mount(GradingList, { props: { mode } })
  return { w, store, setGrade }
}

const row = (w: ReturnType<typeof mount>, id: string) => w.find(`[data-grade-row="${id}"]`)

describe('GradingList', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    route.query = {}
    replace.mockReset()
  })

  it('shows two pickers only for subtasks changed in overtime', () => {
    const { w } = setup()
    expect(row(w, 'A1a').findAll('[data-picker]')).toHaveLength(1)
    const b = row(w, 'A1b')
    expect(b.findAll('[data-picker]')).toHaveLength(2)
    expect(b.text()).toContain('In time')
    expect(b.text()).toContain('Overtime')
    const texts = b.findAll('textarea').map((t) => (t.element as HTMLTextAreaElement).value)
    expect(texts).toEqual(['early b', 'late b'])
  })

  it('picking 1.5 grades the main score', async () => {
    const { w, setGrade } = setup()
    const btn = row(w, 'A1a')
      .findAll('[data-picker] button')
      .find((x) => x.text() === '1.5')!
    await btn.trigger('click')
    expect(setGrade).toHaveBeenCalledWith('A1a', { main: 1.5 })
  })

  it('the overtime picker grades the overtime score', async () => {
    const { w, setGrade } = setup()
    const pickers = row(w, 'A1b').findAll('[data-picker]')
    await pickers[1]!
      .findAll('button')
      .find((x) => x.text() === '2')!
      .trigger('click')
    expect(setGrade).toHaveBeenCalledWith('A1b', { over: 2 })
  })

  it('offers 0..max in 0.5 steps, and a number field without known points', async () => {
    const { w, setGrade } = setup()
    const labels = row(w, 'A1a')
      .findAll('[data-picker] button')
      .map((b) => b.text())
    expect(labels).toEqual(['0', '0.5', '1', '1.5', '2'])
    const input = row(w, 'A1d').find('[data-picker] input')
    expect(input.exists()).toBe(true)
    await input.setValue('4.5')
    expect(setGrade).toHaveBeenCalledWith('A1d', { main: 4.5 })
  })

  it('a fractional max gets a final step equal to max', async () => {
    setActivePinia(createPinia())
    const store = useAttemptStore()
    store.exam = { ...stored, structure: exam([task('A1', '1', [sub('A1a', 'a)', 2.25)])]) }
    store.attempt = attempt({ status: 'handed_in', includedTaskIds: ['A1'] })
    const setGrade = vi.spyOn(store, 'setGrade')
    const w = mount(GradingList, { props: { mode: 'self' } })
    const buttons = row(w, 'A1a').findAll('[data-picker] button.step')
    expect(buttons).toHaveLength(6)
    await buttons[5]!.trigger('click')
    expect(setGrade).toHaveBeenCalledWith('A1a', { main: 2.25 })
  })

  it('Clear removes a grade; an MC row goes back to automatic', async () => {
    const { w, store } = setup()
    const clearGrade = vi.spyOn(store, 'clearGrade')
    expect(row(w, 'A1a').find('[data-clear]').exists()).toBe(false)
    await row(w, 'A1c')
      .findAll('[data-picker] button')
      .find((x) => x.text() === '0 P')!
      .trigger('click')
    expect(store.attempt!.grades.A1c).toEqual({ main: 0 })
    expect(row(w, 'A1c').text()).not.toContain('automatic')
    await row(w, 'A1c').find('[data-clear]').trigger('click')
    expect(clearGrade).toHaveBeenCalledWith('A1c', 'main')
    expect(store.attempt!.grades.A1c).toBeUndefined()
    expect(row(w, 'A1c').text()).toContain('automatic')
  })

  it('MC with a key but unknown points gets a free points field and a verdict', () => {
    const noPts = exam([
      task('A1', '1', [sub('A1c', 'c)', null, { mc_options: mcOptions, mc_key: [0] })]),
    ])
    setActivePinia(createPinia())
    const store = useAttemptStore()
    store.exam = { ...stored, structure: noPts }
    store.attempt = attempt({
      status: 'handed_in',
      includedTaskIds: ['A1'],
      answers: { A1c: ans({ ticks: [0] }) },
    })
    const w = mount(GradingList, { props: { mode: 'self' } })
    const c = row(w, 'A1c')
    expect(c.text()).not.toContain('automatic')
    expect(c.find('[data-picker] input').exists()).toBe(true)
    expect(c.find('[data-verdict]').text()).toBe('Correct')
  })

  it('MC points without their own come from the task total split over its MC subtasks', () => {
    const shared = {
      ...task('A1', '1', [
        sub('m1', 'a)', null, { mc_options: mcOptions, mc_key: [0] }),
        sub('m2', 'b)', null, { mc_options: mcOptions, mc_key: [1] }),
      ]),
      points: 3,
    }
    setActivePinia(createPinia())
    const store = useAttemptStore()
    store.exam = { ...stored, structure: exam([shared]) }
    store.attempt = attempt({
      status: 'handed_in',
      includedTaskIds: ['A1'],
      answers: { m1: ans({ ticks: [0] }), m2: ans({ ticks: [0] }) },
    })
    const w = mount(GradingList, { props: { mode: 'self' } })
    const labels = row(w, 'm1')
      .findAll('[data-picker] button.step')
      .map((b) => b.text())
    expect(labels).toEqual(['0 P', '1.5 P'])
    expect(row(w, 'm1').find('[data-picker] .step.on').text()).toBe('1.5 P')
    expect(row(w, 'm2').find('[data-verdict]').text()).toBe('Incorrect')
    expect(row(w, 'm2').find('[data-picker] .step.on').text()).toBe('0 P')
  })

  it('a per-tick rule offers its partial points between 0 P and full', () => {
    const three = [...mcOptions, { region: 0, bbox: mcOptions[0]!.bbox, text: 'maybe' }]
    setActivePinia(createPinia())
    const store = useAttemptStore()
    store.exam = {
      ...stored,
      structure: exam([task('A1', '1', [sub('m', 'a)', 2, { mc_options: three, mc_key: [0, 1] })])]),
    }
    store.attempt = attempt({
      status: 'handed_in',
      includedTaskIds: ['A1'],
      mcRule: { kind: 'per_tick', right: 1, wrong: -1, floor: 0 },
      answers: { m: ans({ ticks: [0] }) },
    })
    const w = mount(GradingList, { props: { mode: 'self' } })
    const labels = row(w, 'm')
      .findAll('[data-picker] button.step')
      .map((b) => b.text())
    expect(labels).toEqual(['0 P', '1 P', '2 P'])
  })

  it('MC with a key preselects the automatic points and says it is correct', async () => {
    const { w, setGrade } = setup()
    const c = row(w, 'A1c')
    const steps = c.findAll('[data-picker] button.step')
    expect(steps.map((b) => b.text())).toEqual(['0 P', '1 P'])
    expect(c.find('[data-picker] .step.on').text()).toBe('1 P')
    expect(c.text()).toContain('automatic')
    expect(c.find('[data-verdict]').classes()).toContain('good')
    await c.find('[data-picker] input').setValue('0.5')
    expect(setGrade).toHaveBeenCalledWith('A1c', { main: 0.5 })
  })

  it('renders legacy paper and drawn answers read-only', async () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    const { w } = setup({
      snapshot: null,
      answers: {
        A1a: ans({ done: true }),
        A1b: ans({
          mode: 'draw',
          strokes: [
            {
              points: [
                [0, 0],
                [1, 1],
              ],
              erase: false,
            },
          ],
        }),
      },
    })
    await flushPromises()
    expect(row(w, 'A1a').text()).toContain('Answered on paper')
    expect(row(w, 'A1b').find('canvas').classes()).not.toContain('active')
    expect(row(w, 'A1b').find('textarea').attributes('readonly')).toBeDefined()
  })

  it('self mode shows no solution, solution mode shows the ink crop', async () => {
    const withRegion = exam([
      task('A1', '1', [
        sub('A1a', 'a)', 2, {
          regions: [{ page: 1, bbox: { x0: 0, y0: 0, x1: 1, y1: 1 }, image: 'a.png' }],
        }),
      ]),
    ])
    setActivePinia(createPinia())
    const store = useAttemptStore()
    store.exam = { ...stored, structure: withRegion, hasInk: true }
    store.attempt = attempt({ status: 'handed_in', includedTaskIds: ['A1'] })
    const self = mount(GradingList, { props: { mode: 'self' } })
    expect(self.find('[data-solution]').exists()).toBe(false)
    const sol = mount(GradingList, { props: { mode: 'solution' } })
    expect(sol.find('[data-solution]').exists()).toBe(true)
  })

  it('MC shows one crop: the ticks as crosses, the key outlined in red', () => {
    const region = { page: 1, bbox: { x0: 0, y0: 0, x1: 1, y1: 1 }, image: 'a.png' }
    const boxed = [
      { region: 0, bbox: { x0: 0.1, y0: 0.1, x1: 0.2, y1: 0.2 }, text: 'yes' },
      { region: 0, bbox: { x0: 0.1, y0: 0.5, x1: 0.2, y1: 0.6 }, text: 'no' },
    ]
    const withMc = exam([
      task('A1', '1', [
        sub('A1a', 'a)', 1, { regions: [region], mc_options: boxed, mc_key: [0], solution_text: '× ×' }),
        sub('A1b', 'b)', 1, { regions: [region], solution_text: 'free text sol' }),
      ]),
    ])
    setActivePinia(createPinia())
    const store = useAttemptStore()
    store.exam = { ...stored, structure: withMc, hasInk: true }
    store.attempt = attempt({
      status: 'handed_in',
      includedTaskIds: ['A1'],
      answers: { A1a: ans({ ticks: [1] }), A1b: ans({ text: 'mine' }) },
    })
    const w = mount(GradingList, { props: { mode: 'solution' } })
    const a = row(w, 'A1a')
    expect(a.find('[data-solution]').exists()).toBe(false)
    expect(a.findAll('img, .placeholder')).toHaveLength(1)
    expect(a.find('[data-mc-box="1"]').classes()).toContain('on')
    expect(a.find('[data-mc-box="0"] [data-mc-outline]').classes()).toContain('key')
    expect(a.find('[data-mc-box="1"] [data-mc-outline]').classes()).not.toContain('key')
    expect(a.find('[data-verdict]').text()).toBe('Incorrect')
    // free text: the solution crop replaces the separate solution text, the answer sits below
    const b = row(w, 'A1b')
    expect(b.find('[data-solution]').exists()).toBe(true)
    expect(b.find('[data-solution]').text()).not.toContain('free text sol')
    expect((b.find('textarea').element as HTMLTextAreaElement).value).toBe('mine')
  })

  it('MC without a detected key shows the solution crop to grade by hand', () => {
    const region = { page: 1, bbox: { x0: 0, y0: 0, x1: 1, y1: 1 }, image: 'a.png' }
    const boxed = [{ region: 0, bbox: { x0: 0.1, y0: 0.1, x1: 0.2, y1: 0.2 }, text: 'yes' }]
    const noKey = exam([
      task('A1', '1', [sub('A1a', 'a)', 1, { regions: [region], mc_options: boxed, mc_key: null, solution_text: 'sol text' })]),
    ])
    setActivePinia(createPinia())
    const store = useAttemptStore()
    store.exam = { ...stored, structure: noKey, hasInk: true }
    store.attempt = attempt({ status: 'handed_in', includedTaskIds: ['A1'] })
    const w = mount(GradingList, { props: { mode: 'solution' } })
    expect(row(w, 'A1a').find('[data-solution]').exists()).toBe(true)
    expect(row(w, 'A1a').find('[data-verdict]').exists()).toBe(false)
  })

  it('comments and pen marks are saved on the grade', async () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    const { w, store } = setup({ snapshot: null })
    const a = row(w, 'A1a')
    expect(a.find('[aria-label="Comment"]').exists()).toBe(false)
    await a.findAll('button').find((b) => b.text() === 'Comment')!.trigger('click')
    await a.find('[aria-label="Comment"]').setValue('good start')
    expect(store.attempt!.grades.A1a!.comment).toBe('good start')

    expect(a.find('[role=toolbar]').exists()).toBe(false)
    await a.find('[data-mark]').trigger('click')
    expect(a.findAll('.color').map((c) => c.attributes('aria-label'))).toEqual(['Red', 'Green'])
    expect(a.findAll('.size')).toHaveLength(3)
    const marks = a.findAllComponents(DrawCanvas).find((c: { attributes: (k: string) => string | undefined }) => c.attributes('data-marks') !== undefined)!
    expect(marks.props('pen')).toMatchObject({ erase: false, color: '#c62828' })
    marks.vm.$emit('update:strokes', [{ points: [[0, 0]], erase: false }])
    expect(store.attempt!.grades.A1a!.marks!.main).toHaveLength(1)
    expect(store.attempt!.grades.A1a!.comment).toBe('good start')
    await a.findAll('button').find((b) => b.text() === 'Clear')!.trigger('click')
    expect(store.attempt!.grades.A1a!.marks).toEqual({})
  })

  it('without ink, uses the matched subtask of the linked solution exam', async () => {
    const { putExam } = await import('@/lib/db')
    const solId = crypto.randomUUID()
    await putExam({
      id: solId,
      title: 'S',
      createdAt: 1,
      hasInk: true,
      structure: exam([
        task('T1', '1', [sub('other-id', 'a)', 2, { solution_text: 'sol text a' })]),
      ]),
    })
    const { w } = setup({ solutionExamId: solId }, 'solution')
    await vi.waitFor(() => expect(row(w, 'A1a').find('[data-solution]').exists()).toBe(true))
    expect(row(w, 'A1a').text()).toContain('sol text a')
    expect(row(w, 'A1b').text()).toContain('No matching solution found.')
  })

  it('auto-grades MC of a blank exam with the key of the attached solution', async () => {
    const { putExam } = await import('@/lib/db')
    const solId = crypto.randomUUID()
    const blank = exam([task('A1', '1', [sub('A1c', 'c)', 2, { mc_options: mcOptions })])])
    await putExam({
      id: solId,
      title: 'S',
      createdAt: 1,
      hasInk: true,
      structure: exam([task('T1', '1', [sub('s1', 'c)', 2, { mc_options: mcOptions, mc_key: [0] })])]),
    })
    setActivePinia(createPinia())
    const store = useAttemptStore()
    store.exam = { ...stored, structure: blank }
    store.attempt = attempt({
      status: 'handed_in',
      includedTaskIds: ['A1'],
      answers: { A1c: ans({ ticks: [0] }) },
      solutionExamId: solId,
    })
    const w = mount(GradingList, { props: { mode: 'solution' } })
    await vi.waitFor(() => expect(row(w, 'A1c').text()).toContain('automatic'))
    expect(row(w, 'A1c').find('[data-picker] .step.on').text()).toBe('2 P')
    expect(row(w, 'A1c').find('[data-verdict]').text()).toBe('Correct')
  })

  it('shows no matching solution when the linked solution exam is missing', async () => {
    const { w } = setup({ solutionExamId: 'does-not-exist' }, 'solution')
    await vi.waitFor(() => expect(row(w, 'A1a').text()).toContain('No matching solution found.'))
  })

  it('?llm=1 starts one grading pass with the planned jobs and drops the query', async () => {
    route.query = { llm: '1' }
    setActivePinia(createPinia())
    const settings = useSettingsStore()
    settings.provider = 'google'
    settings.keys.google = 'k-123'
    const store = useAttemptStore()
    store.exam = stored
    store.attempt = attempt({
      status: 'handed_in',
      includedTaskIds: ['A1'],
      answers: { A1a: ans({ text: 'x' }), A1b: ans({ text: 'y' }), A1c: ans({ ticks: [0] }) },
    })
    const run = vi.spyOn(store, 'gradeWithLlm').mockResolvedValue()
    mount(GradingList, { props: { mode: 'solution' } })
    await vi.waitFor(() => expect(run).toHaveBeenCalledTimes(1))
    const [jobs, skipped, key] = run.mock.calls[0]!
    expect(jobs.map((j) => j.key)).toEqual(['A1a:main', 'A1b:main'])
    expect(skipped).toMatchObject({ A1c: 'auto', A1d: 'no_answer' })
    expect(key).toMatchObject({ google: 'k-123' })
    expect(replace).toHaveBeenCalledWith({ query: {} })
  })

  it('without ?llm=1 it only registers the planned jobs for Re-grade', async () => {
    setActivePinia(createPinia())
    const store = useAttemptStore()
    const run = vi.spyOn(store, 'gradeWithLlm').mockResolvedValue()
    const prepare = vi.spyOn(store, 'prepareLlm')
    store.exam = stored
    store.attempt = attempt({
      status: 'handed_in',
      includedTaskIds: ['A1'],
      answers: { A1a: ans({ text: 'x' }), A1b: ans({ text: 'y' }) },
    })
    mount(GradingList, { props: { mode: 'self' } })
    await vi.waitFor(() => expect(prepare).toHaveBeenCalledTimes(1))
    expect(prepare.mock.calls[0]![0].map((j) => j.key)).toEqual(['A1a:main', 'A1b:main'])
    expect(prepare.mock.calls[0]![1]).toMatchObject({ A1c: 'no_answer' })
    expect(run).not.toHaveBeenCalled()
  })

  it('shows the LLM card under an answer, with its retry', async () => {
    const { w, store } = setup()
    store.llm.errors['A1a:main'] = 'Rate limited'
    const regrade = vi.spyOn(store, 'regrade').mockResolvedValue()
    await flushPromises()
    await row(w, 'A1a').findAll('button').find((b) => b.text() === 'Retry')!.trigger('click')
    expect(regrade).toHaveBeenCalledWith('A1a:main', expect.objectContaining({ anthropic: expect.any(String) }))
  })

  it('Max points: shows the max, "set points" when missing, and changing it rescales the row', async () => {
    const { w, store } = setup()
    await putExam(stored)
    const r = () => row(w, 'A1d')
    expect((row(w, 'A1a').find('input[aria-label="Max points"]').element as HTMLInputElement).value).toBe('2')
    expect(r().find('input[aria-label="Max points"]').exists()).toBe(false)
    expect(r().text()).toContain('set points')
    expect(r().find('[data-picker] .step').exists()).toBe(false)
    await r().find('button.mode').trigger('click')
    const input = r().find('input[aria-label="Max points"]')
    await input.setValue('2')
    await input.trigger('change')
    await vi.waitFor(() => expect(store.exam!.structure.tasks[0]!.subtasks[3]!.points).toBe(2))
    await flushPromises()
    expect(r().findAll('[data-picker] .step').map((b) => b.text())).toContain('2')
  })

  it('max input: empty clears the override, invalid input is rejected and resets', async () => {
    const { w } = setup()
    const spy = vi.spyOn(useLibraryStore(), 'setPoints').mockResolvedValue()
    const input = row(w, 'A1a').find('input[aria-label="Max points"]')
    const el = input.element as HTMLInputElement
    el.value = ''
    await input.trigger('change')
    expect(spy).toHaveBeenLastCalledWith('e', 'A1a', null)
    spy.mockClear()
    el.value = '-3' // no await between: a re-render would restore the max
    await input.trigger('change')
    expect(spy).not.toHaveBeenCalled()
    expect(el.value).toBe('2') // back to the current max
  })
})
