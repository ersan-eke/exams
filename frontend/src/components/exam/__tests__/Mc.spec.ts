import 'fake-indexeddb/auto'
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAttemptStore } from '@/stores/attempt'
import { attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import type { McOption } from '@/types/exam'
import McOverlay from '../McOverlay.vue'
import McButtonList from '../McButtonList.vue'
import SubtaskBlock from '../SubtaskBlock.vue'

const b = (x0: number, y0: number, x1: number, y1: number) => ({ x0, y0, x1, y1 })
const texts = [
  'Es gibt drei unterschiedliche Signalpegel.',
  'Es handelt sich um einen Leitungscode.',
  'Es wird Gleichstromfreiheit garantiert.',
  'Es handelt sich um einen Kanalcode.',
  '01 erzeugt immer eine Pegeländerung.',
  'Ein Symbol kodiert 3 bit.',
]
const boxes = [
  b(0.027, 0.282, 0.048, 0.405),
  b(0.027, 0.562, 0.048, 0.685),
  b(0.027, 0.819, 0.048, 0.942),
  b(0.526, 0.282, 0.547, 0.405),
  b(0.526, 0.538, 0.547, 0.661),
  b(0.526, 0.795, 0.547, 0.918),
]
const options: McOption[] = boxes.map((bbox, i) => ({ region: 0, bbox, text: texts[i]! }))
const noBox: McOption[] = texts.map((text) => ({ region: 0, bbox: b(0, 0, 0, 0), text }))

describe('McOverlay', () => {
  it('renders one percentage-positioned box hit area per option', () => {
    const w = mount(McOverlay, { props: { options, regionIndex: 0, ticks: [] } })
    const boxesEls = w.findAll('[data-mc-box]')
    expect(boxesEls).toHaveLength(6)
    const style = boxesEls[0]!.attributes('style')!
    expect(style).toContain('%')
    expect(style).toMatch(/left: 2\.\d+%/)
  })

  it('outlines the exact box inside the padded hit area (boxes may be painted over in the crop)', () => {
    const w = mount(McOverlay, { props: { options, regionIndex: 0, ticks: [] } })
    const outline = w.find('[data-mc-box="0"] [data-mc-outline]')
    expect(outline.exists()).toBe(true)
    // box 0.027..0.048 padded by 30 % of its width on each side → box sits at 18.75 % .. 81.25 %
    expect(outline.attributes('style')).toContain('left: 18.75%')
    expect(outline.attributes('style')).toContain('width: 62.5%')
  })

  it('a zero-size box gives no NaN positions', () => {
    const flat: McOption[] = [{ region: 0, bbox: b(0.1, 0.1, 0.1, 0.1), text: '' }]
    const w = mount(McOverlay, { props: { options: flat, regionIndex: 0, ticks: [] } })
    // jsdom drops invalid values like "NaN%", so check the positions survived
    const style = w.find('[data-mc-outline]').attributes('style') ?? ''
    expect(style).toContain('left: 0%')
    expect(style).toContain('width: 100%')
  })

  it('emits toggle with the option index on click', async () => {
    const w = mount(McOverlay, { props: { options, regionIndex: 0, ticks: [] } })
    await w.findAll('[data-mc-box]')[1]!.trigger('click')
    expect(w.emitted('toggle')).toEqual([[1]])
  })

  it('clicking the option text also toggles', async () => {
    const w = mount(McOverlay, { props: { options, regionIndex: 0, ticks: [] } })
    await w.find('[data-mc-text="3"]').trigger('click')
    expect(w.emitted('toggle')).toEqual([[3]])
  })

  it('shows a cross for ticked options only', () => {
    const w = mount(McOverlay, { props: { options, regionIndex: 0, ticks: [2] } })
    const on = w.findAll('[data-mc-box].on')
    expect(on).toHaveLength(1)
    expect(on[0]!.attributes('data-mc-box')).toBe('2')
    expect(on[0]!.text()).toBe('✕')
  })

  it('only renders options of its region but emits global indices', async () => {
    const mixed = [{ ...options[0]!, region: 0 }, { ...options[1]!, region: 1 }]
    const w = mount(McOverlay, { props: { options: mixed, regionIndex: 1, ticks: [] } })
    expect(w.findAll('[data-mc-box]')).toHaveLength(1)
    await w.find('[data-mc-box]').trigger('click')
    expect(w.emitted('toggle')).toEqual([[1]])
  })

  it('readonly shows crosses but ignores clicks', async () => {
    const w = mount(McOverlay, { props: { options, regionIndex: 0, ticks: [0, 4], readonly: true } })
    expect(w.findAll('[data-mc-box].on')).toHaveLength(2)
    await w.find('[data-mc-box]').trigger('click')
    await w.find('[data-mc-text="1"]').trigger('click')
    expect(w.emitted('toggle')).toBeUndefined()
  })
})

describe('McButtonList', () => {
  it('lists the options in order and toggles on click', async () => {
    const w = mount(McButtonList, { props: { options: noBox, ticks: [1] } })
    const btns = w.findAll('button')
    expect(btns.map((x) => x.text())).toEqual(texts.map((t, i) => (i === 1 ? `✕ ${t}` : t)))
    await btns[2]!.trigger('click')
    expect(w.emitted('toggle')).toEqual([[2]])
  })
})

describe('SubtaskBlock multiple choice', () => {
  function setup(mc: McOption[] | undefined) {
    setActivePinia(createPinia())
    const s = useAttemptStore()
    const st = sub('A6e', 'e)', 2, {
      regions: [{ page: 1, bbox: b(0, 0, 1, 1), image: 'r0.png' }],
      mc_options: mc,
    })
    s.exam = { id: 'ex', title: 'X', structure: exam([task('A6', '6', [st])]), createdAt: 1, hasInk: false }
    s.attempt = attempt({
      examId: 'ex',
      includedTaskIds: ['A6'],
      view: { shown: ['A6e'], folded: [], expandedTasks: [], outlineCollapsed: false },
    })
    return { s, w: mount(SubtaskBlock, { props: { task: s.exam.structure.tasks[0]!, subtask: st } }) }
  }

  it('hides AnswerArea and overlays hit areas; toggling stores sorted unique ticks', async () => {
    const { s, w } = setup(options)
    expect(w.findComponent({ name: 'AnswerArea' }).exists()).toBe(false)
    expect(w.findAll('[data-mc-box]')).toHaveLength(6)
    await w.findAll('[data-mc-box]')[4]!.trigger('click')
    await w.findAll('[data-mc-box]')[1]!.trigger('click')
    expect(s.attempt!.answers['A6e']!.ticks).toEqual([1, 4])
    await w.findAll('[data-mc-box]')[4]!.trigger('click')
    expect(s.attempt!.answers['A6e']!.ticks).toEqual([1])
  })

  it('falls back to the button list when no option has a bbox', () => {
    const { w } = setup(noBox)
    expect(w.findAll('[data-mc-box]')).toHaveLength(0)
    expect(w.findComponent(McButtonList).exists()).toBe(true)
    expect(w.findComponent({ name: 'AnswerArea' }).exists()).toBe(false)
  })

  it('falls back to the button list when only some options have a bbox', () => {
    const { w } = setup([...options.slice(0, 5), noBox[5]!])
    expect(w.findAll('[data-mc-box]')).toHaveLength(0)
    expect(w.findComponent(McButtonList).findAll('button')).toHaveLength(6)
  })

  it('falls back to the button list when the region image is missing', () => {
    setActivePinia(createPinia())
    const s = useAttemptStore()
    const st = sub('A6e', 'e)', 2, {
      regions: [{ page: 1, bbox: b(0, 0, 1, 1), image: null }],
      mc_options: options,
    })
    s.exam = { id: 'ex', title: 'X', structure: exam([task('A6', '6', [st])]), createdAt: 1, hasInk: false }
    s.attempt = attempt({ examId: 'ex', includedTaskIds: ['A6'] })
    const w = mount(SubtaskBlock, { props: { task: s.exam.structure.tasks[0]!, subtask: st } })
    expect(w.findComponent(McButtonList).exists()).toBe(true)
  })

  it('shows AnswerArea when there are no mc options', () => {
    const { w } = setup(undefined)
    expect(w.findComponent({ name: 'AnswerArea' }).exists()).toBe(true)
  })
})
