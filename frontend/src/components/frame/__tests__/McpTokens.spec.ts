import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import McpTokens from '../McpTokens.vue'

const reply = (status: number, body?: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status })

const rows = [
  { id: 'a', name: 'laptop', createdAt: 1, lastUsedAt: null },
  { id: 'b', name: 'desktop', createdAt: 2, lastUsedAt: 1700000000000 },
]

function stub(handler: (url: string, init?: RequestInit) => Response) {
  const f = vi.fn(async (url: string, init?: RequestInit) => handler(url, init))
  vi.stubGlobal('fetch', f)
  return f
}

describe('McpTokens', () => {
  beforeEach(() => vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn() } }))
  afterEach(() => vi.unstubAllGlobals())

  it('lists tokens on mount', async () => {
    stub(() => reply(200, rows))
    const w = mount(McpTokens)
    await flushPromises()
    expect(w.text()).toContain('laptop')
    expect(w.text()).toContain('never')
    expect(w.text()).toContain('desktop')
  })

  it('create shows the token once with the command, and copies it', async () => {
    stub((_, init) =>
      init?.method === 'POST'
        ? reply(201, { id: 'c', name: 'new', token: 'es_secret' })
        : reply(200, rows),
    )
    const w = mount(McpTokens)
    await flushPromises()
    await w.get('input[type=text]').setValue('new')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect((w.get('input[readonly]').element as HTMLInputElement).value).toBe('es_secret')
    expect(w.get('code').text()).toContain('/mcp')
    expect(w.get('code').text()).toContain('Bearer es_secret')
    expect(w.text()).toContain('Shown once. Revoke it here if it leaks.')
    await w.get('button.copy').trigger('click')
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('es_secret')
  })

  it('revoke removes the row', async () => {
    stub((_, init) => (init?.method === 'DELETE' ? reply(204) : reply(200, rows)))
    const w = mount(McpTokens)
    await flushPromises()
    await w.findAll('button.revoke')[0]!.trigger('click')
    await flushPromises()
    expect(w.text()).not.toContain('laptop')
    expect(w.text()).toContain('desktop')
  })

  it('revoking the just-created token hides it', async () => {
    stub((_, init) =>
      init?.method === 'POST'
        ? reply(201, { id: 'a', name: 'laptop', token: 'es_secret' })
        : init?.method === 'DELETE'
          ? reply(204)
          : reply(200, rows),
    )
    const w = mount(McpTokens)
    await flushPromises()
    await w.get('input[type=text]').setValue('laptop')
    await w.get('form').trigger('submit')
    await flushPromises()
    await w.findAll('button.revoke')[1]!.trigger('click') // desktop: the fresh token stays
    await flushPromises()
    expect(w.find('input[readonly]').exists()).toBe(true)
    await w.findAll('button.revoke')[0]!.trigger('click')
    await flushPromises()
    expect(w.find('input[readonly]').exists()).toBe(false)
    expect(w.find('code').exists()).toBe(false)
  })

  it('a failed create hides the previous fresh token', async () => {
    let posts = 0
    stub((_, init) =>
      init?.method === 'POST'
        ? posts++
          ? reply(422)
          : reply(201, { id: 'c', name: 'new', token: 'es_secret' })
        : reply(200, rows),
    )
    const w = mount(McpTokens)
    await flushPromises()
    for (const n of ['new', 'again']) {
      await w.get('input[type=text]').setValue(n)
      await w.get('form').trigger('submit')
      await flushPromises()
    }
    expect(w.find('input[readonly]').exists()).toBe(false)
    expect(w.get('[role=alert]').text()).not.toBe('')
  })

  it('shows an inline error when create fails', async () => {
    stub((_, init) => (init?.method === 'POST' ? reply(422) : reply(200, rows)))
    const w = mount(McpTokens)
    await flushPromises()
    await w.get('input[type=text]').setValue('x')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.get('[role=alert]').text()).not.toBe('')
  })
})
