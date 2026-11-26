import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useSettingsStore } from '@/stores/settings'
import StudyView from '../StudyView.vue'

const viewer = { name: 'PdfViewer', props: ['url', 'page', 'terms'], template: '<div />' }
const outline = [
  { title: 'Intro', page: 1, children: [{ title: 'Why', page: 2 }, { title: 'Goals', page: 4 }] },
  { title: 'Wrap-up', page: 9, children: [] },
]
const docs = [
  { id: 'a', title: 'Chapter 1', kind: 'slides', subject: 'Numerik', position: 0, page_count: 12, outline, outline_source: 'automatic' },
  { id: 'b', title: 'Chapter 2', kind: 'slides', subject: 'Numerik', position: 1, page_count: 0, outline: null, outline_source: null },
]

const aiOutline = [{ title: 'Teil A', page: 1, children: [{ title: 'Start', page: 1 }] }]
const calls: { url: string; init?: RequestInit }[] = []

async function open(key = '') {
  setActivePinia(createPinia())
  useSettingsStore().keys.anthropic = key
  calls.length = 0
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url === '/api/chats') return new Response(JSON.stringify({ id: 'c1', title: 'New chat', updated_at: '', messages: [], pinned: [] }), { status: 200 })
    if (url === '/api/chats/c1/messages') return new Response(JSON.stringify({ id: 'c1' }), { status: 200 })
    if (url === '/api/chats/c1/pinned') return new Response(JSON.stringify({ id: 'c1', pinned: [{ document_id: 'a', page: 4 }] }), { status: 200 })
    if (url === '/api/chats/c1' || url === '/api/chats/c1/pinned') return new Response(JSON.stringify({ id: 'c1' }), { status: 200 })
    if (url.endsWith('/outline/ai')) return new Response(JSON.stringify({ ...docs[0], outline: aiOutline, outline_source: 'ai' }), { status: 200 })
    if (url.endsWith('/outline/reset')) return new Response(JSON.stringify(docs[0]), { status: 200 })
    return new Response(JSON.stringify(url === '/api/documents?subject=Numerik' ? docs : []), { status: 200 })
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/study/:subject', name: 'study', component: StudyView },
      { path: '/ask', name: 'ask', component: { template: '<div />' } },
    ],
  })
  router.push('/study/Numerik')
  await router.isReady()
  const w = mount(StudyView, { global: { plugins: [router], stubs: { PdfViewer: viewer } } })
  await flushPromises()
  return Object.assign(w, { router })
}

describe('StudyView', () => {
  it('shows level 1 when a Deck is unfolded, level 2 when a section is, and a click moves the viewer', async () => {
    const w = await open()
    expect(w.find('[data-level1]').exists()).toBe(false)
    expect(w.text()).toContain('reading…') // a Deck the server has not read yet
    expect(w.findComponent(viewer).exists()).toBe(false)

    await w.find('.decks > li .fold').trigger('click')
    const level1 = w.findAll('[data-level1] > li')
    expect(level1.map((l) => l.find('.link').text())).toEqual(['Intro', 'Wrap-up'])
    expect(w.find('[data-level2]').exists()).toBe(false)

    await level1[0]!.find('.fold').trigger('click')
    expect(w.findAll('[data-level2] .link').map((b) => b.text())).toEqual(['Why', 'Goals'])
    expect(level1[1]!.find('.fold').exists()).toBe(false) // nothing under it

    await w.findAll('[data-level2] .link')[1]!.trigger('click')
    expect(w.findComponent(viewer).props()).toMatchObject({ url: '/api/documents/a/file', page: 4 })
    await level1[1]!.find('.link').trigger('click')
    expect(w.findComponent(viewer).props('page')).toBe(9)
  })

  it('asks before sending, sends the key in the header only, marks the AI outline and resets to automatic', async () => {
    const w = await open('sk-secret')
    await w.find('.decks > li .fold').trigger('click')
    expect(w.find('[data-ai]').exists()).toBe(false)
    await w.find('[data-improve]').trigger('click')
    expect(w.text()).toContain('Send 12 pages')
    expect(calls.some((c) => c.url.endsWith('/outline/ai'))).toBe(false) // nothing sent before the confirmation

    await w.find('[data-send]').trigger('click')
    await flushPromises()
    const sent = calls.find((c) => c.url.endsWith('/outline/ai'))!
    expect((sent.init!.headers as Record<string, string>)['X-LLM-Key']).toBe('sk-secret')
    expect(String(sent.init!.body)).not.toContain('sk-secret')
    expect(w.find('[data-ai]').exists()).toBe(true)
    expect(w.find('[data-level1] .link').text()).toBe('Teil A')

    await w.find('[data-reset]').trigger('click')
    await flushPromises()
    expect(w.find('[data-ai]').exists()).toBe(false)
    expect(w.find('[data-level1] .link').text()).toBe('Intro')
  })

  it('explains the missing key and shows a readable error when the LLM fails', async () => {
    const none = await open()
    await none.find('.decks > li .fold').trigger('click')
    expect(none.find('[data-nokey]').text()).toContain('API key')
    expect(none.find('[data-improve]').attributes('disabled')).toBeDefined()

    const w = await open('k')
    vi.stubGlobal('fetch', async (url: string) =>
      url.endsWith('/outline/ai')
        ? new Response(JSON.stringify({ detail: { code: 'bad_key' } }), { status: 400 })
        : new Response(JSON.stringify(url === '/api/documents?subject=Numerik' ? docs : []), { status: 200 }),
    )
    await w.find('.decks > li .fold').trigger('click')
    await w.find('[data-improve]').trigger('click')
    await w.find('[data-send]').trigger('click')
    await flushPromises()
    expect(w.find('[role=alert]').text()).toBe('The API key was rejected.')
    expect(w.find('[data-ai]').exists()).toBe(false)
  })

  it('Explain this page starts a titled Chat in the Subject with exactly that page pinned and opens it', async () => {
    const w = await open()
    expect(w.find('[data-explain]').exists()).toBe(false)
    await w.find('.decks > li .fold').trigger('click')
    await w.find('[data-level1] .fold').trigger('click')
    await w.findAll('[data-level2] .link')[1]!.trigger('click') // Goals, page 4
    await w.find('[data-explain]').trigger('click')
    await flushPromises()
    const body = (url: string) => JSON.parse(String(calls.find((c) => c.url === url)!.init!.body))
    expect(body('/api/chats')).toEqual({ subject: 'Numerik' })
    expect(body('/api/chats/c1')).toEqual({ title: 'Chapter 1 · p. 4' })
    expect(body('/api/chats/c1/pinned')).toEqual({ pins: [{ document_id: 'a', page: 4 }] })
    expect(body('/api/chats/c1/messages')).toEqual({ text: 'Explain this page' }) // Ask AI needs a question
    expect(w.router.currentRoute.value).toMatchObject({ name: 'ask', query: { subject: 'Numerik', chat: 'c1' } })
  })
})
