import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import DrawCanvas from '../DrawCanvas.vue'

const ctxStub = new Proxy(
  {},
  { get: (_t, k) => (k === 'canvas' ? null : () => undefined), set: () => true },
)

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    ctxStub as unknown as CanvasRenderingContext2D,
  )
  vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({
    left: 10,
    top: 20,
    width: 200,
    height: 100,
    right: 210,
    bottom: 120,
    x: 10,
    y: 20,
    toJSON: () => ({}),
  })
})
afterEach(() => vi.restoreAllMocks())

/** jsdom has no PointerEvent: dispatch a MouseEvent carrying the pointer fields */
function fire(c: ReturnType<ReturnType<typeof mount>['find']>, type: string, x: number, y: number, extra = {}) {
  const e = new MouseEvent(type, { clientX: x, clientY: y, bubbles: true })
  Object.assign(e, { pointerId: 1, isPrimary: true, ...extra })
  c.element.dispatchEvent(e)
  return nextTick()
}

async function draw(w: ReturnType<typeof mount>) {
  const c = w.find('canvas')
  await fire(c, 'pointerdown', 10, 20)
  await fire(c, 'pointermove', 110, 70)
  await fire(c, 'pointerup', 210, 120)
}

const pen = { erase: false, color: '#1f56c4', size: 0.004 }

describe('DrawCanvas', () => {
  it('emits one stroke with normalized points and the pen look', async () => {
    const w = mount(DrawCanvas, { props: { strokes: [], pen } })
    await draw(w)
    const emitted = w.emitted('update:strokes')!
    expect(emitted).toHaveLength(1)
    expect(emitted[0]![0]).toEqual([
      {
        points: [
          [0, 0],
          [0.5, 0.5],
          [1, 1],
        ],
        erase: false,
        color: '#1f56c4',
        size: 0.004,
      },
    ])
  })

  it('ignores non-primary pointers', async () => {
    const w = mount(DrawCanvas, { props: { strokes: [], pen } })
    await fire(w.find('canvas'), 'pointerdown', 10, 20, { isPrimary: false })
    await fire(w.find('canvas'), 'pointerup', 10, 20, { isPrimary: false })
    expect(w.emitted('update:strokes')).toBeUndefined()
  })

  it('eraser strokes have erase: true', async () => {
    const w = mount(DrawCanvas, { props: { strokes: [], pen: { ...pen, erase: true } } })
    await draw(w)
    const out = w.emitted('update:strokes')![0]![0] as { erase: boolean }[]
    expect(out[0]!.erase).toBe(true)
  })

  it('without a pen it only shows the strokes', async () => {
    const w = mount(DrawCanvas, {
      props: { strokes: [{ points: [[0, 0], [1, 1]], erase: false }] },
    })
    expect(w.find('canvas').classes()).not.toContain('active')
    await draw(w)
    expect(w.emitted('update:strokes')).toBeUndefined()
  })
})
