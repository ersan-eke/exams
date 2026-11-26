<script setup lang="ts">
import { computed, ref } from 'vue'
import { formatClock } from '@/lib/clock'
import { formatDate, scoreText, subjectOf, type Row } from '@/lib/stats'
import type { Attempt, StoredExam } from '@/types/attempt'

const props = defineProps<{
  exam: StoredExam
  /** handed-in attempts of this exam, newest first */
  rows: Row[]
  running: Attempt | undefined
}>()
const emit = defineEmits<{ update: [patch: Pick<StoredExam, 'subject' | 'hidden'>] }>()

const open = ref(false)

/** the uploaded PDF's own ink, else a solution attached to any attempt */
const solution = computed(() => {
  if (props.exam.hasInk) return props.exam.id
  return props.rows.find((r) => r.attempt.solutionExamId)?.attempt.solutionExamId ?? null
})

function rename(e: Event) {
  const subject = (e.target as HTMLInputElement).value.trim()
  if (subject) emit('update', { subject })
}
</script>

<template>
  <div class="exam" :data-exam="exam.id">
    <div class="line">
      <button
        type="button"
        class="chev"
        :aria-expanded="open"
        :aria-label="`${open ? 'Fold' : 'Unfold'} attempts of ${exam.title}`"
        @click="open = !open"
      >
        {{ open ? '⌄' : '›' }}
      </button>
      <RouterLink class="title" :to="{ name: 'exam-view', params: { examId: exam.id } }">{{
        exam.title
      }}</RouterLink>
      <span class="meta">uploaded {{ formatDate(exam.createdAt) }}</span>
      <span class="meta score">{{ scoreText(rows[0]) }}</span>
      <RouterLink
        v-if="solution"
        class="act"
        data-solution
        :to="{ name: 'exam-view', params: { examId: solution }, query: { ink: '1' } }"
        >View solution</RouterLink
      >
      <button type="button" class="act" @click="emit('update', { hidden: !exam.hidden })">
        {{ exam.hidden ? 'Unhide' : 'Hide' }}
      </button>
    </div>
    <div v-if="open" class="attempts">
      <RouterLink
        v-if="running"
        class="attempt"
        :to="{ name: 'exam', params: { attemptId: running.id } }"
        ><span>{{ formatDate(running.startedAt) }}</span><span>running</span></RouterLink
      >
      <RouterLink
        v-for="r in rows"
        :key="r.attempt.id"
        class="attempt"
        :to="{ name: 'results', params: { attemptId: r.attempt.id } }"
        ><span>{{ formatDate(r.attempt.startedAt) }}</span><span>{{ scoreText(r) }}</span
        ><span>{{ r.practice ? 'MCP' : formatClock(r.usedMs) }}</span></RouterLink
      >
      <p v-if="!rows.length && !running" class="none">No attempts yet.</p>
      <label class="subject">
        <span class="label">Subject</span>
        <input :value="subjectOf(exam)" name="subject" @change="rename" />
      </label>
    </div>
  </div>
</template>

<style scoped>
.exam + .exam {
  border-top: 1px solid var(--line);
}
.line {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--s1) var(--s3);
  padding: var(--s2) var(--s3);
}
.chev {
  width: 14px;
  color: var(--mute);
}
.title {
  flex: 1 1 160px;
  text-decoration: none;
}
.title:hover {
  text-decoration: underline;
}
.meta,
.act {
  color: var(--mute);
  font-size: var(--fs-sm);
}
.act {
  text-decoration: none;
}
.act:hover {
  color: var(--ink);
}
.attempts {
  padding: 0 var(--s3) var(--s3) 38px;
}
.attempt {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: var(--s3);
  padding: var(--s1) 0;
  font-size: var(--fs-sm);
  text-decoration: none;
  border-top: 1px solid var(--line);
}
.attempt:hover {
  background: var(--paper);
}
.none {
  color: var(--mute);
  font-size: var(--fs-sm);
}
.subject {
  display: flex;
  align-items: center;
  gap: var(--s2);
  margin-top: var(--s2);
}
.subject input {
  font: inherit;
  padding: 3px var(--s2);
  border: 1px solid var(--line);
  background: var(--paper);
  width: 180px;
}
</style>
