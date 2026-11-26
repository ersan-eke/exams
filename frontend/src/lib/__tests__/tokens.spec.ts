import { afterEach, describe, expect, it, vi } from 'vitest'
import { createToken, listTokens, revokeToken } from '../tokens'

const reply = (status: number, body?: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status })

describe('tokens api', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists', async () => {
    const f = vi.fn().mockResolvedValue(reply(200, [{ id: 'a', name: 'n', createdAt: 1, lastUsedAt: null }]))
    vi.stubGlobal('fetch', f)
    expect(await listTokens()).toHaveLength(1)
    expect(f).toHaveBeenCalledWith('/api/tokens')
  })

  it('creates with a JSON body', async () => {
    const f = vi.fn().mockResolvedValue(reply(201, { id: 'a', name: 'n', token: 'es_x' }))
    vi.stubGlobal('fetch', f)
    expect((await createToken('n')).token).toBe('es_x')
    const [url, init] = f.mock.calls[0]!
    expect(url).toBe('/api/tokens')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ name: 'n' })
  })

  it('revokes', async () => {
    const f = vi.fn().mockResolvedValue(reply(204))
    vi.stubGlobal('fetch', f)
    await revokeToken('a b')
    expect(f).toHaveBeenCalledWith('/api/tokens/a%20b', { method: 'DELETE' })
  })

  it('throws on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(401)))
    await expect(listTokens()).rejects.toThrow()
    await expect(createToken('n')).rejects.toThrow()
    await expect(revokeToken('a')).rejects.toThrow()
  })
})
