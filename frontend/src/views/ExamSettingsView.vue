<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { lastPulled, pulled } from '@/lib/sync'
import { useRoute, useRouter } from 'vue-router'
import { getExam } from '@/lib/db'
import { subjectOf } from '@/lib/stats'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'
import type { StoredExam } from '@/types/attempt'
import type { McRule } from '@/types/exam'

const route = useRoute()
const router = useRouter()
const library = useLibraryStore()
const settings = useSettingsStore()

const exam = ref<StoredExam>()
const title = ref('')
const subject = ref('')
const minutes = ref(90)
const included = ref<string[]>([])
const attendance = ref(settings.attendanceDefault)
const ruleKind = ref<McRule['kind']>('all_or_nothing')
const perTick = ref({ right: 1, wrong: -1, floor: 0 })
const error = ref('')
const starting = ref(false)

const examId = String(route.params.examId)

async function load() {
  const e = await getExam(examId)
  if (!e) return
  exam.value = e
  title.value = e.title
  subject.value = subjectOf(e)
  minutes.value = e.structure.duration_minutes ?? 90
  included.value = e.structure.tasks.map((t) => t.id)
  const rule = e.structure.mc_rule
  if (rule) {
    ruleKind.value = rule.kind
    if (rule.kind === 'per_tick')
      perTick.value = { right: rule.right, wrong: rule.wrong, floor: rule.floor }
  }
}
onMounted(load)
// only when this exam itself was replaced: a reload overwrites unsaved form edits
watch(pulled, () => lastPulled.exams.includes(examId) && load())

const tasks = computed(() => exam.value?.structure.tasks ?? [])
const hasMc = computed(() => tasks.value.some((t) => t.subtasks.some((s) => s.mc_options?.length)))
const points = computed(() => tasks.value.reduce((sum, t) => sum + (t.points ?? 0), 0))
const issues = computed(() => exam.value?.structure.issues ?? [])
const canStart = computed(() => included.value.length > 0 && minutes.value > 0 && !starting.value)

/** a cleared number field gives '' */
const num = (v: unknown, fallback: number) =>
  typeof v === 'number' && Number.isFinite(v) ? v : fallback

async function start() {
  if (!canStart.value) return
  starting.value = true
  error.value = ''
  try {
    const mcRule: McRule =
      ruleKind.value === 'per_tick'
        ? {
            kind: 'per_tick',
            right: num(perTick.value.right, 1),
            wrong: num(perTick.value.wrong, -1),
            floor: num(perTick.value.floor, 0),
          }
        : { kind: 'all_or_nothing' }
    const attemptId = await library.startAttempt(examId, {
      title: title.value.trim() || exam.value!.title,
      subject: subject.value.trim(),
      timeLimitMin: minutes.value,
      includedTaskIds: tasks.value.map((t) => t.id).filter((id) => included.value.includes(id)),
      attendance: attendance.value,
      mcRule,
    })
    await router.push({ name: 'exam', params: { attemptId } })
  } catch (e) {
    error.value =
      e instanceof Error && e.message === 'another exam is running'
        ? 'Another exam is still running. Finish or hand it in first.'
        : "Couldn't start the exam."
  } finally {
    starting.value = false
  }
}
</script>

<template>
  <div v-if="exam" class="settings">
    <input v-model="title" class="title" name="title" aria-label="Exam title" />
    <p class="summary">{{ tasks.length }} tasks · {{ points }} points</p>

    <section>
      <div class="label">Tasks</div>
      <label v-for="t in tasks" :key="t.id" class="row">
        <input v-model="included" type="checkbox" name="task" :value="t.id" />
        <span>{{ t.number }} {{ t.title }}</span>
        <span v-if="t.points !== null" class="pts">{{ t.points }}</span>
      </label>
    </section>

    <section>
      <label class="field">
        <span class="label">Subject</span>
        <input v-model="subject" name="subject" />
      </label>
      <label class="field">
        <span class="label">Time limit (minutes)</span>
        <input v-model.number="minutes" type="number" name="minutes" min="1" step="1" />
      </label>
      <label v-if="hasMc" class="field">
        <span class="label">Multiple choice scoring</span>
        <select v-model="ruleKind" name="mcrule">
          <option value="all_or_nothing">All or nothing</option>
          <option value="per_tick">Per tick</option>
        </select>
      </label>
      <div v-if="hasMc && ruleKind === 'per_tick'" class="ticks" data-per-tick>
        <label class="field">
          <span class="label">Per right tick</span>
          <input v-model.number="perTick.right" type="number" name="tick-right" step="0.25" />
        </label>
        <label class="field">
          <span class="label">Per wrong tick</span>
          <input v-model.number="perTick.wrong" type="number" name="tick-wrong" step="0.25" />
        </label>
        <label class="field">
          <span class="label">Minimum per subtask</span>
          <input v-model.number="perTick.floor" type="number" name="tick-floor" step="0.25" />
        </label>
      </div>
      <label class="row">
        <input v-model="attendance" type="checkbox" name="attendance" />
        <span>Attendance check</span>
      </label>
    </section>

    <section v-if="issues.length" class="notes">
      <div class="label">Notes from reading the exam</div>
      <p v-for="(i, k) in issues" :key="k">{{ i.message }}</p>
    </section>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <button type="button" class="start" :disabled="!canStart" @click="start">Start exam</button>
  </div>
</template>

<style scoped>
.settings {
  max-width: 520px;
  margin: 0 auto;
  padding: var(--s5);
  display: flex;
  flex-direction: column;
  gap: var(--s4);
}
.title {
  font: inherit;
  font-size: var(--fs-lg);
  font-weight: 500;
  border: 0;
  border-bottom: 1px solid var(--line);
  padding: var(--s2) 0;
  background: transparent;
}
.summary {
  margin: 0;
  color: var(--mute);
  font-variant-numeric: tabular-nums;
}
section {
  display: flex;
  flex-direction: column;
  gap: var(--s2);
}
.row {
  display: flex;
  align-items: center;
  gap: var(--s2);
  padding: var(--s1) 0;
}
.pts {
  margin-left: auto;
  color: var(--mute);
  font-variant-numeric: tabular-nums;
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--s1);
}
.field input,
.field select {
  font: inherit;
  padding: 7px var(--s2);
  border: 1px solid var(--line);
  background: var(--paper);
  max-width: 200px;
}
.ticks {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s3);
}
.ticks .field input {
  width: 90px;
}
.notes p {
  margin: 0;
  color: var(--mute);
}
.error {
  margin: 0;
  color: var(--over);
}
.start {
  align-self: flex-start;
  padding: 9px var(--s5);
  border: 1px solid var(--ink);
  background: var(--ink);
  color: var(--white);
}
.start:disabled {
  background: var(--soft);
  color: var(--mute);
  border-color: var(--line);
}
</style>
