<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import PdfViewer from '@/components/material/PdfViewer.vue'
import Modal from '@/components/ui/Modal.vue'
import { askErrorMessage, type SlideResult } from '@/lib/ask'
import { askChat, createChat, deleteChat, getChat, listChats, postMessage, previewAsk, previewSearch, searchHints, renameChat, setPinned, type Chat, type ChatSummary, type Hints } from '@/lib/chats'
import { useSettingsStore } from '@/stores/settings'

const props = defineProps<{ subject: string; chatId?: string }>()
const settings = useSettingsStore()
const key = computed(() => settings.keys[settings.provider])

const chats = ref<ChatSummary[]>([])
const chat = ref<Chat | null>(null)
const text = ref('')
const busy = ref(false)
const error = ref('')
const asking = ref(false)
const preview = ref<string | null>(null)
const DEV = import.meta.env.DEV
const viewing = ref<{ id: string; page: number; terms: string } | null>(null)

// typing help: debounced, the latest request wins; nothing here is saved
const DEBOUNCE_MS = 300
const hints = ref<Hints>({ completions: [], suggestion: null })
const live = ref<SlideResult[]>([])
let timer: ReturnType<typeof setTimeout> | undefined
let latest = 0
function clearHelp() {
  clearTimeout(timer)
  latest++
  hints.value = { completions: [], suggestion: null }
  live.value = []
}
watch(text, (t) => {
  clearTimeout(timer)
  if (!t.trim()) return clearHelp()
  const mine = ++latest
  timer = setTimeout(async () => {
    const [h, found] = await Promise.all([searchHints(props.subject, t).catch(() => null), previewSearch(props.subject, t).catch(() => null)])
    if (mine !== latest) return
    hints.value = h ?? { completions: [], suggestion: null }
    live.value = found?.slides ?? []
  }, DEBOUNCE_MS)
})
onBeforeUnmount(() => clearTimeout(timer))
// mirrors WORD in backend/app/rag/hints.py: change both
// words are Unicode letters/digits, hyphenated parts included ("Größe", "TCP-Handshake", "IPv6"); \w and \b would split at ä, ö, ü, ß
const W = '[\\p{L}\\p{N}]+(?:-[\\p{L}\\p{N}]+)*'
const complete = (word: string) => (text.value = text.value.replace(new RegExp(`${W}$`, 'u'), () => word) + ' ')
const correct = (s: { word: string; to: string }) => {
  const esc = s.word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  text.value = text.value.replace(new RegExp(`(?<![\\p{L}\\p{N}-])${esc}(?![\\p{L}\\p{N}-])`, 'u'), () => s.to)
}

async function refresh() {
  chats.value = await listChats(props.subject)
}
watch(
  () => props.subject,
  async () => {
    reset()
    clearHelp()
    chats.value = []
    await refresh().catch(() => (error.value = "Couldn't load the Chats."))
    if (props.chatId) await open(props.chatId) // e.g. "Explain this page" from the study page
  },
  { immediate: true },
)

watch(
  () => props.chatId,
  (id) => id && open(id),
)
let opening = 0
async function open(id: string) {
  const mine = ++opening
  const next = await getChat(id).catch(() => null)
  if (mine !== opening) return // another Chat was clicked meanwhile
  reset(next)
  if (!chat.value) error.value = "Couldn't open the Chat."
}
// the Chat is created with its first message, so "New chat" never leaves an empty one behind
const fresh = () => {
  opening++
  reset()
}
async function rename(e: Event) {
  const title = (e.target as HTMLInputElement).value.trim()
  if (chat.value && title && title !== chat.value.title) chat.value.title = (await renameChat(chat.value.id, title)).title
  await refresh()
}
async function remove() {
  if (!chat.value || !confirm(`Delete "${chat.value.title}"?`)) return
  await deleteChat(chat.value.id)
  opening++
  reset()
  await refresh()
}

async function submit() {
  const q = text.value.trim()
  if (!q) return
  busy.value = true
  error.value = ''
  try {
    const from = chat.value?.id
    const made = chat.value ?? (await createChat(props.subject))
    if (chat.value?.id === from) chat.value = made // not if the student opened another Chat meanwhile
    const at = made.id
    const stillOpen = () => chat.value?.id === at // the student may have opened another Chat meanwhile
    // the search is free and always runs; the AI only answers when asked about pinned pages
    await postMessage(at, q).then(
      (c) => stillOpen() && ((chat.value = c), (text.value = '')),
      () => stillOpen() && (error.value = "Couldn't search. Try again."),
    )
    await refresh()
  } catch {
    error.value = "Couldn't start the Chat. Try again."
  }
  busy.value = false
}

const pinned = computed(() => chat.value?.pinned ?? [])
const isPinned = (id: string, page: number) => pinned.value.some((p) => p.document_id === id && p.page === page)
const saving = ref(false) // one pin save at a time: each sends the whole list
async function pin(id: string, page: number) {
  if (!chat.value || saving.value) return
  saving.value = true
  const at = chat.value.id
  const next = isPinned(id, page) ? pinned.value.filter((p) => !(p.document_id === id && p.page === page)) : [...pinned.value, { document_id: id, page }]
  error.value = ''
  const saved = await setPinned(at, next).catch(() => ((error.value = "Couldn't save the pin."), null))
  if (saved && chat.value?.id === at) chat.value = saved
  saving.value = false
}
async function askAi() {
  if (!chat.value || !key.value) return
  asking.value = true
  error.value = ''
  const at = chat.value.id
  try {
    const next = await askChat(at, settings.provider, settings.models[settings.provider], key.value)
    if (chat.value?.id === at) chat.value = next // the student may have opened another Chat meanwhile
    await refresh()
  } catch (e) {
    error.value = askErrorMessage(e)
  }
  asking.value = false
}
async function showRequest() {
  if (!chat.value) return
  const r = await previewAsk(chat.value.id, settings.provider, settings.models[settings.provider]).catch(() => null)
  preview.value = r ? `${r.provider} · ${r.model}\n\n${r.system}\n\n${r.prompt}` : 'No request: the Chat needs a message and a pinned page, and the server needs DEV=1.'
}

function reset(next: Chat | null = null) {
  chat.value = next
  viewing.value = null
  error.value = ''
}
const show = (id: string, page: number | null, terms: string[] = []) => (viewing.value = { id, page: page ?? 1, terms: terms.join(' ') })
</script>

<template>
  <section class="chat">
    <aside>
      <button type="button" class="btn" @click="fresh">New chat</button>
      <ul>
        <li v-for="c in chats" :key="c.id">
          <button type="button" :class="{ on: chat?.id === c.id }" @click="open(c.id)">{{ c.title }}</button>
        </li>
      </ul>
    </aside>

    <div class="talk">
      <div v-if="chat" class="head">
        <input :value="chat.title" aria-label="Chat title" @change="rename" />
        <button type="button" @click="remove">Delete</button>
      </div>
      <p v-else class="note">Type below to start a Chat, or open one from the list.</p>

      <template v-for="(m, i) in chat?.messages ?? []" :key="i">
        <p v-if="m.role === 'user'" class="user">{{ m.text }}</p>
        <div v-else-if="m.role === 'search'" class="found" data-found>
          <ol v-if="m.slides.length" class="slides">
            <li v-for="s in m.slides" :key="`${s.document_id}-${s.label ?? s.page}`" :class="{ weak: s.weak }">
              <button type="button" class="link" @click="show(s.document_id, s.page, s.terms)">
                {{ s.deck }}<template v-if="s.label"> · {{ s.label }}</template> · {{ s.title }}
              </button>
              <button type="button" class="pin" :disabled="saving" :aria-pressed="isPinned(s.document_id, s.page)" @click="pin(s.document_id, s.page)">
                {{ isPinned(s.document_id, s.page) ? 'Unpin' : 'Pin' }}
              </button>
              <span v-if="s.weak" class="meta"> weak match</span>
            </li>
          </ol>
          <p v-else class="note">No matching slides in this Subject's Decks.</p>
          <details v-if="m.exams.length" class="exams">
            <summary>Past exam tasks ({{ m.exams.length }})</summary>
            <ul>
              <li v-for="e in m.exams" :key="`${e.exam_id}-${e.subtask_key}`">
                <RouterLink :to="{ name: 'exam-view', params: { examId: e.exam_id } }">{{ e.title }}, task {{ e.subtask_key }}</RouterLink>
                <span class="meta"> {{ e.text }}</span>
              </li>
            </ul>
          </details>
        </div>
        <div v-else-if="m.role === 'ai'" class="answer" data-answer>
          <p class="text">{{ m.text }}</p>
          <ul v-if="m.cited.length" class="cites">
            <li v-for="c in m.cited" :key="`${c.document_id}-${c.page}`">
              <button type="button" class="link" @click="show(c.document_id, c.page)">{{ c.label }}</button>
            </li>
          </ul>
        </div>
      </template>

      <div v-if="chat" class="ai">
        <button type="button" class="btn" data-ask-ai :disabled="asking || !pinned.length || !key" @click="askAi">
          {{ asking ? 'Asking…' : `Ask AI about these ${pinned.length} page${pinned.length === 1 ? '' : 's'}` }}
        </button>
        <button v-if="DEV" type="button" class="btn" data-request-preview :disabled="!pinned.length" @click="showRequest">What the model gets</button>
      </div>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <form class="question" @submit.prevent="submit">
        <textarea v-model="text" maxlength="1000" placeholder="Ask about this Subject's Decks and exams" />
        <p v-if="hints.suggestion" class="note" data-suggestion>
          Did you mean <button type="button" class="link" @click="correct(hints.suggestion)">{{ hints.suggestion.to }}</button>?
        </p>
        <ul v-if="hints.completions.length" class="cites" data-completions>
          <li v-for="w in hints.completions" :key="w"><button type="button" class="link" @click="complete(w)">{{ w }}</button></li>
        </ul>
        <ul v-if="live.length" class="live note" data-live>
          <li v-for="s in live" :key="`${s.document_id}-${s.label ?? s.page}`">{{ s.deck }}<template v-if="s.label"> · {{ s.label }}</template> · {{ s.title }}</li>
        </ul>
        <button type="submit" class="btn" :disabled="busy || !text.trim()">{{ busy ? 'Searching…' : 'Search' }}</button>
      </form>
      <p v-if="!key" class="note">Add your API key in Settings to ask the AI about pinned pages.</p>
    </div>

    <Modal :open="preview !== null" @close="preview = null">
      <pre class="request">{{ preview }}</pre>
    </Modal>

    <div v-if="viewing" class="viewer">
      <PdfViewer :url="`/api/documents/${encodeURIComponent(viewing.id)}/file`" :page="viewing.page" :terms="viewing.terms" @error="viewing = null" />
    </div>
  </section>
</template>

<style scoped>
.chat {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--s4);
  align-items: start;
}
.chat:not(:has(.viewer)) {
  grid-template-columns: 180px minmax(0, 1fr);
}
aside,
.talk {
  display: flex;
  flex-direction: column;
  gap: var(--s3);
}
aside ul {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s2);
}
aside li button {
  text-align: left;
  width: 100%;
}
aside li button.on {
  font-weight: 600;
}
.head {
  display: flex;
  gap: var(--s3);
}
.head input {
  flex: 1;
}
.user {
  font-weight: 500;
}
.note,
.meta {
  color: var(--mute);
}
.error {
  color: var(--over);
}
.question {
  display: flex;
  flex-direction: column;
  gap: var(--s2);
  align-items: flex-start;
}
.question textarea {
  width: 100%;
  field-sizing: content;
  min-height: 3lh;
  max-height: 12lh;
  resize: none;
}
.btn,
.head button {
  padding: 6px var(--s3);
  border: 1px solid var(--ink);
}
.btn:disabled {
  opacity: 0.4;
}
.link {
  text-align: left;
  text-decoration: underline;
}
.slides,
.exams ul,
.live,
.cites {
  list-style-position: inside;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s2);
}
.cites {
  list-style: none;
  flex-direction: row;
  flex-wrap: wrap;
}
.found,
.answer {
  display: flex;
  flex-direction: column;
  gap: var(--s3);
}
.answer {
  border: 1px solid var(--line);
  padding: var(--s3) var(--s4);
}
.text,
.request {
  white-space: pre-wrap;
}
.ai {
  display: flex;
  gap: var(--s3);
}
.pin {
  text-decoration: underline;
}
.pin[aria-pressed='true'] {
  font-weight: 600;
}
.viewer {
  position: sticky;
  top: var(--s4);
}
@media (max-width: 900px) {
  .chat,
  .chat:not(:has(.viewer)) {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
