import { afterEach, describe, expect, it, vi } from 'vitest'
import { AskError, askErrorMessage } from '../ask'
import { askChat } from '../chats'
import { AlreadyUploadedError, lookupMaterial, materialRoute, uploadDocument } from '../documents'

const reply = (status: number, body: unknown) => vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }))
afterEach(() => vi.unstubAllGlobals())

describe('ask', () => {
  it('sends the key in the header only, never in the body', async () => {
    const f = reply(200, { id: 'c1', messages: [] })
    vi.stubGlobal('fetch', f)
    await askChat('c1', 'anthropic', 'claude-sonnet-5-5', ' sk-1 ')
    const [url, init] = f.mock.calls[0]!
    expect(url).toBe('/api/chats/c1/ask')
    expect(init.headers['X-LLM-Key']).toBe('sk-1')
    expect(init.body).not.toContain('sk-1')
  })

  it('turns the server code into a message', async () => {
    vi.stubGlobal('fetch', reply(400, { detail: { code: 'bad_key' } }))
    const e = await askChat('c1', 'anthropic', 'm', 'k').catch((x) => x)
    expect(e).toBeInstanceOf(AskError)
    expect(askErrorMessage(e)).toBe('The API key was rejected.')
    expect(askErrorMessage(new Error('x'))).toMatch(/Try again/)
  })
})

describe('documents', () => {
  it('builds viewer routes with the page', () => {
    expect(materialRoute('d1', 3)).toEqual({ name: 'material', params: { id: 'd1' }, query: { page: '3' } })
    expect(materialRoute('d1').query).toEqual({})
  })

  it('lookup posts subject and texts', async () => {
    const f = reply(200, [{ document_id: 'd', title: 'Ch 1', page: 2 }])
    vi.stubGlobal('fetch', f)
    expect(await lookupMaterial('Numerik', 'q', 's')).toHaveLength(1)
    expect(JSON.parse(f.mock.calls[0]![1].body)).toEqual({ subject: 'Numerik', text: 'q', solution_text: 's' })
  })

  it('a file the server already has resolves without waiting for a job', async () => {
    vi.stubGlobal('fetch', reply(200, { job_id: null, document_id: 'd9' }))
    expect(await uploadDocument(new File(['%PDF-'], 'a.pdf'), { subject: 'Numerik', kind: 'slides' })).toBe('d9')
  })

  it('surfaces the server error code', async () => {
    vi.stubGlobal('fetch', reply(400, { detail: { code: 'not_pdf' } }))
    await expect(uploadDocument(new File(['x'], 'a.pdf'), { subject: 'Numerik', kind: 'slides' })).rejects.toThrow('not_pdf')
  })

  it('a Deck job that fails rejects with its error code', async () => {
    class Source {
      onmessage: ((e: { data: string }) => void) | null = null
      close = vi.fn()
      constructor() {
        queueMicrotask(() => this.onmessage?.({ data: JSON.stringify({ status: 'failed', error_code: 'scanned' }) }))
      }
    }
    vi.stubGlobal('EventSource', Source)
    vi.stubGlobal('fetch', reply(202, { job_id: 'j1', document_id: 'd1' }))
    await expect(uploadDocument(new File(['%PDF-'], 'a.pdf'), { subject: 'A', kind: 'slides' })).rejects.toThrow('scanned')
  })

  it('a file already filed in another Subject rejects with where it lives', async () => {
    vi.stubGlobal('fetch', reply(409, { detail: { code: 'already_uploaded', document_id: 'd1', subject: 'Numerik' } }))
    const err = await uploadDocument(new File(['%PDF-'], 'a.pdf'), { subject: 'Algebra', kind: 'slides' }).catch((e) => e)
    expect(err).toBeInstanceOf(AlreadyUploadedError)
    expect(err).toMatchObject({ documentId: 'd1', subject: 'Numerik' })
  })
})
