<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { pulled } from '@/lib/sync'
import { useRoute } from 'vue-router'
import ActivityGrid from '@/components/stats/ActivityGrid.vue'
import StatsSummary from '@/components/stats/StatsSummary.vue'
import { formatClock } from '@/lib/clock'
import { followJob } from '@/lib/api'
import { listIntegrations } from '@/lib/integrations'
import { downloadAnki, exportToNotion, listSubjects } from '@/lib/subjects'
import { attemptRows, bySubject, formatDate, scoreText, subjectOf, summarize, type Row } from '@/lib/stats'
import { useLibraryStore } from '@/stores/library'
import type { Attempt, StoredExam } from '@/types/attempt'

const route = useRoute()
const library = useLibraryStore()
const exams = ref<StoredExam[]>([])
const attempts = ref<Attempt[]>([])
const loaded = ref(false)

async function load() {
  const c = await library.catalog()
  exams.value = c.exams
  attempts.value = c.attempts
  loaded.value = true
}
onMounted(load)
watch(pulled, load)

/** set on the second layer: one subject's statistics */
const subject = computed(() => (route.params.subject as string | undefined) || null)
const allRows = computed(() =>
  attemptRows(
    exams.value.filter((e) => !e.hidden),
    attempts.value,
  ),
)
const rows = computed(() =>
  subject.value ? allRows.value.filter((r) => subjectOf(r.exam) === subject.value) : allRows.value,
)
const summary = computed(() => summarize(rows.value, exams.value))
const subjects = computed(() => bySubject([...new Set(allRows.value.map((r) => r.exam))]).map(([s]) => s))

const exporting = ref(false)
const exportError = ref('')
async function exportAnki() {
  exporting.value = true
  exportError.value = ''
  try {
    // the route carries the name; the API wants the id
    const s = (await listSubjects()).find((s) => s.name.toLowerCase() === subject.value!.toLowerCase())
    if (!s) throw new Error('unknown_subject')
    await downloadAnki(s.id, subject.value!)
  } catch (e) {
    exportError.value =
      (e as Error).message === 'nothing_weak'
        ? 'No questions scored below 60% in this subject yet.'
        : 'Could not export the deck. Try again.'
  } finally {
    exporting.value = false
  }
}

const notionConnected = ref(false)
const notionUrl = ref<string | null>(null)
const notionState = ref<'idle' | 'sending' | 'sent'>('idle')
const notionError = ref('')
async function refreshNotion() {
  const n = (await listIntegrations()).notion
  notionConnected.value = n.enabled && n.connections.length > 0
  notionUrl.value = n.databaseUrl
}
onMounted(() => refreshNotion().catch(() => {}))

const notionErrors: Record<string, string> = {
  nothing_weak: 'No questions scored below 60% in this subject yet.',
  notion_not_connected: 'Reconnect Notion in Settings.',
  notion_auth: 'Reconnect Notion in Settings.',
}
async function sendToNotion() {
  notionState.value = 'sending'
  notionError.value = ''
  let code = ''
  try {
    const s = (await listSubjects()).find((s) => s.name.toLowerCase() === subject.value!.toLowerCase())
    if (!s) throw new Error('unknown_subject')
    const end = await followJob(await exportToNotion(s.id))
    if (end.status === 'failed') code = end.error_code ?? 'server'
  } catch (e) {
    code = (e as Error).message
  }
  if (code) {
    notionError.value = notionErrors[code] ?? "Couldn't send to Notion. Try again."
    notionState.value = 'idle'
    return
  }
  await refreshNotion().catch(() => {})
  notionState.value = 'sent'
}

/** the subject's practiced exams, each with its attempts (newest first) */
/** practice from Claude has no time of its own */
const timed = (rows: Row[]) => rows.filter((r) => !r.practice)
const examList = computed(() =>
  bySubject([...new Set(rows.value.map((r) => r.exam))]).flatMap(([, list]) =>
    list.map((exam) => {
      const own = rows.value.filter((r) => r.exam === exam)
      const graded = own.filter((r) => r.score)
      const pct = graded.length
        ? Math.round(
            (graded.reduce((s, r) => s + r.score!.main, 0) /
              Math.max(1, graded.reduce((s, r) => s + r.score!.max, 0))) *
              100,
          )
        : null
      return {
        exam,
        latest: own[0]!,
        count: own.length,
        pct,
        avgMs: timed(own).reduce((s, r) => s + r.usedMs, 0) / Math.max(1, timed(own).length),
      }
    }),
  ),
)
</script>

<template>
  <main class="statistics">
    <p v-if="subject" class="kicker">
      <RouterLink :to="{ name: 'statistics' }">Statistics</RouterLink> · {{ subject }}
    </p>
    <h1>{{ subject ?? 'Statistics' }}</h1>

    <p v-if="loaded && !allRows.length" class="empty">
      No exams handed in yet. <RouterLink :to="{ name: 'new' }">Start one</RouterLink>.
    </p>
    <template v-else-if="loaded">
      <nav v-if="!subject" class="subjects" aria-label="Subjects">
        <RouterLink
          v-for="s in subjects"
          :key="s"
          class="btn"
          :to="{ name: 'statistics-subject', params: { subject: s } }"
          >{{ s }}</RouterLink
        >
      </nav>

      <StatsSummary :summary="summary">
        <section v-if="!subject" class="recent" data-section="recent">
          <div class="label">Recent</div>
          <RouterLink
            v-for="r in rows.slice(0, 5)"
            :key="r.attempt.id"
            class="line"
            :to="{ name: 'results', params: { attemptId: r.attempt.id } }"
            ><span>{{ r.exam.title }}</span><span>{{ scoreText(r) }}</span
            ><span>{{ r.practice ? 'MCP' : formatClock(r.usedMs) }}</span></RouterLink
          >
        </section>
      </StatsSummary>

      <section v-if="subject" class="exams" data-section="exams">
        <div class="label">Exams</div>
        <RouterLink
          v-for="e in examList"
          :key="e.exam.id"
          class="line"
          :to="{ name: 'results', params: { attemptId: e.latest.attempt.id } }"
          ><span>{{ e.exam.title }}</span
          ><span>{{ e.count }} attempt{{ e.count === 1 ? '' : 's' }} · last
            {{ formatDate(e.latest.attempt.startedAt) }}</span
          ><span>{{ e.pct === null ? 'not graded' : `${e.pct} %` }}</span
          ><span>{{ formatClock(e.avgMs) }}</span></RouterLink
        >
      </section>

      <section v-if="subject" class="anki" data-section="anki">
        <button class="btn" :disabled="exporting" @click="exportAnki">Export weak questions to Anki</button>
        <p v-if="exportError" role="alert">{{ exportError }}</p>
        <template v-if="notionConnected">
          <button class="btn" :disabled="notionState === 'sending'" @click="sendToNotion">
            {{ notionState === 'sending' ? 'Sending…' : 'Send weak questions to Notion' }}
          </button>
          <a v-if="notionState === 'sent' && notionUrl" :href="notionUrl" target="_blank" rel="noopener">Sent. Open in Notion</a>
          <p v-if="notionError" role="alert">{{ notionError }}</p>
        </template>
      </section>

      <section v-if="!subject" class="activity" data-section="activity">
        <div class="label">Activity</div>
        <ActivityGrid :rows="allRows" />
      </section>
    </template>
  </main>
</template>

<style scoped>
.statistics {
  max-width: 760px;
  margin: 0 auto;
  padding: 36px 48px;
}
.kicker {
  color: var(--mute);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  margin: 0 0 6px;
}
.kicker a {
  color: inherit;
}
h1 {
  font-weight: 500;
  font-size: 18px;
  margin-bottom: var(--s4);
}
.empty {
  color: var(--mute);
}
.subjects {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s2);
  margin-bottom: var(--s5);
}
.btn {
  padding: 7px 16px;
  border: 1px solid var(--line);
  text-decoration: none;
}
.btn:hover {
  border-color: var(--ink);
}
section {
  margin-top: var(--s5);
}
.label {
  margin-bottom: var(--s2);
}
.line {
  display: grid;
  grid-template-columns: 2fr 1fr auto;
  gap: var(--s3);
  padding: var(--s1) 0;
  border-bottom: 1px solid var(--line);
  text-decoration: none;
}
.exams .line {
  grid-template-columns: 2fr 2fr 1fr auto;
}
.line:hover {
  background: var(--paper);
}
.line span + span {
  color: var(--mute);
}
@media (max-width: 600px) {
  .statistics {
    padding: 28px 16px;
  }
  .exams .line {
    grid-template-columns: 1fr auto;
  }
}
</style>
