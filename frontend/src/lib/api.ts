import type { ExamStructure } from '@/types/exam'

export type UploadErrorCode =
  | 'not_pdf'
  | 'scanned'
  | 'no_tasks'
  | 'unreadable'
  | 'network'
  | 'server'
  | 'sign_in'

export class UploadError extends Error {
  code: UploadErrorCode
  constructor(code: UploadErrorCode, message?: string) {
    super(message ?? code)
    this.name = 'UploadError'
    this.code = code
  }
}

const uploadMessages: Record<UploadErrorCode, string> = {
  not_pdf: "That file isn't a PDF.",
  scanned: "Scanned exams aren't supported yet.",
  no_tasks: 'No tasks found in this PDF.',
  unreadable: "This PDF couldn't be read.",
  network: "Couldn't reach the server. Try again.",
  server: "Couldn't reach the server. Try again.",
  sign_in: 'Sign in to upload exams.',
}

/** user-facing text for a failed upload */
export function uploadErrorMessage(e: unknown): string {
  return uploadMessages[e instanceof UploadError ? e.code : 'server']
}

export interface UploadResult {
  exam: ExamStructure
  images: Record<string, Blob>
  solution_images: Record<string, Blob> | null
  /** the server's id for the exam, used as the local id too */
  examId: string
}

export function decode(images: Record<string, string>): Record<string, Blob> {
  const out: Record<string, Blob> = {}
  for (const [name, b64] of Object.entries(images)) {
    const bin = atob(b64)
    const bytes = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
    out[name] = new Blob([bytes], { type: 'image/png' })
  }
  return out
}

const serverCodes: UploadErrorCode[] = ['not_pdf', 'scanned', 'no_tasks', 'unreadable']

function errorFor(code: unknown): UploadError {
  return new UploadError(
    serverCodes.includes(code as UploadErrorCode) ? (code as UploadErrorCode) : 'server',
  )
}

export interface JobEnd {
  status: 'done' | 'failed'
  error_code: string | null
  exam_id?: string
}

/** resolves with the job's final state once it is done or failed (pushed over SSE) */
export function followJob(jobId: string): Promise<JobEnd> {
  return new Promise((resolve, reject) => {
    const events = new EventSource(`/api/jobs/${jobId}/events`)
    events.onmessage = (e) => {
      const job = JSON.parse(e.data)
      if (job.status !== 'done' && job.status !== 'failed') return
      events.close()
      resolve(job)
    }
    // the browser retries dropped connections itself; CLOSED means it gave up (e.g. 404)
    // shortcut: while the server stays unreachable the browser keeps retrying and this never settles
    events.onerror = () => {
      if (events.readyState === EventSource.CLOSED) reject(new UploadError('server'))
    }
  })
}

/** resolves with the exam id once the server-side job is done */
export async function waitForJob(jobId: string): Promise<string> {
  const job = await followJob(jobId)
  if (job.status === 'failed') throw errorFor(job.error_code)
  return job.exam_id!
}

async function send(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init)
  } catch {
    throw new UploadError('network')
  }
}

/** POST queues the PDF; the result is fetched once the job reports done */
export async function uploadExam(file: File, role?: 'exam' | 'solution', subject?: string): Promise<UploadResult> {
  const form = new FormData()
  form.append('file', file)
  if (role) form.append('role', role)
  if (subject) form.append('subject', subject)

  const res = await send('/api/exams', { method: 'POST', body: form })
  if (res.status === 400) {
    const body = await res.json().catch(() => null)
    throw errorFor(body?.detail?.code)
  }
  if (res.status === 401) throw new UploadError('sign_in')
  if (!res.ok) throw new UploadError('server')

  const examId = await waitForJob((await res.json()).job_id)
  const exam = await send(`/api/exams/${examId}`)
  if (!exam.ok) throw new UploadError('server')
  const body = await exam.json()
  return {
    examId,
    exam: body.exam,
    images: decode(body.images),
    solution_images: body.solution_images ? decode(body.solution_images) : null,
  }
}
