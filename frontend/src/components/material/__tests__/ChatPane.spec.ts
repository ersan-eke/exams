import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useSettingsStore } from '@/stores/settings'
import ChatPane from '../ChatPane.vue'

const viewer = { name: 'PdfViewer', props: ['url', 'page', 'terms'], template: '<div />' }
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const slides = [
  { document_id: 'd1', deck: 'Chapter 3', label: '3-21', page: 21, title: 'IPv4', weak: false, terms: ['ipv4'] },
  { document_id: 'd1', deck: 'Chapter 3', label: null, page: 2, title: 'Page 2', weak: true, terms: [] },
]
const exams = [{ exam_id: 'e1', title: 'Endterm 2024', subtask_key: '2a', text: 'Explain IPv4' }]
const saved = { id: 'c1', title: 'How is IPv4 built?', updated_at: 'now', pinned: [], messages: [{ role: 'user', text: 'How is IPv4 built?' }, { role: 'search', slides, exams }] }

const calls: [string, RequestInit | undefined][] = []
let ask: () => Response
let create: () => Response | Promise<Response> = () => json({ id: 'c1', title: 'New chat', updated_at: 'now', messages: [], pinned: [] })
let messages: () => Response | Promise<Response> = () => json(chatNow())
let pinned: { document_id: string; page: number }[] = []
const chatNow = () => ({ ...saved, pinned })
function fakeServer() {
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    calls.push([url, init])
    const method = init?.method ?? 'GET'
    if (url.startsWith('/api/search/hints')) {
      const t = new URL(url, 'http://x').searchParams.get('text')
      if (t === 'Größ') return json({ completions: ['Größe'], suggestion: null })
      if (t === 'Die Übertragunng ') return json({ completions: [], suggestion: { word: 'Übertragunng', to: 'Übertragung' } })
      return json(t === 'ipv' ? { completions: ['ipv4', 'ipv6'], suggestion: null } : { completions: [], suggestion: { word: 'adresing', to: 'adressierung' } })
    }
    if (url === '/api/search') return json({ slides, exams: [] })
    if (url === '/api/chats/c1/ask') return ask()
    if (url === '/api/chats/c1/pinned') return json({ ...saved, pinned: (pinned = JSON.parse(init!.body as string).pins) })
    if (url === '/api/chats/c1/ask/preview') return json({ provider: 'anthropic', model: 'm', system: 'SYS', prompt: 'PROMPT' })
    if (url === '/api/chats' && method === 'POST') return create()
    if (url.startsWith('/api/chats?')) return json([{ id: 'c1', title: saved.title, updated_at: 'now' }, { id: 'c2', title: 'Other chat', updated_at: 'now' }])
    if (url === '/api/chats/c1/messages') return messages()
    if (url === '/api/chats/c2' && method === 'GET') return json({ id: 'c2', title: 'Other chat', updated_at: 'now', pinned: [], messages: [] })
    if (url === '/api/chats/c1' && method === 'GET') return json(chatNow())
    if (url === '/api/chats/c1' && method === 'PATCH') return json({ id: 'c1', title: JSON.parse(init!.body as string).title, updated_at: 'now' })
    if (url === '/api/chats/c1' && method === 'DELETE') return new Response(null, { status: 204 })
    return json({}, 404)
  })
}

let mounted: { unmount: () => void } | null = null
afterEach(() => mounted?.unmount())
async function setup(key = 'sk-1', chatId?: string) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsStore().keys.anthropic = key
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/exams/:examId/view', name: 'exam-view', component: { template: '<div />' } }] })
  const w = mount(ChatPane, { props: { subject: 'Numerik', chatId }, attachTo: document.body, global: { plugins: [pinia, router], stubs: { PdfViewer: viewer } } })
  await flushPromises()
  mounted = w
  return w
}
async function send(w: Awaited<ReturnType<typeof setup>>, text: string) {
  await w.find('textarea').setValue(text)
  await w.find('form').trigger('submit')
  await flushPromises()
}

describe('ChatPane', () => {
  beforeEach(() => {
    calls.length = 0
    pinned = []
    messages = () => json(chatNow())
    create = () => json({ id: 'c1', title: 'New chat', updated_at: 'now', messages: [], pinned: [] })
    ask = () => json({ ...chatNow(), messages: [...saved.messages, { role: 'ai', text: 'Because.', cited: [{ document_id: 'd1', page: 2, label: 'Chapter 3 · p. 2' }], provider: 'anthropic', model: 'm' }] })
    fakeServer()
  })

  it('lists the Subject\'s Chats and restores a conversation when one is opened', async () => {
    const w = await setup('')
    expect(calls[0]![0]).toBe('/api/chats?subject=Numerik')
    await w.find('aside li button').trigger('click')
    await flushPromises()
    expect(w.find('.user').text()).toBe('How is IPv4 built?')
    expect(w.findAll('[data-found] .slides li')[0]!.find('.link').text()).toBe('Chapter 3 · 3-21 · IPv4')
  })

  it('shows the Chat clicked last even when an earlier one answers later', async () => {
    const w = await setup('')
    const real = globalThis.fetch
    const held: Record<string, () => void> = {}
    vi.stubGlobal('fetch', (url: string, init?: RequestInit) =>
      /^\/api\/chats\/c[12]$/.test(url) && (init?.method ?? 'GET') === 'GET'
        ? new Promise((res) => (held[url] = () => res(real(url, init))))
        : real(url, init),
    )
    const [a, b] = w.findAll('aside li button')
    await a!.trigger('click')
    await b!.trigger('click')
    held['/api/chats/c2']!()
    await flushPromises()
    held['/api/chats/c1']!()
    await flushPromises()
    expect(w.find('.user').exists()).toBe(false) // c2 is empty; c1 would show its question
  })

  it('opens the Chat it is given, with its pinned pages', async () => {
    pinned = [{ document_id: 'd1', page: 2 }]
    const w = await setup('sk-1', 'c1')
    expect(w.find('.user').text()).toBe('How is IPv4 built?')
    expect(w.text()).toContain('Ask AI about these 1 page')
  })

  it('stores a message, shows its search turn and opens a result in the viewer without leaving', async () => {
    const w = await setup('')
    await send(w, 'How is IPv4 built?')
    const post = calls.find(([u]) => u === '/api/chats/c1/messages')!
    expect(JSON.parse(post[1]!.body as string)).toEqual({ text: 'How is IPv4 built?' })
    const items = w.findAll('[data-found] .slides li')
    expect(items[1]!.text()).toContain('weak match')
    expect(w.find('[data-found] details').text()).toContain('Endterm 2024, task 2a')
    expect(calls.some(([u]) => u.endsWith('/ask'))).toBe(false)
    expect(w.text()).toContain('Add your API key')
    expect(w.findComponent(viewer).exists()).toBe(false)
    await items[0]!.find('button').trigger('click')
    expect(w.findComponent(viewer).props()).toEqual({ url: '/api/documents/d1/file', page: 21, terms: 'ipv4' })
    await items[1]!.find('button').trigger('click')
    expect(w.findComponent(viewer).props('page')).toBe(2)
  })

  it('pins pages, counts them on the Ask AI button and shows the cited page of the answer', async () => {
    const w = await setup()
    await w.find('aside li button').trigger('click')
    await flushPromises()
    const btn = () => w.find('[data-ask-ai]')
    expect(btn().attributes('disabled')).toBeDefined()
    await w.findAll('[data-found] .slides li')[1]!.find('.pin').trigger('click')
    await flushPromises()
    expect(JSON.parse(calls.find(([u]) => u.endsWith('/pinned'))![1]!.body as string)).toEqual({ pins: [{ document_id: 'd1', page: 2 }] })
    expect(btn().text()).toBe('Ask AI about these 1 page')
    await btn().trigger('click')
    await flushPromises()
    const post = calls.find(([u]) => u === '/api/chats/c1/ask')![1]!
    expect((post.headers as Record<string, string>)['X-LLM-Key']).toBe('sk-1')
    expect(w.find('[data-answer]').text()).toContain('Because.')
    await w.find('[data-answer] button').trigger('click')
    expect(w.findComponent(viewer).props('page')).toBe(2)
    await w.findAll('.pin')[1]!.trigger('click') // unpin
    await flushPromises()
    expect(btn().attributes('disabled')).toBeDefined()
  })

  it('cannot ask the AI without a key', async () => {
    pinned = [{ document_id: 'd1', page: 2 }]
    const w = await setup('')
    await w.find('aside li button').trigger('click')
    await flushPromises()
    expect(w.find('[data-ask-ai]').attributes('disabled')).toBeDefined()
  })

  it('shows a readable error', async () => {
    pinned = [{ document_id: 'd1', page: 2 }]
    ask = () => json({ detail: { code: 'rate_limited' } }, 429)
    const w = await setup()
    await w.find('aside li button').trigger('click')
    await flushPromises()
    await w.find('[data-ask-ai]').trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toContain('Too many questions')
  })

  it('shows the request the model would get in dev builds', async () => {
    pinned = [{ document_id: 'd1', page: 2 }]
    const w = await setup()
    await w.find('aside li button').trigger('click')
    await flushPromises()
    await w.find('[data-request-preview]').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('PROMPT')
  })

  it('renames and deletes the open Chat', async () => {
    vi.stubGlobal('confirm', () => true)
    const w = await setup('')
    await w.find('aside li button').trigger('click')
    await flushPromises()
    const title = w.find('input[aria-label="Chat title"]')
    await title.setValue('Netze')
    await title.trigger('change')
    await flushPromises()
    expect(JSON.parse(calls.find(([, i]) => i?.method === 'PATCH')![1]!.body as string)).toEqual({ title: 'Netze' })
    await w.find('.head button').trigger('click')
    await flushPromises()
    expect(calls.some(([u, i]) => u === '/api/chats/c1' && i?.method === 'DELETE')).toBe(true)
    expect(w.find('.head').exists()).toBe(false)
  })

  it('completes and corrects words with umlauts', async () => {
    vi.useFakeTimers()
    try {
      const w = await setup('')
      const input = w.find('textarea')
      await input.setValue('Größ')
      await vi.advanceTimersByTimeAsync(301)
      await flushPromises()
      await w.find('[data-completions] button').trigger('click')
      expect((input.element as HTMLTextAreaElement).value).toBe('Größe ')
      await input.setValue('Die Übertragunng ')
      await vi.advanceTimersByTimeAsync(301)
      await flushPromises()
      await w.find('[data-suggestion] button').trigger('click')
      expect((input.element as HTMLTextAreaElement).value).toBe('Die Übertragung ')
    } finally {
      vi.useRealTimers()
    }
  })

  describe('a reply lands in the Chat it was sent from', () => {
    async function sendThenSwitch(reply: () => Response) {
      let release!: () => void
      messages = () => new Promise<Response>((done) => (release = () => done(reply())))
      const w = await setup('', 'c1')
      const input = w.find('textarea')
      await input.setValue('How is IPv4 built?')
      await w.find('form').trigger('submit')
      await flushPromises()
      await w.findAll('aside li button')[1]!.trigger('click') // open Chat B while A's search runs
      await flushPromises()
      await input.setValue('my draft')
      const listCalls = calls.filter(([u]) => u.startsWith('/api/chats?')).length
      release()
      await flushPromises()
      return { w, input, listCalls }
    }

    it('leaves the open Chat and its draft alone, and refreshes the list', async () => {
      const { w, input, listCalls } = await sendThenSwitch(() => json(chatNow()))
      expect(w.find('.head input').element).toHaveProperty('value', 'Other chat')
      expect((input.element as HTMLTextAreaElement).value).toBe('my draft')
      expect(calls.filter(([u]) => u.startsWith('/api/chats?')).length).toBeGreaterThan(listCalls)
    })

    it('does not close the open Chat when the first message of a new one is still creating it', async () => {
      let release!: () => void
      create = () => new Promise<Response>((done) => (release = () => done(json({ id: 'c1', title: 'New chat', updated_at: 'now', messages: [], pinned: [] }))))
      const w = await setup('')
      await w.find('textarea').setValue('How is IPv4 built?')
      await w.find('form').trigger('submit')
      await flushPromises()
      await w.findAll('aside li button')[1]!.trigger('click')
      await flushPromises()
      release()
      await flushPromises()
      expect(w.find('.head input').element).toHaveProperty('value', 'Other chat')
    })

    it('shows no error of a failed send in another Chat', async () => {
      const { w } = await sendThenSwitch(() => json({}, 500))
      expect(w.find('[role=alert]').exists()).toBe(false)
    })
  })

  it('debounces typing help, applies a completion or a correction and stores nothing', async () => {
    vi.useFakeTimers()
    try {
      const w = await setup('')
      const input = w.find('textarea')
      await input.setValue('i')
      await input.setValue('ipv')
      await vi.advanceTimersByTimeAsync(299)
      expect(calls.some(([u]) => u.startsWith('/api/search'))).toBe(false)
      await vi.advanceTimersByTimeAsync(2)
      await flushPromises()
      expect(calls.filter(([u]) => u.startsWith('/api/search/hints'))).toHaveLength(1)
      expect(w.find('[data-live]').text()).toContain('Chapter 3 · 3-21 · IPv4')
      await w.find('[data-completions] button').trigger('click')
      expect((input.element as HTMLTextAreaElement).value).toBe('ipv4 ')
      await input.setValue('adresing ')
      await vi.advanceTimersByTimeAsync(301)
      await flushPromises()
      expect(w.find('[data-suggestion]').text()).toBe('Did you mean adressierung?')
      await w.find('[data-suggestion] button').trigger('click')
      expect((input.element as HTMLTextAreaElement).value).toBe('adressierung ')
      expect(calls.some(([u]) => u.includes('/messages'))).toBe(false)
      await input.setValue('')
      expect(w.find('[data-live]').exists()).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })
})
