<script setup lang="ts">
import { computed } from 'vue'
import { changedInOvertime, formatPoints, subtaskScore } from '@/lib/scoring'
import { includedTasks } from '@/lib/sheet'
import type { Attempt, StoredExam } from '@/types/attempt'

const props = defineProps<{
  exam: StoredExam
  attempt: Attempt
  /** answer keys by subtask id (see mcKeys), so automatic MC points count in "you" */
  keys?: Record<string, number[]>
}>()
defineEmits<{ jump: [subtaskId: string] }>()

const lines = computed(() => {
  const a = props.attempt
  return includedTasks(props.exam.structure, a).map((t) => {
    let you = 0
    let llm = 0
    const chips = t.subtasks.map((s) => {
      const sc = subtaskScore(a, t, s, props.keys?.[s.id])
      you += sc.over ?? sc.main
      const g = a.grades[s.id]?.llm?.[changedInOvertime(a, s.id) ? 'over' : 'main']
      // no printed point value: graded on a 1-point scale, shown as a verdict and kept out of the points total
      if (sc.max !== null) llm += g?.points ?? 0
      const shown = !g ? '–' : sc.max === null ? (g.points >= 1 ? '✓' : g.points <= 0 ? '✗' : '◐') : `${formatPoints(g.points)}/${formatPoints(sc.max)}`
      return { id: s.id, text: `${s.label} ${shown}` }
    })
    return { id: t.id, number: t.number, chips, you, llm }
  })
})
const any = computed(() =>
  Object.values(props.attempt.grades).some((g) => g.llm && Object.keys(g.llm).length),
)
</script>

<template>
  <section v-if="any" class="summary" aria-label="LLM grading summary">
    <p v-for="l in lines" :key="l.id" class="line" :data-task="l.id">
      <span class="num">Aufgabe {{ l.number }}</span>
      <button v-for="c in l.chips" :key="c.id" type="button" class="chip" @click="$emit('jump', c.id)">
        {{ c.text }}
      </button>
      <span class="total">you: {{ formatPoints(l.you) }} P · LLM: {{ formatPoints(l.llm) }} P</span>
    </p>
  </section>
</template>

<style scoped>
.summary {
  margin-top: var(--s4);
  padding-bottom: var(--s3);
  border-bottom: 1px solid var(--line);
}
.line {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s1) var(--s3);
  margin: 0 0 var(--s2);
}
.num {
  font-weight: 500;
}
.chip {
  color: var(--ink);
  border-bottom: 1px solid var(--line);
}
.total {
  margin-left: auto;
  color: var(--mute);
}
</style>
