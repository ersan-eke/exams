<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AddMaterial from '@/components/material/AddMaterial.vue'
import ChatPane from '@/components/material/ChatPane.vue'
import SubjectSelect from '@/components/material/SubjectSelect.vue'
import FoldBar from '@/components/ui/FoldBar.vue'
import { deleteDocument, listDocuments, materialRoute, patchDocument, type DocumentKind, type StudyDocument } from '@/lib/documents'
import { listSubjects, renameSubject, type Subject } from '@/lib/subjects'
import { sync } from '@/lib/sync'
import { useAccountStore } from '@/stores/account'

const route = useRoute()
const account = useAccountStore()

const subject = ref(typeof route.query.subject === 'string' ? route.query.subject : '')
const subjects = ref<Subject[]>([])
const decks = ref<StudyDocument[]>([])
const open = ref<string[]>(subject.value ? [subject.value.toLowerCase()] : [])
const manageError = ref('')

const trimmed = computed(() => subject.value.trim())
// the Chat of the link belongs to the link's Subject only
const chatId = computed(() => (typeof route.query.chat === 'string' && trimmed.value === route.query.subject ? route.query.chat : undefined))
const same = (a: string | null, b: string) => a?.toLowerCase() === b.toLowerCase()
const decksOf = (name: string) => decks.value.filter((d) => same(d.subject, name))
const unfiled = computed(() => decks.value.filter((d) => !d.subject))

async function load() {
  if (!account.user) return
  const [s, d] = await Promise.all([listSubjects(), listDocuments()])
  subjects.value = s
  decks.value = d
}
onMounted(load)
watch(() => account.user, load)

const toggle = (k: string) => (open.value = open.value.includes(k) ? open.value.filter((x) => x !== k) : [...open.value, k])
const count = (n: number) => (n ? `${n} Deck${n === 1 ? '' : 's'}` : 'No material yet')

async function reorder(list: StudyDocument[], i: number, by: -1 | 1) {
  const next = [...list]
  ;[next[i], next[i + by]] = [next[i + by]!, next[i]!]
  await Promise.all(next.flatMap((d, pos) => (d.position === pos ? [] : [patchDocument(d.id, { position: pos })])))
  await load()
}
async function rename(d: StudyDocument, e: Event) {
  const title = (e.target as HTMLInputElement).value.trim()
  if (title && title !== d.title) await patchDocument(d.id, { title })
  await load()
}
async function setKind(d: StudyDocument, e: Event) {
  await patchDocument(d.id, { kind: (e.target as HTMLSelectElement).value as DocumentKind })
  await load()
}
async function file(d: StudyDocument, name: string) {
  if (name) await patchDocument(d.id, { subject: name })
  await load()
}
async function remove(d: StudyDocument) {
  if (!confirm(`Delete "${d.title}"?`)) return
  await deleteDocument(d.id)
  await load()
}
async function renameBar(s: Subject, e: Event) {
  const input = e.target as HTMLInputElement
  const name = input.value.trim()
  manageError.value = ''
  if (!name || name === s.name) return (input.value = s.name)
  try {
    await renameSubject(s.id, name)
  } catch (err) {
    input.value = s.name
    manageError.value = err instanceof Error && err.message === 'name_taken' ? `There is already a Subject called ${name}.` : 'Renaming failed.'
    return
  }
  if (same(subject.value, s.name)) subject.value = name
  open.value = open.value.map((k) => (k === s.name.toLowerCase() ? name.toLowerCase() : k))
  await Promise.all([load(), sync().catch(() => {})]) // exams take the new name from the server on this pull
}

</script>

<template>
  <main class="ask">
    <h1>Ask</h1>
    <p v-if="!account.user" class="note">Sign in to add Decks and ask questions about them.</p>
    <template v-else>
      <SubjectSelect v-model="subject" @created="load" />

      <ChatPane v-if="trimmed" :subject="trimmed" :chat-id="chatId" />

      <section class="decks">
        <h2>Decks</h2>
        <p v-if="manageError" class="error" role="alert">{{ manageError }}</p>
        <FoldBar
          v-for="s in subjects"
          :key="s.id"
          :title="s.name"
          :meta="count(decksOf(s.name).length)"
          :folded="!open.includes(s.name.toLowerCase())"
          @toggle="toggle(s.name.toLowerCase())"
        >
          <div class="bar-body">
            <input class="title" :value="s.name" aria-label="Subject name" @change="renameBar(s, $event)" />
            <RouterLink :to="{ name: 'study', params: { subject: s.name } }">Study page</RouterLink>
            <p v-if="!decksOf(s.name).length" class="note">No material yet</p>
            <ol class="rows">
              <li v-for="(d, i) in decksOf(s.name)" :key="d.id">
                <input class="title" :value="d.title" aria-label="Deck title" @change="rename(d, $event)" />
                <select :value="d.kind" aria-label="Deck kind" @change="setKind(d, $event)">
                  <option value="slides">Slides</option>
                  <option value="script">Script</option>
                  <option value="exercises">Exercises</option>
                </select>
                <span class="meta">{{ d.page_count ? `${d.page_count} p.` : 'reading…' }}</span>
                <RouterLink v-if="d.page_count" :to="materialRoute(d.id)">Open</RouterLink>
                <button type="button" :disabled="i === 0" aria-label="Move up" @click="reorder(decksOf(s.name), i, -1)">↑</button>
                <button type="button" :disabled="i === decksOf(s.name).length - 1" aria-label="Move down" @click="reorder(decksOf(s.name), i, 1)">↓</button>
                <button type="button" @click="remove(d)">Delete</button>
              </li>
            </ol>
            <AddMaterial :subject="s.name" @done="load" />
          </div>
        </FoldBar>

        <FoldBar v-if="unfiled.length" title="Unfiled" :meta="count(unfiled.length)" :folded="!open.includes('unfiled')" @toggle="toggle('unfiled')">
          <div class="bar-body">
            <ul class="rows">
              <li v-for="d in unfiled" :key="d.id">
                <span class="title">{{ d.title }}</span>
                <span class="meta">{{ d.kind }}</span>
                <SubjectSelect label="Assign to" @update:model-value="file(d, $event)" />
                <button type="button" @click="remove(d)">Delete</button>
              </li>
            </ul>
          </div>
        </FoldBar>
        <AddMaterial v-if="!subjects.length" @done="load" />
      </section>
    </template>
  </main>
</template>

<style scoped>
.ask {
  max-width: 1280px;
  margin: 0 auto;
  padding: 36px 48px;
  display: flex;
  flex-direction: column;
  gap: var(--s4);
}
h1 {
  font-weight: 500;
  font-size: 18px;
}
h2 {
  font-weight: 500;
  font-size: var(--fs-lg);
  margin-bottom: var(--s3);
}
.note,
.meta {
  color: var(--mute);
}
.error {
  color: var(--over);
}
.rows button {
  padding: 6px var(--s3);
  border: 1px solid var(--ink);
}
.rows button:disabled {
  opacity: 0.4;
}
.rows {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s2);
  margin-bottom: var(--s3);
}
.rows li {
  display: flex;
  gap: var(--s3);
  align-items: center;
  flex-wrap: wrap;
}
.title {
  flex: 1 1 200px;
}
.bar-body {
  display: flex;
  flex-direction: column;
  gap: var(--s3);
  padding: var(--s3) var(--s4);
  border: 1px solid var(--line);
  border-top: 0;
}
@media (max-width: 600px) {
  .ask {
    padding: 28px 16px;
  }
}
</style>
