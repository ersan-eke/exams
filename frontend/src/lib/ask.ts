export interface SlideResult {
  document_id: string
  deck: string
  label: string | null
  page: number
  title: string
  weak: boolean
}

export interface ExamResult {
  exam_id: string
  title: string
  subtask_key: string
  text: string
}

export interface SearchResults {
  slides: SlideResult[]
  exams: ExamResult[]
}

/** a failed ask: `code` is the server's (no_key, bad_key, rate_limited, ...) */
export class AskError extends Error {
  constructor(public code: string) {
    super(code)
  }
}

const messages: Record<string, string> = {
  no_key: 'Add your API key in Settings first.',
  bad_key: 'The API key was rejected.',
  rate_limited: 'Too many questions, try again in a minute.',
  no_credits: 'The provider says the account is out of credits.',
  refused: 'The model declined to answer.',
  no_pins: 'Pin at least one page first.',
  not_read: 'The Deck is still being read, try again in a moment.',
  unreadable: "Couldn't read the Deck's PDF.",
  llm_failed: 'The model gave no usable answer. Try again.',
  no_question: 'Send a message first.',
}
export const askErrorMessage = (e: unknown) =>
  (e instanceof AskError && messages[e.code]) || "Couldn't get an answer. Try again."

/** free local search of the Subject's Decks and past exam tasks: no key, no LLM */
export async function searchSubject(subject: string, query: string): Promise<SearchResults> {
  const res = await fetch('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ subject, query }),
  })
  if (!res.ok) throw new Error('search_failed')
  return res.json()
}
