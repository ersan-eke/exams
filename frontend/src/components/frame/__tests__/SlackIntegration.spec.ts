import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import SlackIntegration from '../SlackIntegration.vue'

const reply = (status: number, body?: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status })
const list = (enabled: boolean, connections: object[] = []) => reply(200, { slack: { enabled, connections } })
const conn = [{ id: 'a', workspace: 'Acme', connectedAt: 1 }]

function stub(handler: (url: string, init?: RequestInit) => Response) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => handler(url, init)))
}

describe('SlackIntegration', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    history.replaceState(null, '', '/')
  })

  it('renders nothing when disabled', async () => {
    stub(() => list(false))
    const w = mount(SlackIntegration)
    await flushPromises()
    expect(w.find('section').exists()).toBe(false)
  })

  it('offers Add to Slack with no connections', async () => {
    stub(() => list(true))
    const w = mount(SlackIntegration)
    await flushPromises()
    expect(w.get('a').attributes('href')).toBe('/api/integrations/slack/connect')
    expect(w.get('a').text()).toContain('Add to Slack')
  })

  it('shows workspace and hint, disconnect removes the row', async () => {
    stub((_, init) => (init?.method === 'DELETE' ? reply(204) : list(true, conn)))
    const w = mount(SlackIntegration)
    await flushPromises()
    expect(w.text()).toContain('Acme')
    expect(w.text()).toContain('Use /quiz <subject> in Slack')
    expect(w.get('a').text()).toContain('Add another workspace')
    await w.get('button.disconnect').trigger('click')
    await flushPromises()
    expect(w.text()).not.toContain('Acme')
  })

  it('a failed list shows an alert', async () => {
    stub(() => reply(500))
    const w = mount(SlackIntegration)
    await flushPromises()
    expect(w.get('[role=alert]').text()).not.toBe('')
  })

  it('a failed disconnect shows an alert and keeps the row', async () => {
    stub((_, init) => (init?.method === 'DELETE' ? reply(404) : list(true, conn)))
    const w = mount(SlackIntegration)
    await flushPromises()
    await w.get('button.disconnect').trigger('click')
    await flushPromises()
    expect(w.get('[role=alert]').text()).not.toBe('')
    expect(w.text()).toContain('Acme')
  })

  it('shows a notice for ?integration= and strips the query', async () => {
    history.replaceState(null, '', '/?integration=failed&x=1')
    stub(() => list(true))
    const w = mount(SlackIntegration)
    await flushPromises()
    expect(w.get('[role=status]').text()).toContain('failed')
    expect(location.search).toBe('?x=1')
  })
})
