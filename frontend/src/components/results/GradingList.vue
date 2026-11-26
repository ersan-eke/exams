<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GradingRow, { type SolutionView } from './GradingRow.vue'
import { useSolutionExam } from '@/composables/useSolutionExam'
import { listExams } from '@/lib/db'
import { planGrading } from '@/lib/grading'
import { includedTasks } from '@/lib/sheet'
import { matchSolution, mcKeys } from '@/lib/solution'
import { useAccountStore } from '@/stores/account'
import { useAttemptStore } from '@/stores/attempt'
import { useSettingsStore } from '@/stores/settings'
import type { Region, Subtask } from '@/types/exam'

const props = defineProps<{ mode: 'solution' | 'self' }>()
const store = useAttemptStore()

/** undefined while loading, null when the linked solution exam can't be loaded */
const solutionExam = useSolutionExam()

const matches = computed(() =>
  store.exam && solutionExam.value
    ? matchSolution(store.exam.structure, solutionExam.value.structure)
    : {},
)

/** the attached solution's key also auto-grades MC of a blank exam, in both modes */
const keys = computed(() =>
  store.exam ? mcKeys(store.exam.structure, solutionExam.value?.structure ?? null) : {},
)

const images = (regions: Region[]) =>
  regions.flatMap((r, regionIndex) => (r.image === null ? [] : [{ name: r.image, regionIndex }]))

const view = (examId: string, s: Subtask): SolutionView => ({
  examId,
  images: images(s.regions),
  text: s.solution_text,
  mc: s.mc_options?.length && s.mc_key?.length ? { options: s.mc_options, key: s.mc_key } : null,
})

function solutionFor(s: Subtask): SolutionView | null {
  const e = store.exam
  if (props.mode !== 'solution' || !e) return null
  if (e.hasInk) return view(e.id, s)
  if (solutionExam.value === undefined) return null // still loading
  const m = matches.value[s.id]
  if (!solutionExam.value || !m) return { examId: '', images: [], text: '', mc: null }
  return view(solutionExam.value.id, m)
}

// once the solution is known, plan the jobs so Re-grade works; ?llm=1 (from the results page) also runs them
const route = useRoute()
const router = useRouter()
const settings = useSettingsStore()
const account = useAccountStore()
let plannedFor: string | null = null
watch(
  () =>
    store.exam &&
    store.attempt &&
    (solutionExam.value !== undefined || store.exam.hasInk || !store.attempt.solutionExamId)
      ? store.attempt.id
      : null,
  async (id) => {
    if (!id || id === plannedFor) return
    plannedFor = id
    const run = route.query.llm === '1'
    if (run) {
      const { llm: _llm, ...query } = route.query
      await router.replace({ query })
    }
    let plan: ReturnType<typeof planGrading>
    try {
      plan = planGrading({
        exam: store.exam!,
        attempt: store.attempt!,
        solutionExam: solutionExam.value ?? null,
        mcKeys: keys.value,
        library: await listExams(),
        provider: settings.provider,
        model: settings.models[settings.provider],
        material: !!account.user,
      })
    } catch {
      return // no plan: Re-grade stays inert, the rows still work
    }
    if (run) await store.gradeWithLlm(plan.jobs, plan.skipped, settings.keys)
    else store.prepareLlm(plan.jobs, plan.skipped)
  },
  { immediate: true },
)

const rows = computed(() =>
  store.exam && store.attempt
    ? includedTasks(store.exam.structure, store.attempt).flatMap((task) =>
        task.subtasks.map((subtask) => ({ task, subtask })),
      )
    : [],
)
</script>

<template>
  <div class="grading-list">
    <GradingRow
      v-for="r in rows"
      :key="r.subtask.id"
      :task="r.task"
      :subtask="r.subtask"
      :solution="solutionFor(r.subtask)"
      :mc-key="keys[r.subtask.id] ?? null"
    />
  </div>
</template>

<style scoped>
.grading-list {
  margin-top: var(--s5);
  border-top: 1px solid var(--line);
}
</style>
