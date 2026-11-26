import 'fake-indexeddb/auto'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { putExam } from '@/lib/db'
import type { ExamStructure } from '@/types/exam'
import ExamSettingsView from '../ExamSettingsView.vue'

const lib = vi.hoisted(() => ({ startAttempt: vi.fn() }))
vi.mock('@/stores/library', () => ({ useLibraryStore: () => lib }))

const stub = { template: '<div />' }
const sub = (id: string, mc = false) => ({
  id,
  label: id,
  points: 2,
  mc_options: mc ? [{ region: 0, bbox: {}, text: 'a' }] : undefined,
})
function structure(over: Partial<ExamStructure> = {}, mc = false): ExamStructure {
  return {
    source: 'x.pdf',
    tasks: [
      { id: 't1', number: '1', title: 'One', points: 10, subtasks: [sub('t1a', mc)] },
      { id: 't2', number: '2', title: 'Two', points: 5, subtasks: [sub('t2a')] },
    ],
    issues: [],
    ...over,
  } as unknown as ExamStructure
}

let n = 0
async function setup(s: ExamStructure) {
  setActivePinia(createPinia())
  const examId = `ex${n++}`
  await putExam({ id: examId, title: 'Exam X', structure: s, createdAt: 1, hasInk: false })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/exams/:examId/settings', name: 'exam-settings', component: ExamSettingsView },
      { path: '/attempts/:attemptId', name: 'exam', component: stub },
    ],
  })
  router.push(`/exams/${examId}/settings`)
  await router.isReady()
  const wrapper = mount(ExamSettingsView, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router, examId }
}

describe('ExamSettingsView', () => {
  beforeEach(() => lib.startAttempt.mockReset().mockResolvedValue('att1'))

  it('prefills 90 minutes and shows the summary', async () => {
    const { wrapper } = await setup(structure())
    expect(
      (wrapper.find('input[type=number][name=minutes]').element as HTMLInputElement).value,
    ).toBe('90')
    expect(wrapper.text()).toContain('2 tasks · 15 points')
  })

  it('prefills duration from the structure', async () => {
    const { wrapper } = await setup(structure({ duration_minutes: 120 }))
    expect((wrapper.find('input[name=minutes]').element as HTMLInputElement).value).toBe('120')
  })

  it('hides the MC rule without MC subtasks', async () => {
    const { wrapper } = await setup(structure())
    expect(wrapper.find('select[name=mcrule]').exists()).toBe(false)
  })

  it('shows the MC rule prefilled when MC exists', async () => {
    const { wrapper } = await setup(structure({}, true))
    expect((wrapper.find('select[name=mcrule]').element as HTMLSelectElement).value).toBe(
      'all_or_nothing',
    )
    const per = { kind: 'per_tick', right: 1, wrong: -1, floor: 0 } as const
    const w2 = (await setup(structure({ mc_rule: per }, true))).wrapper
    expect((w2.find('select[name=mcrule]').element as HTMLSelectElement).value).toBe('per_tick')
  })

  it('per tick shows editable right / wrong / minimum values and starts with them', async () => {
    const per = { kind: 'per_tick', right: 0.5, wrong: -0.5, floor: 0 } as const
    const { wrapper, examId } = await setup(structure({ mc_rule: per }, true))
    const field = (n: string) => wrapper.find(`input[name=${n}]`)
    expect((field('tick-right').element as HTMLInputElement).value).toBe('0.5')
    expect((field('tick-wrong').element as HTMLInputElement).value).toBe('-0.5')
    expect((field('tick-floor').element as HTMLInputElement).value).toBe('0')
    await field('tick-wrong').setValue('-1')
    await wrapper.find('button.start').trigger('click')
    await flushPromises()
    expect(lib.startAttempt).toHaveBeenCalledWith(
      examId,
      expect.objectContaining({ mcRule: { kind: 'per_tick', right: 0.5, wrong: -1, floor: 0 } }),
    )
  })

  it('switching to per tick without a parsed rule prefills 1 / -1 / 0', async () => {
    const { wrapper } = await setup(structure({}, true))
    expect(wrapper.find('input[name=tick-right]').exists()).toBe(false)
    await wrapper.find('select[name=mcrule]').setValue('per_tick')
    const val = (n: string) =>
      (wrapper.find(`input[name=${n}]`).element as HTMLInputElement).value
    expect([val('tick-right'), val('tick-wrong'), val('tick-floor')]).toEqual(['1', '-1', '0'])
  })

  it('starts with only ticked tasks and navigates', async () => {
    const { wrapper, router, examId } = await setup(structure())
    await wrapper.findAll('input[type=checkbox][name=task]')[0]!.setValue(false)
    await wrapper.find('button.start').trigger('click')
    await flushPromises()
    expect(lib.startAttempt).toHaveBeenCalledWith(
      examId,
      expect.objectContaining({
        includedTaskIds: ['t2'],
        timeLimitMin: 90,
        title: 'Exam X',
        subject: 'X',
        mcRule: { kind: 'all_or_nothing' },
        attendance: true,
      }),
    )
    expect(router.currentRoute.value.name).toBe('exam')
    expect(router.currentRoute.value.params.attemptId).toBe('att1')
  })

  it('disables Start when no task is included', async () => {
    const { wrapper } = await setup(structure())
    for (const c of wrapper.findAll('input[name=task]')) await c.setValue(false)
    expect(wrapper.find('button.start').attributes('disabled')).toBeDefined()
  })

  it('lists issues in a quiet note only when present', async () => {
    const a = await setup(structure({ issues: [{ level: 'warn', message: 'Odd layout' }] }))
    expect(a.wrapper.text()).toContain('Notes from reading the exam')
    expect(a.wrapper.text()).toContain('Odd layout')
    const b = await setup(structure())
    expect(b.wrapper.text()).not.toContain('Notes from reading the exam')
  })
})
