<script setup lang="ts">
import { computed } from 'vue'
import { formatPoints } from '@/lib/scoring'
import type { SkipReason } from '@/lib/grading'
import type { LlmGrade } from '@/types/attempt'

const props = defineProps<{
  grade?: LlmGrade
  /** null: the exam states no points, graded on a 1-point scale and shown as a verdict */
  max: number | null
  pending?: string
  error?: string
  skipped?: SkipReason
}>()
defineEmits<{ regrade: [] }>()

const SKIPS: Partial<Record<SkipReason, string>> = {
  no_answer: 'No answer, not sent',
}
const skipText = computed(() => (props.skipped ? SKIPS[props.skipped] : undefined))
const shown = computed(
  () => props.pending !== undefined || !!props.error || !!props.grade || !!skipText.value,
)

const verdict = (p: number) => (p >= 1 ? '✓ correct' : p <= 0 ? '✗ wrong' : `◐ partly (${Math.round(p * 100)}%)`)
const points = computed(() => {
  const g = props.grade!
  if (props.max === null) return `${verdict(g.points)}${g.certain ? '' : ' · unsure'}`
  const p = g.certain
    ? formatPoints(g.points)
    : `${formatPoints(g.min)}–${formatPoints(g.max)}`
  return `${p} / ${formatPoints(props.max)} P${g.certain ? '' : ' · unsure'}`
})
const model = computed(() => props.grade!.model.split('/').pop())
const mark = (hit: number, max: number) => (hit <= 0 ? '✗' : hit >= max ? '✓' : '◐')
</script>

<template>
  <div v-if="shown" class="llm" data-llm>
    <div class="label">LLM</div>
    <template v-if="pending !== undefined">
      <p class="state">grading…</p>
      <p v-if="pending" class="thinking" data-thinking>{{ pending }}</p>
    </template>
    <p v-else-if="error" class="state bad">
      {{ error }}
      <button type="button" class="link" @click="$emit('regrade')">Retry</button>
    </p>
    <template v-else-if="grade">
      <div class="head">
        <span class="points">{{ points }}</span>
        <span class="meta"
          >{{ grade.basis === 'solution' ? 'from the solution' : 'own solution' }} · {{ model }}</span
        >
      </div>
      <ul class="rubric">
        <li v-for="(l, i) in grade.rubric" :key="i" data-rubric-line>
          <span class="mark" aria-hidden="true">{{ mark(l.hit, l.max) }}</span>
          <span class="item">{{ l.item }}</span>
          <span class="hit">{{ formatPoints(l.hit) }} / {{ formatPoints(l.max) }}</span>
          <span class="tag">{{ l.source === 'solution' ? 'guide' : 'inferred' }}</span>
          <span v-if="l.note" class="note">{{ l.note }}</span>
        </li>
      </ul>
      <p v-if="grade.feedback" class="feedback">Feedback: {{ grade.feedback }}</p>
      <button type="button" class="link" @click="$emit('regrade')">Re-grade</button>
    </template>
    <p v-else class="state">{{ skipText }}</p>
  </div>
</template>

<style scoped>
.llm {
  margin-top: var(--s3);
  padding: var(--s2) var(--s3);
  background: var(--paper);
  border: 1px solid var(--line);
}
.label {
  color: var(--mute);
  font-size: var(--fs-sm);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.head {
  display: flex;
  justify-content: space-between;
  gap: var(--s3);
  margin-top: var(--s1);
}
.points {
  font-weight: 500;
}
.meta,
.state,
.tag,
.note {
  color: var(--mute);
}
.state {
  margin: var(--s1) 0 0;
}
.bad {
  color: var(--bad);
}
.thinking {
  margin: var(--s1) 0 0;
  max-height: 6lh;
  overflow-y: auto;
  color: var(--mute);
  white-space: pre-wrap;
}
.rubric {
  list-style: none;
  margin: var(--s2) 0 0;
  padding: 0;
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  column-gap: var(--s3);
  row-gap: var(--s1);
}
.rubric li {
  display: contents;
}
.note {
  grid-column: 2 / -1;
  margin-top: -2px;
}
.hit {
  text-align: right;
}
.tag {
  font-size: var(--fs-sm);
  min-width: 4.5em;
}
.feedback {
  margin: var(--s2) 0 0;
  white-space: pre-wrap;
}
.link {
  margin-top: var(--s2);
  padding: 0 0 1px;
  font-size: var(--fs-sm);
  color: var(--mute);
  border-bottom: 1px solid var(--line);
}
.state .link {
  margin: 0 0 0 var(--s2);
}
@media (max-width: 600px) {
  .rubric {
    grid-template-columns: auto 1fr auto;
  }
  .tag {
    display: none;
  }
  .head {
    flex-direction: column;
    gap: 0;
  }
}
</style>
