import { afterEach, describe, expect, it, vi } from 'vitest'
import { followJob, UploadError, uploadErrorMessage, uploadExam } from '../api'

/** jsdom has no EventSource; this one replays the given job states as SSE messages */
function stubEvents(...states: object[]) {
  const opened: string[] = []
  class FakeEventSource {
    static CLOSED = 2
    readyState = 1
    onmessage: ((e: { data: string }) => void) | null = null
    onerror: (() => void) | null = null
    constructor(url: string) {
      opened.push(url)
      setTimeout(() => states.forEach((s) => this.onmessage?.({ data: JSON.stringify(s) })))
    }
    close() {
      this.readyState = FakeEventSource.CLOSED
    }
  }
  vi.stubGlobal('EventSource', FakeEventSource)
  return opened
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

describe('uploadExam', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('queues the PDF, waits for the job, then fetches and decodes the exam', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(json({ job_id: 'j1' }, 202))
      .mockResolvedValueOnce(
        json({ exam: { tasks: [] }, images: { 'a.png': btoa('png') }, solution_images: null }),
      )
    vi.stubGlobal('fetch', fetch)
    const opened = stubEvents(
      { status: 'running', stage: 'extract' },
      { status: 'done', exam_id: 'e1' },
    )

    const res = await uploadExam(new File(['%PDF-'], 'a.pdf'))

    expect(opened).toEqual(['/api/jobs/j1/events'])
    expect(fetch.mock.calls[1]?.[0]).toBe('/api/exams/e1')
    expect(res.exam).toEqual({ tasks: [] })
    expect(res.images['a.png']).toBeInstanceOf(Blob)
    expect(res.solution_images).toBeNull()
    expect(res.examId).toBe('e1')
  })

  it('posts the subject as a form field when given', async () => {
    const fetch = vi.fn().mockResolvedValue(json({ detail: { code: 'x' } }, 400))
    vi.stubGlobal('fetch', fetch)
    await uploadExam(new File(['%PDF-'], 'a.pdf'), undefined, 'Analysis 1').catch(() => null)
    expect((fetch.mock.calls[0]?.[1].body as FormData).get('subject')).toBe('Analysis 1')
  })

  it('maps a failed job to its code and message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ job_id: 'j1' }, 202)))
    stubEvents({ status: 'failed', error_code: 'unreadable' })
    const err = await uploadExam(new File(['%PDF-'], 'a.pdf')).catch((e) => e)
    expect(err).toBeInstanceOf(UploadError)
    expect(err.code).toBe('unreadable')
    expect(uploadErrorMessage(err)).toBe("This PDF couldn't be read.")
  })

  it('maps a 400 not_pdf without waiting for a job', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ detail: { code: 'not_pdf' } }, 400)))
    const opened = stubEvents()
    const err = await uploadExam(new File(['x'], 'a.txt')).catch((e) => e)
    expect(err.code).toBe('not_pdf')
    expect(opened).toEqual([])
  })

  it('maps a 401 to sign_in', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ detail: { code: 'sign_in' } }, 401)))
    const err = await uploadExam(new File(['%PDF-'], 'a.pdf')).catch((e) => e)
    expect(err).toBeInstanceOf(UploadError)
    expect(err.code).toBe('sign_in')
    expect(uploadErrorMessage(err)).toBe('Sign in to upload exams.')
  })

  it('treats unknown failure codes as a server error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ job_id: 'j1' }, 202)))
    stubEvents({ status: 'failed', error_code: 'server' })
    const err = await uploadExam(new File(['%PDF-'], 'a.pdf')).catch((e) => e)
    expect(err.code).toBe('server')
  })
})

describe('followJob', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('resolves on a failed event with its code, ignoring running ones', async () => {
    stubEvents({ status: 'running' }, { status: 'failed', error_code: 'notion_auth' })
    await expect(followJob('j1')).resolves.toMatchObject({ status: 'failed', error_code: 'notion_auth' })
  })
})
