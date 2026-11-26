<script setup lang="ts">
import { computed } from 'vue'
import { formatClock, formatOvertime } from '@/lib/clock'
import { isAnswered } from '@/lib/answers'
import { isPractice } from '@/lib/scoring'
import { includedTasks } from '@/lib/sheet'
import type { Attempt, StoredExam } from '@/types/attempt'

const props = defineProps<{ attempt: Attempt; exam: StoredExam }>()

const used = computed(() => Math.max(0, (props.attempt.handedInAt ?? props.attempt.startedAt) - props.attempt.startedAt))
const within = computed(() => Math.min(used.value, props.attempt.timeLimitMs))
const over = computed(() => used.value - within.value)

const ids = computed(() =>
  includedTasks(props.exam.structure, props.attempt).flatMap((t) => t.subtasks.map((s) => s.id)),
)
// a practice attempt from Claude has no time; it counts what was practiced against the whole exam
const practice = computed(() => isPractice(props.attempt))
const examSubtasks = computed(() => props.exam.structure.tasks.reduce((n, t) => n + t.subtasks.length, 0))
const practiced = computed(() => Object.keys(props.attempt.grades).length)

const answered = computed(() => {
  const source = props.attempt.snapshot ?? props.attempt.answers
  return ids.value.filter((id) => isAnswered(source[id])).length
})
</script>

<template>
  <div v-if="practice" class="stats" data-practice>
    <div class="stat">
      <div class="v">{{ practiced }} / {{ examSubtasks }}</div>
      <div class="k">subtasks of the exam practiced in Claude</div>
    </div>
  </div>
  <div v-else class="stats">
    <div class="stat">
      <div class="v">{{ formatClock(within) }}</div>
      <div class="k">within the limit</div>
    </div>
    <div v-if="over > 0" class="stat">
      <div class="v over">{{ formatOvertime(over) }}</div>
      <div class="k">overtime</div>
    </div>
    <div class="stat">
      <div class="v">{{ answered }} / {{ ids.length }}</div>
      <div class="k">subtasks answered in time</div>
    </div>
  </div>
</template>

<style scoped>
.stats {
  display: flex;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.stat {
  flex: 1;
  padding: 16px 0;
}
.stat + .stat {
  padding-left: 18px;
  border-left: 1px solid var(--line);
}
.v {
  font-size: 22px;
  font-weight: 300;
  font-variant-numeric: tabular-nums;
}
.k {
  color: var(--mute);
  margin-top: 4px;
  font-size: 12px;
}
.over {
  color: var(--over);
}
</style>
