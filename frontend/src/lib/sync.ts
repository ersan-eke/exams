import { ref } from 'vue'
import type { Attempt, StoredExam } from '@/types/attempt'
import { decode } from './api'
import { blobBase64 } from './grading'
import {
  clearDirty, dirtyIds, getAttempt, getExam, getImage, imageNames, onLocalEdit, putImages, storeRemoteAttempt,
  storeRemoteExam, type ImageVariant, type SyncKind,
} from './db'

/** bumped after a pull that wrote something; stores watch it and reload */
export const pulled = ref(0)
/** ids the last pull wrote */
export const lastPulled: { exams: string[]; attempts: string[] } = { exams: [], attempts: [] }

const CURSOR = 'sync-cursor'

type AttemptWire = Omit<Attempt, 'view'>

interface ExamMeta {
  id: string
  title: string
  hasInk: boolean
  hidden: boolean
  subject: string | null
  pointOverrides: StoredExam['pointOverrides'] | null
  rubrics: StoredExam['rubrics'] | null
  solutionFor: string | null
  fingerprint: string | null
  createdAt: number
  editedAt: number
}

export function toWire(a: Attempt): AttemptWire {
  const { view: _view, ...rest } = a
  return { ...rest, editedAt: a.editedAt ?? 0 }
}

function toMeta(e: StoredExam): ExamMeta {
  return {
    id: e.id, title: e.title, hasInk: e.hasInk, hidden: e.hidden ?? false, subject: e.subject ?? null,
    pointOverrides: e.pointOverrides ?? null, rubrics: e.rubrics ?? null, solutionFor: e.solutionFor ?? null,
    fingerprint: e.fingerprint ?? null, createdAt: e.createdAt, editedAt: e.editedAt ?? 0,
  }
}

/** the server sends null for unset optional fields; the client leaves them undefined */
const fromMeta = (m: ExamMeta): Omit<StoredExam, 'structure'> => ({
  id: m.id, title: m.title, hasInk: m.hasInk, hidden: m.hidden, subject: m.subject ?? undefined,
  pointOverrides: m.pointOverrides ?? undefined, rubrics: m.rubrics ?? undefined,
  solutionFor: m.solutionFor ?? undefined, fingerprint: m.fingerprint ?? undefined,
  createdAt: m.createdAt, editedAt: m.editedAt,
})

/** ends the run; whatever is still dirty goes next time */
class Stop extends Error {}

async function call(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init)
  } catch {
    throw new Stop() // offline
  }
}

const put = (url: string, body: object) =>
  call(url, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

const code409 = async (res: Response) =>
  res.status === 409 ? (await res.json().catch(() => null))?.detail?.code : undefined

/** clears the dirty flag unless the record was edited again meanwhile (that edit still has to go) */
async function clearIfUnchanged(kind: SyncKind, id: string, editedAt: number) {
  const now = await (kind === 'exams' ? getExam(id) : getAttempt(id))
  if ((now?.editedAt ?? 0) === editedAt) clearDirty(kind, id)
}

const rejected = (res: Response) => res.status === 413 || res.status === 422

/** 2xx/413/422 take the record out of the outbox; 401/5xx end the run; other errors keep it for next time */
async function settle(kind: SyncKind, id: string, sentEditedAt: number, res: Response) {
  if (rejected(res)) {
    console.warn(`sync: server rejected ${kind} ${id} (${res.status}), keeping it local-only`)
  } else if (res.status === 401 || res.status >= 500) {
    throw new Stop()
  } else if (!res.ok) {
    // e.g. 404 (another account's id): ending the run here would block every later push and the pull
    console.warn(`sync: ${kind} ${id} failed (${res.status}), will retry`)
    return
  }
  await clearIfUnchanged(kind, id, sentEditedAt)
}

async function crops(examId: string, variant: ImageVariant): Promise<Record<string, string>> {
  const out: Record<string, string> = {}
  for (const name of await imageNames(examId, variant)) {
    const blob = await getImage(examId, variant, name)
    if (blob) out[name] = await blobBase64(blob)
  }
  return out
}

/** exams the server rejected in this run, so an attempt on them doesn't upload them again */
const rejectedExams = new Set<string>()

/** true when the server rejected the exam (413/422), so it stays local-only */
async function pushExam(id: string): Promise<boolean> {
  if (rejectedExams.has(id)) return true
  const e = await getExam(id)
  if (!e) {
    clearDirty('exams', id) // deleted locally
    return false
  }
  const meta = toMeta(e)
  const url = `/api/exams/${encodeURIComponent(id)}`
  let res = await put(url, meta)
  if ((await code409(res)) === 'need_content') {
    res = await put(url, {
      ...meta, structure: e.structure, images: await crops(id, 'blank'),
      ...(e.hasInk ? { solutionImages: await crops(id, 'ink') } : {}),
    })
  }
  await settle('exams', id, meta.editedAt, res)
  if (rejected(res)) rejectedExams.add(id)
  return rejected(res)
}

async function pushAttempt(id: string) {
  const a = await getAttempt(id)
  if (!a) return clearDirty('attempts', id)
  if (a.status === 'running') return // the server only takes finished attempts
  const wire = toWire(a)
  const url = `/api/attempts/${encodeURIComponent(id)}`
  let res = await put(url, wire)
  if ((await code409(res)) === 'need_exam') {
    const local = (await pushExam(a.examId)) || (!!a.solutionExamId && (await pushExam(a.solutionExamId)))
    if (local) {
      // the server will never have its exam, so asking again would re-upload it on every run
      console.warn(`sync: attempt ${id}'s exam is local-only, keeping the attempt local-only too`)
      return clearDirty('attempts', id)
    }
    res = await put(url, wire)
  }
  await settle('attempts', id, wire.editedAt!, res)
}

/** a dropped or truncated body counts as a network failure */
const json = (res: Response) => res.json().catch(() => { throw new Stop() })

/** structure + crops of an exam not stored here; images first, record last, so a half-fetched exam never shows */
async function fetchExam(m: ExamMeta) {
  const got = await call(`/api/exams/${encodeURIComponent(m.id)}`)
  if (!got.ok) throw new Error(`status ${got.status}`)
  const c = await json(got)
  await putImages(m.id, 'blank', decode(c.images))
  if (c.solution_images) await putImages(m.id, 'ink', decode(c.solution_images))
  await storeRemoteExam({ ...fromMeta(m), structure: c.exam })
}

interface Page {
  cursor: string
  more: boolean
  after: string | null
  pageSince: string | null
  exams: ExamMeta[]
  attempts: AttemptWire[]
}

async function pull() {
  const since = localStorage.getItem(CURSOR)
  const res = await call(since ? `/api/sync?since=${encodeURIComponent(since)}` : '/api/sync')
  if (!res.ok) throw new Stop()
  let body: Page = await json(res)
  const cursor = body.cursor // the first page's: whatever changes while we page through is fetched again next time
  const wrote = { exams: [] as string[], attempts: [] as string[] }
  let complete = true
  for (;;) {
    complete = (await apply(body, wrote)) && complete
    if (!body.more) break
    const next = await call(`/api/sync?since=${encodeURIComponent(body.pageSince!)}&after=${body.after}`)
    if (!next.ok) throw new Stop()
    body = await json(next)
  }
  // shortcut: an incomplete or failed pull keeps the old cursor, so everything is fetched again next time
  if (complete) localStorage.setItem(CURSOR, cursor)
  if (wrote.exams.length || wrote.attempts.length) {
    Object.assign(lastPulled, wrote)
    pulled.value++
  }
}

/** stores one page; false when an exam could not be fetched */
async function apply(body: Page, wrote: { exams: string[]; attempts: string[] }): Promise<boolean> {
  let complete = true

  // shortcut: read-compare-write is not one IDB transaction, so a local edit landing between getExam/getAttempt
  // and storeRemote* is overwritten by the remote one; do it in one readwrite transaction if that shows up
  for (const m of body.exams) {
    const local = await getExam(m.id)
    if (local && (local.editedAt ?? 0) >= m.editedAt) continue
    if (local) {
      await storeRemoteExam({ ...local, ...fromMeta(m) })
    } else {
      try {
        await fetchExam(m)
      } catch (e) {
        // skip it so one broken exam can't block every later pull; the kept cursor retries it next time
        console.warn(`sync: couldn't fetch exam ${m.id}, will retry`, e)
        complete = false
        continue
      }
    }
    await clearIfUnchanged('exams', m.id, m.editedAt)
    wrote.exams.push(m.id)
  }
  for (const w of body.attempts) {
    const local = await getAttempt(w.id)
    if (local && (local.editedAt ?? 0) >= (w.editedAt ?? 0)) continue
    await storeRemoteAttempt(w) // keeps our device-local view
    await clearIfUnchanged('attempts', w.id, w.editedAt ?? 0)
    wrote.attempts.push(w.id)
  }

  return complete
}

async function run() {
  rejectedExams.clear()
  try {
    for (const id of dirtyIds('exams')) await pushExam(id)
    for (const id of dirtyIds('attempts')) await pushAttempt(id)
    await pull()
  } catch (e) {
    if (!(e instanceof Stop)) throw e
  }
}

let running: Promise<void> | null = null
let again = false

/** push the outbox, then pull; a call during a run makes it run once more */
export function sync(): Promise<void> {
  if (running) {
    again = true
    return running
  }
  running = (async () => {
    try {
      do {
        again = false
        await run()
      } while (again)
    } finally {
      running = null
    }
  })()
  return running
}

const DEBOUNCE_MS = 2000
let started = false

/** sync 2 s after the last local edit and when the tab comes back; both only while signed in */
export function startSync(isSignedIn: () => boolean): void {
  if (started) return
  started = true
  let timer: ReturnType<typeof setTimeout> | undefined
  onLocalEdit(() => {
    clearTimeout(timer)
    timer = setTimeout(() => isSignedIn() && void sync(), DEBOUNCE_MS)
  })
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && isSignedIn()) void sync()
  })
}
