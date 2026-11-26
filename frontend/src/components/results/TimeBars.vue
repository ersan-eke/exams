<script setup lang="ts">
import { computed, ref } from 'vue'
import { formatClock } from '@/lib/clock'
import { formatPoints } from '@/lib/scoring'
import { includedTasks } from '@/lib/sheet'
import type { Attempt, StoredExam } from '@/types/attempt'

const props = defineProps<{
  attempt: Attempt
  exam: StoredExam
  /** per subtask id, once graded: adds a points column and the correct / incorrect grouping */
  points?: Record<string, { main: number; max: number | null }>
}>()
const open = ref(false)
const sort = ref<'task' | 'asc' | 'desc'>('desc')
const view = ref<'bars' | 'chart'>('bars')
const group = ref<'subtask' | 'question' | 'result'>('subtask')

const SORTS = [
  { key: 'task', label: 'exam order' },
  { key: 'asc', label: 'time ↑' },
  { key: 'desc', label: 'time ↓' },
] as const

const GROUPS = computed(() => [
  { key: 'subtask', label: 'all subtasks' } as const,
  { key: 'question', label: 'by question' } as const,
  ...(props.points ? [{ key: 'result', label: 'correct / incorrect' } as const] : []),
])

interface Pts {
  got: number
  max: number | null
}
/** full points, or any points when the max is unknown */
const isCorrect = (p: Pts) => (p.max !== null ? p.got >= p.max : p.got > 0)
const sumPts = (list: (Pts | undefined)[]): Pts | undefined =>
  list.every((p) => p)
    ? {
        got: list.reduce((sum, p) => sum + p!.got, 0),
        max: list.every((p) => p!.max !== null) ? list.reduce((sum, p) => sum + p!.max!, 0) : null,
      }
    : undefined

const HOT = 2

const rows = computed(() => {
  const spent = (id: string) =>
    (props.attempt.time[id]?.main ?? 0) + (props.attempt.time[id]?.over ?? 0)
  const pts = (id: string): Pts | undefined => {
    const p = props.points?.[id]
    return p && { got: p.main, max: p.max }
  }
  const tasks = includedTasks(props.exam.structure, props.attempt)
  const list =
    group.value === 'question'
      ? tasks.map((t) => ({
          id: t.id,
          label: t.number,
          ms: t.subtasks.reduce((sum, s) => sum + spent(s.id), 0),
          pts: sumPts(t.subtasks.map((s) => pts(s.id))),
        }))
      : tasks.flatMap((t) =>
          t.subtasks.map((s) => ({
            id: s.id,
            label: s.label === '' ? t.number : `${t.number} ${s.label}`,
            ms: spent(s.id),
            pts: pts(s.id),
          })),
        )
  // hot = the HOT slowest subtasks, whatever order is displayed
  const byTime = [...list].sort((a, b) => b.ms - a.ms)
  const hot = new Set(
    byTime
      .slice(0, HOT)
      .filter((r) => r.ms > 0)
      .map((r) => r.id),
  )
  const max = byTime[0]?.ms || 1
  const ordered = sort.value === 'task' ? list : sort.value === 'desc' ? byTime : byTime.reverse()
  return ordered.map((r) => ({ ...r, pct: Math.round((r.ms / max) * 100), hot: hot.has(r.id) }))
})

const sections = computed(() =>
  group.value === 'result'
    ? [
        { title: 'Correct', rows: rows.value.filter((r) => r.pts && isCorrect(r.pts)) },
        { title: 'Incorrect', rows: rows.value.filter((r) => !r.pts || !isCorrect(r.pts)) },
      ].filter((sec) => sec.rows.length)
    : [{ title: null, rows: rows.value }],
)

const ptsText = (p: Pts | undefined) =>
  p ? `${formatPoints(p.got)}${p.max !== null ? ` / ${formatPoints(p.max)}` : ''} P` : ''

const maxMs = computed(() => Math.max(0, ...rows.value.map((r) => r.ms)))
</script>

<template>
  <div class="bars-wrap">
    <p class="toggle">
      Time breakdown &nbsp;<button type="button" @click="open = !open">
        {{ open ? 'hide' : 'show' }}
      </button>
    </p>
    <template v-if="open">
      <div class="controls">
        <span class="sorts">
          <button
            v-for="s in SORTS"
            :key="s.key"
            type="button"
            class="sort"
            :class="{ on: sort === s.key }"
            :aria-pressed="sort === s.key"
            @click="sort = s.key"
          >
            {{ s.label }}
          </button>
          <span class="sep" aria-hidden="true"></span>
          <button
            v-for="g in GROUPS"
            :key="g.key"
            type="button"
            class="sort group"
            :class="{ on: group === g.key }"
            :aria-pressed="group === g.key"
            @click="group = g.key"
          >
            {{ g.label }}
          </button>
        </span>
        <span class="views">
          <button
            type="button"
            class="view"
            :class="{ on: view === 'bars' }"
            :aria-pressed="view === 'bars'"
            aria-label="Bar list"
            title="Bar list"
            @click="view = 'bars'"
          >
            <svg viewBox="0 0 14 14" aria-hidden="true"><path d="M1 2h12M1 7h8M1 12h10" /></svg>
          </button>
          <button
            type="button"
            class="view"
            :class="{ on: view === 'chart' }"
            :aria-pressed="view === 'chart'"
            aria-label="Column chart"
            title="Column chart"
            @click="view = 'chart'"
          >
            <svg viewBox="0 0 14 14" aria-hidden="true"><path d="M2 13V5M7 13V1M12 13V8" /></svg>
          </button>
        </span>
      </div>

      <div v-if="view === 'bars'" class="bars">
        <div
          v-for="sec in sections"
          :key="sec.title ?? ''"
          class="section"
          :data-section-title="sec.title"
        >
          <div v-if="sec.title" class="sec-title label">{{ sec.title }}</div>
          <div v-for="r in sec.rows" :key="r.id" class="row" :class="{ pts: !!points }">
            <span class="n">{{ r.label }}</span>
            <span class="track"
              ><span class="b" :class="{ hot: r.hot }" :style="{ width: r.pct + '%' }"></span
            ></span>
            <span class="t">{{ formatClock(r.ms) }}</span>
            <span v-if="points" class="p" :class="r.pts && (isCorrect(r.pts) ? 'good' : 'bad')">{{
              ptsText(r.pts)
            }}</span>
          </div>
        </div>
      </div>

      <div v-else class="chart">
        <div class="y">
          <span>{{ formatClock(maxMs) }}</span>
          <span>{{ formatClock(maxMs / 2) }}</span>
          <span>00:00</span>
        </div>
        <div class="plot">
          <div
            v-for="r in sections.flatMap((sec) => sec.rows)"
            :key="r.id"
            class="col"
            :title="`${r.label}: ${formatClock(r.ms)}${r.pts ? ' · ' + ptsText(r.pts) : ''}`"
          >
            <span class="area"
              ><span class="c" :class="{ hot: r.hot }" :style="{ height: r.pct + '%' }"></span
            ></span>
            <span class="n">{{ r.label }}</span>
            <span v-if="r.pts" class="n p" :class="isCorrect(r.pts) ? 'good' : 'bad'">{{
              formatPoints(r.pts.got)
            }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.toggle {
  margin: 22px 0 10px;
  color: var(--mute);
}
.toggle button {
  font: inherit;
  color: var(--ink);
  font-weight: 500;
  background: none;
  border: 0;
  border-bottom: 1px solid var(--ink);
  padding: 0;
  cursor: pointer;
}
.controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.sorts {
  display: flex;
  gap: 12px;
}
.sort,
.view {
  font: inherit;
  color: var(--mute);
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
}
.sort.on {
  color: var(--ink);
  border-bottom: 1px solid var(--ink);
}
.sep {
  width: 1px;
  background: var(--line);
}
.views {
  display: flex;
  gap: 4px;
}
.view {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border: 1px solid transparent;
}
.view.on {
  color: var(--ink);
  border-color: var(--line);
}
.view svg {
  width: 12px;
  height: 12px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
}
.row {
  display: grid;
  grid-template-columns: 54px 1fr 50px;
  gap: 10px;
  align-items: center;
  margin-bottom: 6px;
}
.row.pts {
  grid-template-columns: 54px 1fr 50px 64px;
}
.n {
  color: var(--mute);
}
.p {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.good {
  color: var(--good);
}
.bad {
  color: var(--bad);
}
.sec-title {
  margin: 10px 0 6px;
}
.t {
  color: var(--mute);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.b {
  display: block;
  height: 6px;
  background: #d9d8d2;
}
.b.hot,
.c.hot {
  background: var(--ink);
}
.chart {
  display: flex;
  gap: 8px;
}
.y {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: 140px;
  color: var(--mute);
  font-size: var(--fs-sm);
  font-variant-numeric: tabular-nums;
  text-align: right;
  /* lift labels so "00:00" sits on the baseline */
  transform: translateY(-0.5em);
}
.plot {
  flex: 1;
  display: flex;
  gap: 6px;
  overflow-x: auto;
}
.col {
  flex: 1 0 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.area {
  display: flex;
  align-items: flex-end;
  width: 100%;
  height: 140px;
  border-bottom: 1px solid var(--line);
}
.c {
  display: block;
  width: 100%;
  background: #d9d8d2;
}
.col .n {
  margin-top: 4px;
  font-size: var(--fs-sm);
  white-space: nowrap;
}
</style>
