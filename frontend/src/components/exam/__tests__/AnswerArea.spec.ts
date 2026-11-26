import 'fake-indexeddb/auto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAttemptStore } from '@/stores/attempt'
import { useSettingsStore } from '@/stores/settings'
import { attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import type { Subtask } from '@/types/exam'
import AnswerArea from '../AnswerArea.vue'
import DrawCanvas from '../DrawCanvas.vue'

const region = { page: 0, bbox: { x0: 0, y0: 0, x1: 1, y1: 1 }, image: 'a.png' }
const plain = sub('A1a', 'a)', 2)
const boxed = sub('A1a', 'a)', 2, {
  regions: [region],
  answer_boxes: [{ region: 0, bbox: { x0: 0.1, y0: 0.5, x1: 0.9, y1: 0.95 } }],
})

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
})
afterEach(() => vi.restoreAllMocks())

function setup(subtask: Subtask = plain) {
  setActivePinia(createPinia())
  const s = useAttemptStore()
  s.exam = { id: 'ex', title: 'x', structure: exam([task('A1', '1', [subtask])]), createdAt: 0, hasInk: false }
  s.attempt = attempt({ examId: 'ex' })
  return { s, w: mount(AnswerArea, { props: { subtask } }) }
}
type W = ReturnType<typeof setup>['w']
const button = (w: W, label: string) => w.findAll('button').find((b) => b.text() === label)!
const canvas = (w: W) => w.findComponent(DrawCanvas)

describe('AnswerArea', () => {
  it('offers Text and Draw only', () => {
    const { w } = setup()
    expect(w.findAll('[role=tab]').map((b) => b.text())).toEqual(['Text', 'Draw'])
  })

  it('typing updates the answer text', async () => {
    const { s, w } = setup()
    await w.find('textarea').setValue('hello')
    expect(s.attempt!.answers['A1a']!.parts[0]!.text).toBe('hello')
  })

  it('puts the text field on the printed answer box', () => {
    const { w } = setup(boxed)
    const t = w.find('.crop-wrap textarea')
    expect(t.exists()).toBe(true)
    expect(t.attributes('style')).toContain('left: 10%; top: 50%; width: 80%; height: 45%')
  })

  it('without an answer box the text field goes below the crops', () => {
    const { w } = setup({ ...plain, regions: [region] })
    expect(w.find('.crop-wrap textarea').exists()).toBe(false)
    expect(w.find('textarea.below').exists()).toBe(true)
  })

  it('Draw arms the canvas and keeps the text visible', async () => {
    const { s, w } = setup()
    await w.find('textarea').setValue('keep me')
    expect(canvas(w).props('pen')).toBeNull()
    await button(w, 'Draw').trigger('click')
    expect(s.attempt!.answers['A1a']!.mode).toBe('draw')
    expect(canvas(w).props('pen')).toMatchObject({ erase: false, color: '#1c1c1c' })
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('keep me')
  })

  it('pen sizes and colors, eraser sizes, and the wider marker', async () => {
    const { w } = setup()
    await button(w, 'Draw').trigger('click')
    expect(w.findAll('.size')).toHaveLength(3)
    expect(w.findAll('.color').map((c) => c.attributes('aria-label'))).toEqual([
      'Black',
      'Blue',
      'Orange',
      'Marker',
    ])
    await w.find('[aria-label="Large pen"]').trigger('click')
    await w.find('[aria-label="Blue"]').trigger('click')
    const blue = canvas(w).props('pen')!
    expect(blue.color).toBe('#1f56c4')
    await w.find('[aria-label="Marker"]').trigger('click')
    expect(canvas(w).props('pen')!.size).toBeCloseTo(blue.size * 4)

    await button(w, 'Eraser').trigger('click')
    expect(w.findAll('.color')).toHaveLength(0)
    expect(w.findAll('.size')).toHaveLength(3)
    await w.find('[aria-label="Small eraser"]').trigger('click')
    expect(canvas(w).props('pen')).toMatchObject({ erase: true, size: 0.015 })
    // picking a color goes back to the pen
    await button(w, 'Pen').trigger('click')
    expect(canvas(w).props('pen')!.erase).toBe(false)
  })

  it('a box split over two pages gives two parts, each with its own text, drawing and bar', async () => {
    const split = sub('A1a', 'a)', 2, {
      regions: [region, { ...region, page: 1, image: 'b.png' }],
      answer_boxes: [
        { region: 0, bbox: { x0: 0, y0: 0.5, x1: 1, y1: 1 } },
        { region: 1, bbox: { x0: 0, y0: 0, x1: 1, y1: 0.8 } },
      ],
    })
    const { s, w } = setup(split)
    expect(w.findAll('.part')).toHaveLength(2)
    expect(w.findAll('[role=tablist]')).toHaveLength(2)
    await w.findAll('textarea')[1]!.setValue('second')
    expect(s.attempt!.answers['A1a']!.parts.map((p) => p.text)).toEqual(['', 'second'])
    // Draw on the second part only
    await w.findAll('.part')[1]!.findAll('button').find((b) => b.text() === 'Draw')!.trigger('click')
    const canvases = w.findAllComponents(DrawCanvas)
    expect(canvases[0]!.props('pen')).toBeNull()
    expect(canvases[1]!.props('pen')).not.toBeNull()
    canvases[1]!.vm.$emit('update:strokes', [{ points: [[0, 0]], erase: false }])
    expect(s.attempt!.answers['A1a']!.parts[1]!.strokes).toHaveLength(1)
    expect(s.attempt!.answers['A1a']!.parts[1]!.text).toBe('second')
  })

  it('Clear removes all strokes', async () => {
    const { s, w } = setup()
    await button(w, 'Draw').trigger('click')
    canvas(w).vm.$emit('update:strokes', [{ points: [[0, 0]], erase: false }])
    expect(s.attempt!.answers['A1a']!.parts[0]!.strokes).toHaveLength(1)
    await button(w, 'Clear').trigger('click')
    expect(s.attempt!.answers['A1a']!.parts[0]!.strokes).toEqual([])
  })

  it('starts in the default answer mode', () => {
    setActivePinia(createPinia())
    useSettingsStore().defaultAnswerMode = 'draw'
    const s = useAttemptStore()
    s.exam = { id: 'ex', title: 'x', structure: exam([task('A1', '1', [plain])]), createdAt: 0, hasInk: false }
    s.attempt = attempt({ examId: 'ex' })
    const w = mount(AnswerArea, { props: { subtask: plain } })
    expect(w.find('[role=toolbar]').exists()).toBe(true)
  })
})
