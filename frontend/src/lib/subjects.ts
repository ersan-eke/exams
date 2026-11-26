export interface Subject {
  id: string
  name: string
}

async function ok(res: Response): Promise<Response> {
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail?.code ?? `Request failed (${res.status})`)
  return res
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

/** every subject of the signed-in user: empty ones and ones only exams use included */
export async function listSubjects(): Promise<Subject[]> {
  return (await ok(await fetch('/api/subjects'))).json()
}

/** an existing name (any case) comes back as it is stored */
export async function createSubject(name: string): Promise<Subject> {
  return (await ok(await fetch('/api/subjects', json('POST', { name })))).json()
}

/** saves the subject's weak questions as `<name>.apkg`; rejects with the code `nothing_weak` when none scored below 60 % */
export async function downloadAnki(id: string, name: string): Promise<void> {
  const url = URL.createObjectURL(await (await ok(await fetch(`/api/subjects/${encodeURIComponent(id)}/anki`))).blob())
  const a = document.createElement('a')
  a.href = url
  a.download = `${name}.apkg`
  a.click()
  URL.revokeObjectURL(url)
}

/** exams and Decks follow; rejects with the code `name_taken` when another subject has the name */
export async function renameSubject(id: string, name: string): Promise<Subject> {
  return (await ok(await fetch(`/api/subjects/${encodeURIComponent(id)}`, json('PATCH', { name })))).json()
}

/** queues a Notion export of the subject's weak questions and resolves with the job id; rejects with the code `notion_not_connected` or `nothing_weak` */
export async function exportToNotion(id: string): Promise<string> {
  return (await (await ok(await fetch(`/api/subjects/${encodeURIComponent(id)}/notion`, { method: 'POST' }))).json()).jobId
}
