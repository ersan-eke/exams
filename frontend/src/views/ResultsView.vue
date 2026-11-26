<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LlmSummary from '@/components/results/LlmSummary.vue'
import TimeBars from '@/components/results/TimeBars.vue'
import TimeStats from '@/components/results/TimeStats.vue'
import PdfDropZone from '@/components/ui/PdfDropZone.vue'
import { useSolutionExam } from '@/composables/useSolutionExam'
import { uploadErrorMessage } from '@/lib/api'
import { formatPoints, isPractice, scores, subtaskScore } from '@/lib/scoring'
import { mcKeys } from '@/lib/solution'
import { useAttemptStore } from '@/stores/attempt'
import { useAccountStore } from '@/stores/account'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'

const route = useRoute()
const router = useRouter()
const store = useAttemptStore()
const ready = ref(false)
const error = ref<string | null>(null)

const settings = useSettingsStore()
const hasKey = computed(() => !!settings.keys[settings.provider])
const llmHint = computed(() =>
  !hasKey.value
    ? 'Add an API key in settings'
    : hasSolution.value
      ? 'using the solution'
      : 'no solution: the model solves it first',
)
const gradeParams = () => ({
  attemptId: route.params.attemptId,
  mode: hasSolution.value ? 'solution' : 'self',
})
const askLlm = () => router.push({ name: 'grade', params: gradeParams(), query: { llm: '1' } })
// the grading page scrolls to the row named by the hash
const jump = (subtaskId: string) =>
  router.push({ name: 'grade', params: gradeParams(), hash: `#${subtaskId}` })

const library = useLibraryStore()
const account = useAccountStore()
const dropOpen = ref(false)
const uploading = ref(false)
const uploadError = ref('')
const hasSolution = computed(() => !!store.exam?.hasInk || !!store.attempt?.solutionExamId)
const solutionExam = useSolutionExam()
const score = computed(() => {
  const a = store.attempt
  const e = store.exam
  if (!a || !e) return null
  return scores(a, e.structure, keys.value)
})
const keys = computed(() =>
  store.exam ? mcKeys(store.exam.structure, solutionExam.value?.structure ?? null) : {},
)
/** points per subtask, once grading is finished */
const points = computed(() => {
  const a = store.attempt
  const e = store.exam
  if (!a?.gradedAt || !e) return undefined
  return Object.fromEntries(
    e.structure.tasks.flatMap((t) =>
      t.subtasks.map((s) => [s.id, subtaskScore(a, t, s, keys.value[s.id])]),
    ),
  )
})

const grade = (mode: 'solution' | 'self') =>
  router.push({ name: 'grade', params: { attemptId: route.params.attemptId, mode } })

function compare() {
  if (hasSolution.value) void grade('solution')
  else {
    dropOpen.value = true
  }
}

function gradeMyself() {
  void grade('self')
}

async function uploadSolution(file: File) {
  const a = store.attempt
  if (!a) return
  uploadError.value = ''
  uploading.value = true
  try {
    await library.attachSolution(a.id, file)
    dropOpen.value = false
    await grade('solution')
  } catch (e) {
    uploadError.value = uploadErrorMessage(e)
  } finally {
    uploading.value = false
  }
}

async function open(id: string) {
  dropOpen.value = false
  ready.value = false
  error.value = null
  try {
    await store.load(id)
    if (store.attempt?.status === 'running') {
      await router.replace({ name: 'exam', params: { attemptId: id } })
      return
    }
    ready.value = true
  } catch {
    error.value = 'These results could not be opened.'
  }
}

watch(
  () => route.params.attemptId as string,
  (id) => void open(id),
  { immediate: true },
)
</script>

<template>
  <main class="results">
    <p v-if="error" class="kicker">{{ error }}</p>
    <template v-else-if="ready && store.attempt && store.exam">
      <template v-if="isPractice(store.attempt)">
        <p class="kicker">Practiced in Claude · MCP · {{ store.exam.title }}</p>
        <h1>Practice session in Claude.</h1>
        <TimeStats :attempt="store.attempt" :exam="store.exam" />
      </template>
      <template v-else>
        <p class="kicker">Handed in · {{ store.exam.title }}</p>
        <h1>Done. Here is how you used your time.</h1>
        <TimeStats :attempt="store.attempt" :exam="store.exam" />
        <TimeBars :attempt="store.attempt" :exam="store.exam" :points="points" />
      </template>
      <section class="grading" data-section="grading">
        <div v-if="score" class="score">
          <div class="score-main">
            {{ formatPoints(score.main) }} / {{ formatPoints(score.maxKnown) }}
          </div>
          <div v-if="score.over !== null" class="score-over">
            With overtime {{ formatPoints(score.over) }} / {{ formatPoints(score.maxKnown) }}
          </div>
        </div>
        <div class="actions">
          <button type="button" class="btn on" @click="compare">Compare with solution</button>
          <button type="button" class="btn" @click="gradeMyself">Grade myself</button>
          <button type="button" class="btn" :disabled="!hasKey" @click="askLlm">
            Ask an LLM to grade <span class="soon" data-llm-hint>{{ llmHint }}</span>
          </button>
        </div>
        <LlmSummary :exam="store.exam" :attempt="store.attempt" :keys="keys" @jump="jump" />
        <PdfDropZone
          v-if="dropOpen"
          class="drop"
          data-solution-drop
          heading="Drop the solution PDF here"
          :hint="account.user ? 'Kept in your account' : 'Stays on this device'"
          :busy="uploading"
          busy-text="Reading the solution…"
          :error="uploadError"
          @file="uploadSolution"
        />
      </section>
      <footer class="foot">
        <RouterLink
          class="btn"
          data-retry
          :to="{ name: 'exam-settings', params: { examId: store.exam.id } }"
          >Retry</RouterLink
        >
        <RouterLink class="btn" data-home :to="{ name: 'new' }">Home</RouterLink>
      </footer>
    </template>
  </main>
</template>

<style scoped>
.results {
  max-width: 640px;
  margin: 0 auto;
  padding: 36px 48px;
  font-size: 12px;
}
.kicker {
  color: var(--mute);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  margin: 0 0 6px;
}
h1 {
  font-weight: 500;
  font-size: 18px;
  margin: 0 0 26px;
}
.score {
  margin-top: var(--s5);
  font-variant-numeric: tabular-nums;
}
.score-main {
  font-size: 28px;
  font-weight: 300;
}
.score-over {
  margin-top: var(--s1);
  color: var(--over);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s3);
  margin-top: 30px;
}
.btn {
  padding: 9px 16px;
  border: 1px solid var(--line);
  color: var(--ink);
}
.btn.on {
  border-color: var(--ink);
}
.btn:disabled {
  color: var(--mute);
  cursor: default;
}
.soon {
  font-size: var(--fs-sm);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-left: var(--s1);
}
.drop {
  margin-top: var(--s4);
}
.foot {
  display: flex;
  justify-content: space-between;
  margin-top: var(--s6);
  padding-top: var(--s4);
  border-top: 1px solid var(--line);
}
.foot .btn {
  text-decoration: none;
}
@media (max-width: 600px) {
  .results {
    padding: 28px 16px;
  }
}
</style>
