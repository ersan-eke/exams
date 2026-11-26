import type { Provider } from '@/types/attempt'
import { waitForJob } from './api'
import { AskError } from './ask'

export type DocumentKind = 'slides' | 'script' | 'exercises'

/** an Outline entry: level 1 entries carry their level 2 entries */
export interface OutlineEntry {
  title: string
  page: number
  children?: OutlineEntry[]
}

export interface StudyDocument {
  id: string
  title: string
  kind: DocumentKind
  subject: string | null
  position: number
  /** 0 while the server is still reading it */
  page_count: number
  /** null until the server has read the Deck */
  outline: OutlineEntry[] | null
  outline_source: 'automatic' | 'ai' | null
}

/** replaces the Outline with the student's LLM's. The key goes in the header only, never in the body */
export async function improveOutline(id: string, provider: Provider, model: string, key: string): Promise<StudyDocument> {
  const res = await fetch(`/api/documents/${encodeURIComponent(id)}/outline/ai`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-LLM-Key': key.trim() },
    body: JSON.stringify({ provider, model }),
  })
  if (!res.ok) throw new AskError((await res.json().catch(() => null))?.detail?.code ?? 'server')
  return res.json()
}

export async function resetOutline(id: string): Promise<StudyDocument> {
  const res = await fetch(`/api/documents/${encodeURIComponent(id)}/outline/reset`, { method: 'POST' })
  if (!res.ok) throw new AskError((await res.json().catch(() => null))?.detail?.code ?? 'server')
  return res.json()
}

export interface MaterialLink {
  document_id: string
  title: string
  page: number | null
}

async function ok(res: Response): Promise<Response> {
  if (!res.ok) throw new Error(`Request failed (${res.status})`)
  return res
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

/** one subject's Decks in reading order, or (no subject) all of the user's Decks; subject null means unfiled */
export async function listDocuments(subject?: string): Promise<StudyDocument[]> {
  const q = subject ? `?subject=${encodeURIComponent(subject)}` : ''
  return (await ok(await fetch(`/api/documents${q}`))).json()
}

export async function getDocument(id: string): Promise<StudyDocument> {
  return (await ok(await fetch(`/api/documents/${encodeURIComponent(id)}`))).json()
}

/** the PDF is already a Deck of the user's, filed under `subject` (null: unfiled); it is not moved */
export class AlreadyUploadedError extends Error {
  constructor(
    readonly documentId: string,
    readonly subject: string | null,
  ) {
    super('already_uploaded')
  }
}

/** resolves once the server has read the PDF (pushed over SSE); a file the server already has resolves at once */
export async function uploadDocument(file: File, opts: { subject: string; kind: DocumentKind }): Promise<string> {
  const form = new FormData()
  form.append('file', file)
  form.append('kind', opts.kind)
  form.append('subject', opts.subject)
  const res = await fetch('/api/documents', { method: 'POST', body: form })
  if (!res.ok) {
    const detail = (await res.json().catch(() => null))?.detail
    if (detail?.code === 'already_uploaded') throw new AlreadyUploadedError(detail.document_id, detail.subject)
    throw new Error(detail?.code ?? `Request failed (${res.status})`)
  }
  const { job_id, document_id } = await res.json()
  if (job_id) await waitForJob(job_id)
  return document_id
}

export async function patchDocument(
  id: string,
  patch: { subject?: string | null; title?: string; position?: number; kind?: DocumentKind },
): Promise<StudyDocument> {
  return (await ok(await fetch(`/api/documents/${encodeURIComponent(id)}`, json('PATCH', patch)))).json()
}

export async function deleteDocument(id: string): Promise<void> {
  await ok(await fetch(`/api/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }))
}

/** where the viewer page for a Deck (and page) lives in the app; `terms` are the words to highlight on that page */
export const materialRoute = (id: string, page?: number | null, terms?: string) => ({
  name: 'material',
  params: { id },
  query: { ...(page ? { page: String(page) } : {}), ...(terms ? { terms } : {}) },
})

/** the pages of this subject's material that best match a subtask, at most two; [] when nothing fits */
export async function lookupMaterial(subject: string, text: string, solutionText = ''): Promise<MaterialLink[]> {
  return (await ok(await fetch('/api/materials/lookup', json('POST', { subject, text, solution_text: solutionText })))).json()
}
