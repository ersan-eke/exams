<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PdfViewer from '@/components/material/PdfViewer.vue'
import { askErrorMessage } from '@/lib/ask'
import { createChat, postMessage, renameChat, setPinned } from '@/lib/chats'
import { improveOutline, listDocuments, resetOutline, type OutlineEntry, type StudyDocument } from '@/lib/documents'
import { useSettingsStore } from '@/stores/settings'

const route = useRoute()
const router = useRouter()
const settings = useSettingsStore()
const key = computed(() => settings.keys[settings.provider])
const subject = computed(() => String(route.params.subject))
const decks = ref<StudyDocument[]>([])
const failed = ref(false)
const viewing = ref<{ id: string; page: number } | null>(null)
const open = ref<string[]>([]) // folded out: a Deck ("id") or one of its sections ("id:page")

watch(
  subject,
  async (name) => {
    viewing.value = null
    open.value = []
    failed.value = false
    decks.value = []
    try {
      const list = await listDocuments(name)
      if (name === subject.value) decks.value = list // the student may have moved to another Subject meanwhile
    } catch {
      if (name === subject.value) failed.value = true
    }
  },
  { immediate: true },
)

const isOpen = (k: string) => open.value.includes(k)
const toggle = (k: string) => (open.value = isOpen(k) ? open.value.filter((x) => x !== k) : [...open.value, k])
const confirming = ref<string | null>(null) // the Deck whose "send N pages?" question is showing
const busy = ref<string[]>([]) // Decks with a request in flight
const error = ref('')

async function change(d: StudyDocument, run: () => Promise<StudyDocument>) {
  busy.value = [...busy.value, d.id]
  error.value = ''
  try {
    const fresh = await run()
    decks.value = decks.value.map((x) => (x.id === d.id ? { ...x, outline: fresh.outline, outline_source: fresh.outline_source } : x))
  } catch (e) {
    error.value = askErrorMessage(e)
  }
  if (confirming.value === d.id) confirming.value = null
  busy.value = busy.value.filter((x) => x !== d.id)
}
const improve = (d: StudyDocument) => change(d, () => improveOutline(d.id, settings.provider, settings.models[settings.provider], key.value))
const reset = (d: StudyDocument) => change(d, () => resetOutline(d.id))
const explaining = ref(false)
/** a new Chat in this Subject, titled after the page and with it pinned, ready for "Ask AI" (which needs a question, so one is sent) */
async function explain() {
  const at = viewing.value
  const deck = decks.value.find((d) => d.id === at?.id)
  if (!at || !deck || explaining.value) return
  explaining.value = true
  error.value = ''
  try {
    const { id } = await createChat(subject.value)
    await renameChat(id, `${deck.title} · p. ${at.page}`)
    const kept = await setPinned(id, [{ document_id: at.id, page: at.page }])
    if (!kept.pinned.length) throw new Error('pin dropped')
    await postMessage(id, 'Explain this page')
    await router.push({ name: 'ask', query: { subject: subject.value, chat: id } })
  } catch {
    error.value = "Couldn't start the Chat. Try again."
  }
  explaining.value = false
}
const jump = (id: string, e: OutlineEntry) => (viewing.value = { id, page: e.page })
</script>

<template>
  <main class="study">
    <header>
      <RouterLink :to="{ name: 'ask', query: { subject } }">← Ask</RouterLink>
      <h1>{{ subject }}</h1>
    </header>
    <p v-if="failed" class="note" role="alert">Couldn't load the Decks.</p>
    <p v-if="error" class="note" role="alert">{{ error }}</p>

    <div class="viewer">
      <PdfViewer v-if="viewing" :url="`/api/documents/${encodeURIComponent(viewing.id)}/file`" :page="viewing.page" terms="" @error="viewing = null" />
      <button v-if="viewing" type="button" data-explain :disabled="explaining" @click="explain">Explain this page</button>
      <p v-else class="note">Open a Deck below and pick an entry to read it here.</p>
    </div>

    <p v-if="!decks.length && !failed" class="note">No material yet</p>
    <ol class="decks">
      <li v-for="d in decks" :key="d.id">
        <button type="button" class="fold" :aria-expanded="isOpen(d.id)" @click="toggle(d.id)">{{ d.title }}</button>
        <span v-if="!d.page_count" class="meta"> reading…</span>
        <div v-if="isOpen(d.id) && d.outline" class="actions">
          <span v-if="d.outline_source === 'ai'" class="meta" data-ai>AI outline</span>
          <button v-if="d.outline_source === 'ai'" type="button" :disabled="busy.includes(d.id)" data-reset @click="reset(d)">Reset to automatic</button>
          <template v-if="confirming === d.id">
            <span>Send {{ d.page_count }} pages (title and first ~200 characters each) to {{ settings.provider }}?</span>
            <button type="button" :disabled="busy.includes(d.id)" data-send @click="improve(d)">{{ busy.includes(d.id) ? 'Working…' : 'Send' }}</button>
            <button type="button" :disabled="busy.includes(d.id)" @click="confirming = null">Cancel</button>
          </template>
          <button v-else type="button" :disabled="!key" data-improve @click="confirming = d.id">Improve outline with AI</button>
          <span v-if="!key" class="meta" data-nokey>Add your API key in Settings first.</span>
        </div>
        <ul v-if="isOpen(d.id) && d.outline" class="level1" data-level1>
          <li v-for="(e, i) in d.outline" :key="i">
            <button v-if="e.children?.length" type="button" class="fold" :aria-expanded="isOpen(`${d.id}:${e.page}`)" @click="toggle(`${d.id}:${e.page}`)">
              {{ isOpen(`${d.id}:${e.page}`) ? '▾' : '▸' }}
            </button>
            <button type="button" class="link" @click="jump(d.id, e)">{{ e.title }}</button>
            <span class="meta"> p. {{ e.page }}</span>
            <ul v-if="isOpen(`${d.id}:${e.page}`)" class="level2" data-level2>
              <li v-for="(c, j) in e.children" :key="j">
                <button type="button" class="link" @click="jump(d.id, c)">{{ c.title }}</button>
                <span class="meta"> p. {{ c.page }}</span>
              </li>
            </ul>
          </li>
        </ul>
      </li>
    </ol>
  </main>
</template>

<style scoped>
.study {
  display: flex;
  flex-direction: column;
  gap: var(--s4);
  padding: var(--s4) var(--s5);
}
header {
  display: flex;
  gap: var(--s4);
  align-items: baseline;
}
h1 {
  font-weight: 500;
  font-size: 16px;
}
.viewer {
  min-height: 40vh;
}
.note,
.meta {
  color: var(--mute);
}
.decks,
.level1,
.level2 {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s2);
}
.level1,
.level2 {
  margin: var(--s2) 0 0 var(--s4);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s2);
  align-items: baseline;
  margin: var(--s2) 0 0 var(--s4);
}
.fold {
  font-weight: 500;
}
.link {
  text-align: left;
  text-decoration: underline;
}
</style>
