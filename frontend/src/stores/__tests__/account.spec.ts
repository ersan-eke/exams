import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAccountStore } from '../account'
import { markAllDirty } from '@/lib/db'
import { sync } from '@/lib/sync'

vi.mock('@/lib/db', () => ({ markAllDirty: vi.fn(async () => {}) }))
vi.mock('@/lib/sync', () => ({ sync: vi.fn(async () => {}) }))

const ada = { id: 'u1', name: 'Ada', email: 'ada@example.com' }
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

describe('account store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('loads the signed-in user and the offered providers', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ user: ada, providers: ['github'] })))
    const account = useAccountStore()
    await account.load()
    expect(account.user).toEqual(ada)
    expect(account.providers).toEqual(['github'])
  })

  it('flags a failed sign-in from the callback redirect and drops the query', async () => {
    history.replaceState(null, '', '/?login=failed')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ user: null, providers: ['github'] })))
    const account = useAccountStore()
    await account.load()
    expect(account.loginFailed).toBe(true)
    expect(location.search).toBe('')
  })

  it('flags a denied sign-in separately and drops the query', async () => {
    history.replaceState(null, '', '/?login=denied')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ user: null, providers: ['github'] })))
    const account = useAccountStore()
    await account.load()
    expect(account.loginDenied).toBe(true)
    expect(account.loginFailed).toBe(false)
    expect(location.search).toBe('')
  })

  it('stays signed out when the server is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const account = useAccountStore()
    await account.load()
    expect(account.user).toBeNull()
    expect(account.providers).toEqual([])
  })

  it('signs out through the server', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(json({ user: ada, providers: [] }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetch)
    const account = useAccountStore()
    await account.load()
    await account.logout()
    expect(fetch).toHaveBeenLastCalledWith('/api/auth/logout', { method: 'POST' })
    expect(account.user).toBeNull()
  })

  it('first sign-in on a device marks everything dirty and clears the cursor', async () => {
    localStorage.setItem('sync-cursor', 'abc')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ user: ada, providers: [] })))
    await useAccountStore().load()
    expect(markAllDirty).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem('sync-cursor')).toBeNull()
    expect(localStorage.getItem('sync-user')).toBe('u1')
    expect(sync).toHaveBeenCalledTimes(1)
  })

  it('the same user again marks nothing', async () => {
    localStorage.setItem('sync-user', 'u1')
    localStorage.setItem('sync-cursor', 'abc')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ user: ada, providers: [] })))
    await useAccountStore().load()
    expect(markAllDirty).not.toHaveBeenCalled()
    expect(localStorage.getItem('sync-cursor')).toBe('abc')
    expect(sync).toHaveBeenCalledTimes(1)
  })

  it('does not sync while signed out', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ user: null, providers: [] })))
    await useAccountStore().load()
    expect(sync).not.toHaveBeenCalled()
    expect(markAllDirty).not.toHaveBeenCalled()
  })
})
