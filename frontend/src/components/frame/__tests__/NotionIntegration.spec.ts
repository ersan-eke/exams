import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import NotionIntegration from '../NotionIntegration.vue'

const reply = (status: number, body?: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status })
const list = (enabled: boolean, connections: object[] = [], databaseUrl: string | null = null) =>
  reply(200, { slack: { enabled: true, connections: [] }, notion: { enabled, connections, databaseUrl } })
const conn = [{ id: 'a', workspace: 'Acme', connectedAt: 1 }]

function stub(handler: (url: string, init?: RequestInit) => Response) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => handler(url, init)))
}

describe('NotionIntegration', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    history.replaceState(null, '', '/')
  })

  it('renders nothing when disabled', async () => {
    stub(() => list(false))
    const w = mount(NotionIntegration)
    await flushPromises()
    expect(w.find('section').exists()).toBe(false)
  })

  it('offers Add to Notion with no connections', async () => {
    stub(() => list(true))
    const w = mount(NotionIntegration)
    await flushPromises()
    expect(w.get('a').attributes('href')).toBe('/api/integrations/notion/connect')
    expect(w.get('a').text()).toContain('Add to Notion')
  })

  it('lists the workspace and the database link, disconnect removes the row', async () => {
    stub((_, init) => (init?.method === 'DELETE' ? reply(204) : list(true, conn, 'https://notion.so/db')))
    const w = mount(NotionIntegration)
    await flushPromises()
    expect(w.text()).toContain('Acme')
    expect(w.find('a[href="https://notion.so/db"]').text()).toBe('Open flashcards')
    await w.get('button.disconnect').trigger('click')
    await flushPromises()
    expect(fetch).toHaveBeenCalledWith('/api/integrations/a', { method: 'DELETE' })
    expect(w.text()).not.toContain('Acme')
    expect(w.text()).not.toContain('Open flashcards')
  })

  it('shows the success notice and strips only its value', async () => {
    history.replaceState(null, '', '/?integration=notion&x=1')
    stub(() => list(true))
    const w = mount(NotionIntegration)
    await flushPromises()
    expect(w.get('[role=status]').text()).toBe('Notion connected.')
    expect(location.search).toBe('?x=1')
  })

  it('shows the failure notice', async () => {
    history.replaceState(null, '', '/?integration=notion_failed')
    stub(() => list(true))
    const w = mount(NotionIntegration)
    await flushPromises()
    expect(w.get('[role=status]').text()).toBe('Connecting Notion failed, try again.')
  })

  it('leaves the Slack value in the URL', async () => {
    history.replaceState(null, '', '/?integration=slack')
    stub(() => list(true))
    const w = mount(NotionIntegration)
    await flushPromises()
    expect(w.find('[role=status]').exists()).toBe(false)
    expect(location.search).toBe('?integration=slack')
  })
})
