import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { exam } from '@/lib/__tests__/fixtures'
import { useAccountStore } from '@/stores/account'
import { useSettingsStore } from '@/stores/settings'
import AskView from '../AskView.vue'

const lib = vi.hoisted(() => ({ catalog: vi.fn() }))
vi.mock('@/stores/library', () => ({ useLibraryStore: () => lib }))

const stub = { template: '<div />' }
const chapter = { id: 'd1', title: 'Chapter 3', kind: 'slides', subject: 'Numerik', position: 0, page_count: 12, outline: null, outline_source: null }
const subjects = [
  { id: 's1', name: 'Numerik' },
  { id: 's2', name: 'Empty' },
]
const okRename = (name: string) => ({ id: 's1', name })
let renamed: (name: string) => unknown = okRename
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

const calls: [string, RequestInit | undefined][] = []
function fakeServer() {
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    calls.push([url, init])
    if (url.startsWith('/api/chats')) return json([])
    if (url === '/api/subjects' && !init) return json(subjects)
    if (url === '/api/subjects') return json({ id: 's9', name: JSON.parse(init!.body as string).name })
    if (url.startsWith('/api/subjects/')) return json(renamed(JSON.parse(init!.body as string).name), renamed === okRename ? 200 : 409)
    if (init?.method === 'PATCH') return json({ ...chapter, ...JSON.parse(init.body as string) })
    if (url.startsWith('/api/documents')) return json([chapter, { ...chapter, id: 'd2', title: 'Loose', subject: null }])
    return json({}, 404)
  })
}

async function setup(key = 'sk-1') {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAccountStore().user = { id: 'u', name: null, email: null }
  useSettingsStore().keys.anthropic = key
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/ask', name: 'ask', component: AskView },
      { path: '/material/:id', name: 'material', component: stub },
      { path: '/study/:subject', name: 'study', component: stub },
      { path: '/exams/:examId/view', name: 'exam-view', component: stub },
    ],
  })
  router.push('/ask?subject=Numerik')
  await router.isReady()
  const w = mount(AskView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { w, router }
}

describe('AskView', () => {
  beforeEach(() => {
    calls.length = 0
    renamed = okRename
    lib.catalog.mockReset().mockResolvedValue({ exams: [{ id: 'e', title: 'Numerik 2024', structure: exam([]), createdAt: 0, hasInk: false }], attempts: [] })
    fakeServer()
  })

  it('shows a fold bar per Subject with Deck rows, an empty Subject and an Unfiled bar', async () => {
    const { w } = await setup()
    const bars = w.findAll('.fold')
    expect(bars.map((b) => b.find('.title').text().replace(/^[›⌄]/, ''))).toEqual(['Numerik', 'Empty', 'Unfiled'])
    expect(bars[0]!.text()).toContain('1 Deck')
    expect((w.find('input[aria-label="Deck title"]').element as HTMLInputElement).value).toBe('Chapter 3')
    expect(bars[0]!.find('a[href="/study/Numerik"]').text()).toBe('Study page')
    await bars[1]!.find('button.fold-bar').trigger('click')
    expect(bars[1]!.text()).toContain('No material yet')
    await bars[2]!.find('button.fold-bar').trigger('click')
    expect(w.text()).toContain('Loose')
    expect(w.text()).not.toMatch(/document|chapter/i)
  })

  it('changes a Deck’s kind from its row', async () => {
    const { w } = await setup()
    await w.find('select[aria-label="Deck kind"]').setValue('script')
    const patch = calls.find(([u, i]) => u === '/api/documents/d1' && i?.method === 'PATCH')!
    expect(JSON.parse(patch[1]!.body as string)).toEqual({ kind: 'script' })
  })

  it('creates a Subject when a new name is typed into the dropdown', async () => {
    const { w } = await setup()
    const input = w.find('label.subject input')
    await input.setValue('Algebra')
    await input.trigger('change')
    await flushPromises()
    const post = calls.find(([u, i]) => u === '/api/subjects' && i?.method === 'POST')!
    expect(JSON.parse(post[1]!.body as string)).toEqual({ name: 'Algebra' })
  })

  it('renames a Subject from its bar and reports a taken name', async () => {
    const { w } = await setup()
    const input = w.find('input[aria-label="Subject name"]')
    await input.setValue('Numerics')
    await input.trigger('change')
    await flushPromises()
    expect(calls.some(([u, i]) => u === '/api/subjects/s1' && i?.method === 'PATCH')).toBe(true)
    renamed = () => ({ detail: { code: 'name_taken' } })
    await input.setValue('Empty')
    await input.trigger('change')
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toContain('already a Subject')
  })

  it('assigns an Unfiled Deck through the Subject dropdown', async () => {
    const { w } = await setup()
    await w.findAll('button.fold-bar')[2]!.trigger('click')
    const input = w.find('.fold:last-of-type label.subject input')
    await input.setValue('Numerik')
    await input.trigger('change')
    await flushPromises()
    const patch = calls.find(([u, i]) => u === '/api/documents/d2' && i?.method === 'PATCH')!
    expect(JSON.parse(patch[1]!.body as string)).toEqual({ subject: 'Numerik' })
  })

  it('shows the Chat pane for the chosen Subject', async () => {
    const { w } = await setup()
    expect(w.findComponent({ name: 'ChatPane' }).props('subject')).toBe('Numerik')
  })
})
