import { openDB, type DBSchema, type IDBPDatabase } from 'idb'
import type { Answer, Attempt, StoredExam, ViewState } from '@/types/attempt'
import type { Task } from '@/types/exam'
import { migrateAnswer } from './answers'

const migrateAnswers = (r: Record<string, Answer> | null | undefined) =>
  r && Object.fromEntries(Object.entries(r).map(([id, x]) => [id, migrateAnswer(x)]))

/** bring attempts saved by older versions to the current shape */
function migrate(a: Attempt): Attempt {
  return { ...a, answers: migrateAnswers(a.answers)!, snapshot: migrateAnswers(a.snapshot) ?? null }
}

interface ExamenDB extends DBSchema {
  exams: { key: string; value: StoredExam }
  images: { key: string; value: Blob }
  attempts: { key: string; value: Attempt; indexes: { examId: string } }
}

export type ImageVariant = 'blank' | 'ink'

let dbPromise: Promise<IDBPDatabase<ExamenDB>> | null = null

function db() {
  dbPromise ??= openDB<ExamenDB>('examen', 1, {
    upgrade(d) {
      d.createObjectStore('exams', { keyPath: 'id' })
      d.createObjectStore('images')
      d.createObjectStore('attempts', { keyPath: 'id' }).createIndex('examId', 'examId')
    },
  })
  return dbPromise
}

const imageKey = (examId: string, variant: ImageVariant, name: string) =>
  `${examId}/${variant}/${name}`

export type SyncKind = 'exams' | 'attempts'

const dirtyKey = (kind: SyncKind) => `sync-dirty-${kind}`

export function dirtyIds(kind: SyncKind): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(dirtyKey(kind)) ?? '[]')
    return Array.isArray(v) ? v : []
  } catch {
    return []
  }
}

function saveDirty(kind: SyncKind, ids: string[]) {
  try {
    localStorage.setItem(dirtyKey(kind), JSON.stringify(ids))
  } catch {
    // shortcut: storage full or blocked, the edit is not queued for push; upgrade with a retry/notice
  }
}

export function markDirty(kind: SyncKind, id: string) {
  const ids = dirtyIds(kind)
  if (!ids.includes(id)) saveDirty(kind, [...ids, id])
}

export function clearDirty(kind: SyncKind, id: string) {
  saveDirty(kind, dirtyIds(kind).filter((x) => x !== id))
}

/** first sync on a device: everything stored locally counts as not yet pushed */
export async function markAllDirty(): Promise<void> {
  const d = await db()
  for (const id of await d.getAllKeys('exams')) markDirty('exams', id)
  for (const id of await d.getAllKeys('attempts')) markDirty('attempts', id)
}

let editListener: (() => void) | null = null
/** sync registers here, which keeps this file free of a sync.ts import */
export function onLocalEdit(fn: () => void): void {
  editListener = fn
}

/** same as stored, ignoring the edit time and the given device-local keys */
const sameAs = (a: object, b: object | undefined, skip: string[]) => {
  const strip = (r: object) =>
    JSON.stringify(Object.fromEntries(Object.entries(r).filter(([k]) => k !== 'editedAt' && !skip.includes(k))))
  return !!b && strip(a) === strip(b)
}

async function putStamped(kind: SyncKind, rec: { id: string }, skip: string[]) {
  const d = await db()
  const stored = (await d.get(kind, rec.id)) as { editedAt?: number } | undefined
  // shortcut: JSON.stringify key order can differ, which only causes a harmless extra push
  if (sameAs(rec, stored, skip)) {
    // unchanged apart from device-local keys: save those, keep the stored edit time
    await d.put(kind, { ...rec, editedAt: stored!.editedAt } as never)
    return
  }
  await d.put(kind, { ...rec, editedAt: Date.now() } as never)
  markDirty(kind, rec.id)
  editListener?.()
}

export async function putExam(e: StoredExam): Promise<void> {
  await putStamped('exams', e, [])
}

export async function storeRemoteExam(e: StoredExam): Promise<void> {
  await (await db()).put('exams', e)
}

/** the default view for a new attempt: first included task open */
export function emptyView(first?: Task): ViewState {
  return {
    shown: first?.subtasks[0] ? [first.subtasks[0].id] : [],
    folded: [],
    expandedTasks: first ? [first.id] : [],
    outlineCollapsed: false,
  }
}

export async function getExam(id: string): Promise<StoredExam | undefined> {
  return (await db()).get('exams', id)
}

export async function listExams(): Promise<StoredExam[]> {
  const all = await (await db()).getAll('exams')
  return all.sort((a, b) => b.createdAt - a.createdAt)
}

export async function putImages(
  examId: string,
  variant: ImageVariant,
  images: Record<string, Blob>,
): Promise<void> {
  const d = await db()
  const tx = d.transaction('images', 'readwrite')
  await Promise.all([
    ...Object.entries(images).map(([name, blob]) =>
      tx.store.put(blob, imageKey(examId, variant, name)),
    ),
    tx.done,
  ])
}

export async function getImage(
  examId: string,
  variant: ImageVariant,
  name: string,
): Promise<Blob | undefined> {
  return (await db()).get('images', imageKey(examId, variant, name))
}

/** names of the crops stored for an exam */
export async function imageNames(examId: string, variant: ImageVariant): Promise<string[]> {
  const prefix = imageKey(examId, variant, '')
  const keys = await (await db()).getAllKeys('images', IDBKeyRange.bound(prefix, prefix + '\uffff'))
  return keys.map((k) => k.slice(prefix.length))
}

export async function putAttempt(a: Attempt): Promise<void> {
  // a running attempt saves about once a second and is never pushed; the hand-in save stamps it
  if (a.status === 'running') await (await db()).put('attempts', a)
  else await putStamped('attempts', a, ['view'])
}

/** a pulled attempt: view is device-local, so keep ours if we have one */
export async function storeRemoteAttempt(a: Omit<Attempt, 'view'>): Promise<void> {
  const d = await db()
  const local = await d.get('attempts', a.id)
  await d.put('attempts', { ...a, view: local?.view ?? emptyView() })
}

export async function getAttempt(id: string): Promise<Attempt | undefined> {
  const a = await (await db()).get('attempts', id)
  return a && migrate(a)
}

export async function attemptsForExam(examId: string): Promise<Attempt[]> {
  return (await (await db()).getAllFromIndex('attempts', 'examId', examId)).map(migrate)
}

export async function listAttempts(): Promise<Attempt[]> {
  return (await (await db()).getAll('attempts')).map(migrate)
}

export async function runningAttempt(): Promise<Attempt | undefined> {
  const all = await (await db()).getAll('attempts')
  const running = all.find((a) => a.status === 'running')
  return running && migrate(running)
}
