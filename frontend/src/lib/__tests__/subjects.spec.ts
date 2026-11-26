import { afterEach, describe, expect, it, vi } from 'vitest'
import { downloadAnki, exportToNotion } from '../subjects'

describe('downloadAnki', () => {
  afterEach(() => vi.restoreAllMocks())

  it('rejects with the server code when nothing is weak', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: 'nothing_weak' } }), { status: 409 })))
    await expect(downloadAnki('s1', 'GRNVS')).rejects.toThrow('nothing_weak')
  })

  it('saves the deck as <name>.apkg and revokes the object URL', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('PK', { status: 200 })))
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe('GRNVS.apkg')
    })
    await downloadAnki('s1', 'GRNVS')
    expect(fetch).toHaveBeenCalledWith('/api/subjects/s1/anki')
    expect(click).toHaveBeenCalledOnce()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:x')
  })
})

describe('exportToNotion', () => {
  afterEach(() => vi.restoreAllMocks())

  it('POSTs and returns the job id', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ jobId: 'j1' }), { status: 202 })))
    await expect(exportToNotion('s1')).resolves.toBe('j1')
    expect(fetch).toHaveBeenCalledWith('/api/subjects/s1/notion', { method: 'POST' })
  })

  it('rejects with the code on a 409', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: 'notion_not_connected' } }), { status: 409 })))
    await expect(exportToNotion('s1')).rejects.toThrow('notion_not_connected')
  })
})
