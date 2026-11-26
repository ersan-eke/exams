<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { pulled } from '@/lib/sync'
import ExamRow from '@/components/exams/ExamRow.vue'
import AddMaterial from '@/components/material/AddMaterial.vue'
import FoldBar from '@/components/ui/FoldBar.vue'
import { attemptRows, bySubject, ownExams } from '@/lib/stats'
import { useLibraryStore } from '@/stores/library'
import type { Attempt, StoredExam } from '@/types/attempt'

const library = useLibraryStore()
const exams = ref<StoredExam[]>([])
const attempts = ref<Attempt[]>([])
const loaded = ref(false)
/** unfolded bars: subject names, prefixed with "hidden:" inside the Hidden section */
const open = ref<string[]>([])

async function load() {
  const c = await library.catalog()
  exams.value = c.exams
  attempts.value = c.attempts
  loaded.value = true
}
onMounted(load)
watch(pulled, load)

const rows = computed(() => attemptRows(exams.value, attempts.value))
const rowsOf = (id: string) => rows.value.filter((r) => r.exam.id === id)
const runningOf = (id: string) => attempts.value.find((a) => a.examId === id && a.status === 'running')
const visible = computed(() => bySubject(ownExams(exams.value).filter((e) => !e.hidden)))
const hidden = computed(() => bySubject(ownExams(exams.value).filter((e) => e.hidden)))

const toggle = (key: string) =>
  (open.value = open.value.includes(key) ? open.value.filter((k) => k !== key) : [...open.value, key])
const count = (n: number) => `${n} exam${n === 1 ? '' : 's'}`

async function update(id: string, patch: Pick<StoredExam, 'subject' | 'hidden'>) {
  await library.updateExam(id, patch)
  await load()
}
</script>

<template>
  <main class="my-exams">
    <h1>My exams</h1>
    <p v-if="loaded && !visible.length && !hidden.length" class="empty">
      No exams yet. <RouterLink :to="{ name: 'new' }">Upload one</RouterLink>.
    </p>
    <FoldBar
      v-for="[subject, list] in visible"
      :key="subject"
      class="group"
      :title="subject"
      :meta="count(list.length)"
      :folded="!open.includes(subject)"
      @toggle="toggle(subject)"
    >
      <ExamRow
        v-for="e in list"
        :key="e.id"
        :exam="e"
        :rows="rowsOf(e.id)"
        :running="runningOf(e.id)"
        @update="update(e.id, $event)"
      />
      <details class="material">
        <summary>Add material</summary>
        <AddMaterial :subject="subject" />
      </details>
    </FoldBar>

    <FoldBar
      v-if="hidden.length"
      class="hidden-section"
      title="Hidden"
      :meta="count(hidden.reduce((n, [, l]) => n + l.length, 0))"
      :folded="!open.includes('hidden')"
      @toggle="toggle('hidden')"
    >
      <FoldBar
        v-for="[subject, list] in hidden"
        :key="subject"
        class="group"
        :title="subject"
        :meta="count(list.length)"
        :folded="!open.includes(`hidden:${subject}`)"
        @toggle="toggle(`hidden:${subject}`)"
      >
        <ExamRow
          v-for="e in list"
          :key="e.id"
          :exam="e"
          :rows="rowsOf(e.id)"
          :running="runningOf(e.id)"
          @update="update(e.id, $event)"
        />
      </FoldBar>
    </FoldBar>
  </main>
</template>

<style scoped>
.my-exams {
  max-width: 760px;
  margin: 0 auto;
  padding: 36px 48px;
  display: flex;
  flex-direction: column;
  gap: var(--s2);
}
h1 {
  font-weight: 500;
  font-size: 18px;
  margin-bottom: var(--s4);
}
.empty {
  color: var(--mute);
}
.group :deep(.fold-body) {
  border: 1px solid var(--line);
  border-top: 0;
}
.material {
  padding: var(--s3) var(--s4);
}
.material summary {
  cursor: pointer;
  color: var(--mute);
}
.hidden-section {
  margin-top: var(--s5);
}
.hidden-section > :deep(.fold-body) {
  display: flex;
  flex-direction: column;
  gap: var(--s2);
  padding: var(--s2) 0 0 var(--s4);
}
@media (max-width: 600px) {
  .my-exams {
    padding: 28px 16px;
  }
}
</style>
