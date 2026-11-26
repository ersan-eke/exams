<script setup lang="ts">
import { computed } from 'vue'
import { dayKey, formatDate, scoreText, type Row } from '@/lib/stats'

const props = defineProps<{ rows: Row[]; now?: number }>()

const WEEKS = 53

/** one cell per day, column = week (Sunday first), ending today */
const days = computed(() => {
  const today = new Date(props.now ?? Date.now())
  const byDay = new Map<string, Row[]>()
  for (const r of props.rows) {
    const k = dayKey(r.attempt.startedAt)
    byDay.set(k, [...(byDay.get(k) ?? []), r])
  }
  const count = (WEEKS - 1) * 7 + today.getDay() + 1
  return Array.from({ length: count }, (_, i) => {
    // day-of-month arithmetic keeps local midnight across DST changes
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (count - 1 - i))
    const rows = byDay.get(dayKey(d.getTime())) ?? []
    const label = [formatDate(d.getTime()), ...rows.map((r) => `${r.exam.title} · ${scoreText(r)}`)]
    return { key: dayKey(d.getTime()), level: Math.min(rows.length, 3), label: label.join('\n') }
  })
})
</script>

<template>
  <div class="activity">
    <div class="grid" role="img" aria-label="Days with practiced exams over the last year">
      <span
        v-for="d in days"
        :key="d.key"
        class="day"
        :class="`l${d.level}`"
        :data-day="d.key"
        :title="d.label"
      ></span>
    </div>
  </div>
</template>

<style scoped>
.activity {
  overflow-x: auto;
}
.grid {
  display: grid;
  grid-template-rows: repeat(7, 10px);
  grid-auto-flow: column;
  grid-auto-columns: 10px;
  gap: 3px;
  width: max-content;
}
.day {
  background: var(--soft);
  border: 1px solid var(--line);
}
.l1 {
  background: #c9c8c3;
}
.l2 {
  background: #8a8a85;
}
.l3 {
  background: var(--ink);
}
</style>
