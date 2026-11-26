import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import MaterialView from '../MaterialView.vue'

const viewer = { name: 'PdfViewer', props: ['url', 'page', 'terms'], template: '<div />' }

const docs = [
  { id: 'a', title: 'Chapter 1', kind: 'slides', subject: 'Numerik', position: 0, page_count: 5 },
  { id: 'b', title: 'Chapter 2', kind: 'slides', subject: 'Numerik', position: 1, page_count: 9 },
]
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

async function open(path: string) {
  vi.stubGlobal('fetch', async (url: string) => {
    if (url.startsWith('/api/documents?subject=')) return json(docs)
    const doc = docs.find((d) => url === `/api/documents/${d.id}`)
    return doc ? json(doc) : json({}, 404)
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/material/:id', name: 'material', component: MaterialView },
      { path: '/ask', name: 'ask', component: { template: '<div />' } },
    ],
  })
  router.push(path)
  await router.isReady()
  const w = mount(MaterialView, { global: { plugins: [router], stubs: { PdfViewer: viewer } } })
  await flushPromises()
  return w
}

describe('MaterialView', () => {
  it('opens the PDF at the cited page with the neighbouring Deck linked', async () => {
    const w = await open('/material/a?page=3&terms=huffman')
    expect(w.findComponent(viewer).props()).toEqual({ url: '/api/documents/a/file', page: 3, terms: 'huffman' })
    expect(w.text()).toContain('page 3 of 5')
    expect(w.text()).toContain('Next: Chapter 2')
    expect(w.text()).not.toContain('Previous')
  })

  it('defaults to page 1 and says so when the Deck is gone', async () => {
    expect((await open('/material/b')).findComponent(viewer).props('page')).toBe(1)
    expect((await open('/material/zzz')).text()).toContain("wasn't found")
  })
})
