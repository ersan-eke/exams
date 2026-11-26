import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const getPage = vi.fn<(n: number) => Promise<object>>(async () => ({
  getViewport: ({ scale }: { scale: number }) => ({ width: 100 * scale, height: 50 * scale, scale }),
  render: () => ({ promise: Promise.resolve() }),
  streamTextContent: () => ({}),
}))
const getDocument = vi.fn<(o: object) => object>(() => ({ promise: Promise.resolve({ numPages: 9, getPage }), destroy: async () => {} }))
vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: {},
  getDocument,
  TextLayer: class {
    textDivs: HTMLElement[] = []
    constructor(o: { container: HTMLElement }) {
      const span = document.createElement('span')
      span.textContent = 'The Huffman-Code tree'
      o.container.append(span)
      this.textDivs = [span]
    }
    render = async () => {}
  },
}))
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: 'worker.js' }))
vi.mock('pdfjs-dist/web/pdf_viewer.css', () => ({}))

const { default: PdfViewer } = await import('../PdfViewer.vue')

describe('PdfViewer', () => {
  it('changes page without loading the PDF again and highlights the terms', async () => {
    HTMLCanvasElement.prototype.getContext = (() => null) as never
    const w = mount(PdfViewer, { props: { url: '/f', page: 2, terms: 'huffman' } })
    await flushPromises()
    expect(getPage).toHaveBeenLastCalledWith(2)
    expect(w.find('mark').text()).toBe('Huffman')

    await w.setProps({ page: 5 })
    await flushPromises()
    expect(getPage).toHaveBeenLastCalledWith(5)
    expect(getDocument).toHaveBeenCalledTimes(1)
  })

  it('ends on the last Deck clicked after A → B → A with late loads, without an error', async () => {
    HTMLCanvasElement.prototype.getContext = (() => null) as never
    const loads: { url: string; resolve: () => void; destroyed: boolean }[] = []
    getDocument.mockImplementation(({ url }: { url?: string } = {}) => {
      const load = { url: url!, resolve: () => {}, destroyed: false }
      loads.push(load)
      const promise = new Promise((res, rej) => {
        load.resolve = () => (load.destroyed ? rej(new Error('destroyed')) : res({
          numPages: 9,
          getPage: async (n: number) => (load.destroyed ? Promise.reject(new Error('destroyed')) : getPage(n)),
        }))
      })
      return { promise, destroy: async () => { load.destroyed = true } }
    })
    const w = mount(PdfViewer, { props: { url: '/a', page: 1, terms: '' } })
    await flushPromises()
    loads[0]!.resolve()
    await flushPromises()
    await w.setProps({ url: '/b' })
    await w.setProps({ url: '/a' })
    const callsBefore = getPage.mock.calls.length
    loads.slice(1).forEach((l) => l.resolve())
    await flushPromises()

    expect(w.emitted('error')).toBeUndefined()
    expect(getPage).toHaveBeenCalledTimes(callsBefore + 1)
    expect(loads[loads.length - 1]).toMatchObject({ url: '/a', destroyed: false })
    expect(loads.filter((l) => !l.destroyed)).toHaveLength(1)
  })

  it('cancels the page still being drawn before drawing the next one, without an error', async () => {
    HTMLCanvasElement.prototype.getContext = (() => null) as never
    let active = 0
    const cancels = vi.fn()
    getDocument.mockImplementation(() => ({
      promise: Promise.resolve({
        numPages: 9,
        getPage: async () => ({
          getViewport: ({ scale }: { scale: number }) => ({ width: 100 * scale, height: 50 * scale, scale }),
          render: () => {
            // pdf.js refuses a second render on a canvas that is still being drawn
            if (active) throw new Error('Cannot use the same canvas during multiple render() operations')
            active++
            let reject!: (e: Error) => void
            const promise = new Promise<void>((_, rej) => (reject = rej))
            return {
              promise: promise.finally(() => active--),
              cancel: () => {
                cancels()
                reject(Object.assign(new Error('cancelled'), { name: 'RenderingCancelledException' }))
              },
            }
          },
          streamTextContent: () => ({}),
        }),
      }),
      destroy: async () => {},
    }))
    const w = mount(PdfViewer, { props: { url: '/c', page: 1, terms: '' } })
    await flushPromises()
    await w.setProps({ page: 2 })
    await flushPromises()
    expect(cancels).toHaveBeenCalledTimes(1)
    expect(w.emitted('error')).toBeUndefined()
  })
})
