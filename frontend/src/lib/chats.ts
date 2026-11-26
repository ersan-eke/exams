import type { Provider } from '@/types/attempt'
import { AskError, searchSubject, type ExamResult, type SearchResults, type SlideResult } from './ask'

/** a slide result as stored in a Chat: what Search found, plus the query words found on it */
export type ChatSlide = SlideResult & { terms: string[] }

/** a page of a Deck: what is pinned and what an AI turn cites */
export interface PageRef {
  document_id: string
  page: number
}
export type AiCitation = PageRef & { label: string }

export type ChatMessage =
  | { role: 'user'; text: string }
  | { role: 'search'; slides: ChatSlide[]; exams: ExamResult[] }
  | { role: 'ai'; text: string; cited: AiCitation[]; provider: Provider; model: string }

export interface ChatSummary {
  id: string
  title: string
  updated_at: string
}

export interface Chat extends ChatSummary {
  messages: ChatMessage[]
  pinned: PageRef[]
}

async function call<T>(url: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await fetch(url, body === undefined ? { method } : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(`Request failed (${res.status})`)
  return res.status === 204 ? (undefined as T) : res.json()
}

export const listChats = (subject: string) => call<ChatSummary[]>(`/api/chats?subject=${encodeURIComponent(subject)}`)
export const createChat = (subject: string) => call<Chat>('/api/chats', 'POST', { subject })
export const getChat = (id: string) => call<Chat>(`/api/chats/${id}`)
export const renameChat = (id: string, title: string) => call<ChatSummary>(`/api/chats/${id}`, 'PATCH', { title })
export const deleteChat = (id: string) => call<void>(`/api/chats/${id}`, 'DELETE')
/** stores the message and runs the free Search; the returned Chat ends with the user message and its search turn */
export const postMessage = (id: string, text: string) => call<Chat>(`/api/chats/${id}/messages`, 'POST', { text })
/** replaces the pinned pages; the returned Chat holds the ones the server kept */
export const setPinned = (id: string, pins: PageRef[]) => call<Chat>(`/api/chats/${id}/pinned`, 'PUT', { pins })

/** the AI turn: answers from the pinned pages. The key goes in the header only, never in the body */
export async function askChat(id: string, provider: Provider, model: string, key: string): Promise<Chat> {
  const res = await fetch(`/api/chats/${id}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-LLM-Key': key.trim() },
    body: JSON.stringify({ provider, model }),
  })
  if (!res.ok) throw new AskError((await res.json().catch(() => null))?.detail?.code ?? 'server')
  return res.json()
}

/** dev only: the request the AI turn would send */
export const previewAsk = (id: string, provider: Provider, model: string) =>
  call<{ provider: string; model: string; system: string; prompt: string }>(`/api/chats/${id}/ask/preview`, 'POST', { provider, model })

export interface Hints {
  completions: string[]
  suggestion: { word: string; to: string } | null
}
/** typing help for the input: completions for the last word and a "Did you mean", from the Subject's titles */
export const searchHints = (subject: string, text: string) => call<Hints>(`/api/search/hints?subject=${encodeURIComponent(subject)}&text=${encodeURIComponent(text)}`)
/** what Search would find for the text typed so far; nothing is stored */
export const previewSearch = (subject: string, text: string): Promise<SearchResults> => searchSubject(subject, text)
