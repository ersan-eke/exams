<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GradingList from '@/components/results/GradingList.vue'
import LlmSummary from '@/components/results/LlmSummary.vue'
import { useSolutionExam } from '@/composables/useSolutionExam'
import { listExams } from '@/lib/db'
import { evalCasesJsonl, planGrading } from '@/lib/grading'
import { mcKeys } from '@/lib/solution'
import { useAttemptStore } from '@/stores/attempt'
import { useSettingsStore } from '@/stores/settings'

const DEV = import.meta.env.DEV
const route = useRoute()
const router = useRouter()
const store = useAttemptStore()
const settings = useSettingsStore()
const solutionExam = useSolutionExam()
const ready = ref(false)
const error = ref<string | null>(null)
const mode = computed(() => (route.params.mode === 'solution' ? 'solution' : 'self'))

async function open(id: string) {
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
    error.value = 'This attempt could not be opened.'
  }
}

const PROVIDER_NAMES = { anthropic: 'Claude', google: 'Gemini', openrouter: 'OpenRouter' }
const grading = computed(() => store.llm.done < store.llm.total)
const keys = computed(() =>
  store.exam ? mcKeys(store.exam.structure, solutionExam.value?.structure ?? null) : {},
)

const jump = (id: string) =>
  document.querySelector(`[data-grade-row="${id}"]`)?.scrollIntoView({ behavior: 'smooth' })

// arriving with #<subtaskId> (from the results summary) scrolls to that row once it is rendered
watch(ready, async (r) => {
  if (!r || !route.hash) return
  await nextTick()
  jump(decodeURIComponent(route.hash.slice(1)))
})

/** dev only: the self-graded versions as eval cases, with similar solved tasks as references */
async function exportEval() {
  const { exam, attempt } = store
  if (!exam || !attempt) return
  const { jobs } = planGrading({
    exam,
    attempt,
    solutionExam: solutionExam.value ?? null,
    mcKeys: keys.value,
    library: await listExams(),
    provider: settings.provider,
    model: settings.models[settings.provider],
    withReferences: true,
  })
  const cases = await Promise.all(
    jobs.flatMap((j) => {
      const expected = attempt.grades[j.subtaskId]?.[j.version]
      return expected === undefined
        ? []
        : [j.build().then((request) => ({ id: j.key, expected, request }))]
    }),
  )
  const url = URL.createObjectURL(new Blob([evalCasesJsonl(cases)], { type: 'application/jsonl' }))
  const a = document.createElement('a')
  a.href = url
  a.download = 'cases.jsonl'
  a.click()
  URL.revokeObjectURL(url)
}

async function finish() {
  await store.finishGrading()
  await router.push({ name: 'results', params: { attemptId: route.params.attemptId } })
}

watch(
  () => route.params.attemptId as string,
  (id) => void open(id),
  { immediate: true },
)
</script>

<template>
  <div class="grading-page">
    <p v-if="error" class="message">{{ error }}</p>
    <template v-else-if="ready">
      <header class="top">
        <span class="title">Grading · {{ store.exam?.title }}</span>
        <span v-if="grading" class="progress" data-llm-progress>
          {{ PROVIDER_NAMES[settings.provider] }} is grading · {{ store.llm.done }} /
          {{ store.llm.total }}
          <span
            class="bar"
            role="progressbar"
            aria-label="LLM grading progress"
            aria-valuemin="0"
            :aria-valuenow="store.llm.done"
            :aria-valuemax="store.llm.total"
            ><span class="fill" :style="{ width: `${(store.llm.done / store.llm.total) * 100}%` }"
          /></span>
          <button type="button" class="link" @click="store.stopLlm()">Stop</button>
        </span>
        <button v-if="DEV" type="button" class="link" data-export-eval @click="exportEval">
          Export eval cases
        </button>
        <button type="button" class="finish" data-finish @click="finish">Finish grading</button>
      </header>
      <main class="page">
        <LlmSummary v-if="store.attempt && store.exam" :exam="store.exam" :attempt="store.attempt" :keys="keys" @jump="jump" />
        <GradingList :mode="mode" />
      </main>
    </template>
  </div>
</template>

<style scoped>
.grading-page {
  min-height: 100vh;
  background: var(--white);
  font-size: 12px;
}
.message {
  margin: var(--s6) auto;
  color: var(--mute);
  text-align: center;
}
.top {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--s3);
  padding: var(--s3) 20px;
  padding-top: calc(var(--s3) + env(safe-area-inset-top, 0px));
  border-bottom: 1px solid var(--line);
  background: var(--white);
}
.title {
  color: var(--mute);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.progress {
  display: flex;
  align-items: center;
  gap: var(--s2);
  margin-left: auto;
  color: var(--mute);
  white-space: nowrap;
}
.bar {
  width: 64px;
  height: 2px;
  background: var(--line);
}
.fill {
  display: block;
  height: 100%;
  background: var(--ink);
}
.link {
  color: var(--mute);
  border-bottom: 1px solid var(--line);
}
.finish {
  color: var(--ink);
  font-weight: 500;
  padding: 2px 0;
  border-bottom: 1px solid var(--ink);
}
.page {
  max-width: 640px;
  margin: 0 auto;
  padding: 0 48px 48px;
}
.page :deep(.grading-list) {
  margin-top: 0;
  border-top: 0;
}
@media (max-width: 600px) {
  .page {
    padding: 0 16px 28px;
  }
}
</style>
