<script setup lang="ts">
import { formatClock } from '@/lib/clock'
import { formatPoints } from '@/lib/scoring'
import { formatDuration, type Group, type Summary } from '@/lib/stats'

defineProps<{ summary: Summary }>()

const avgScore = (g: Group) =>
  g.avgScore === null ? 'not graded' : `${formatPoints(g.avgScore)} / ${formatPoints(g.avgMax!)} P`
const pct = (p: { main: number; max: number }) => (p.max ? Math.round((p.main / p.max) * 100) : 0)
</script>

<template>
  <div class="stats">
    <div class="stat">
      <div class="v">{{ summary.exams }}</div>
      <div class="k">exams taken</div>
    </div>
    <div class="stat">
      <div class="v">{{ summary.questions }}</div>
      <div class="k">questions answered</div>
    </div>
    <div class="stat">
      <div class="v">{{ formatDuration(summary.timeMs) }}</div>
      <div class="k">time spent</div>
    </div>
  </div>

  <section class="points" data-section="points">
    <div class="label">Points</div>
    <template v-if="summary.points">
      <div class="big">{{ pct(summary.points) }} %</div>
      <div class="k">
        {{ formatPoints(summary.points.main) }} / {{ formatPoints(summary.points.max) }} P over
        {{ summary.points.graded }} graded exam{{ summary.points.graded === 1 ? '' : 's' }}
      </div>
    </template>
    <div v-else class="k">No graded exams yet.</div>
  </section>

  <slot />

  <section v-if="summary.mc || summary.long.length" class="groups" data-section="groups">
    <div class="label">Per question</div>
    <table>
      <thead>
        <tr>
          <th>Question</th>
          <th>Count</th>
          <th>Avg. time</th>
          <th>Avg. score</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="summary.mc" data-group="mc">
          <td>Multiple choice</td>
          <td>{{ summary.mc.count }}</td>
          <td>{{ formatClock(summary.mc.avgTimeMs) }}</td>
          <td>{{ avgScore(summary.mc) }}</td>
        </tr>
        <tr v-for="g in summary.long" :key="String(g.points)" :data-group="g.points ?? 'unknown'">
          <td>{{ g.points === null ? 'Points unknown' : `${formatPoints(g.points)} P question` }}</td>
          <td>{{ g.count }}</td>
          <td>{{ formatClock(g.avgTimeMs) }}</td>
          <td>{{ avgScore(g) }}</td>
        </tr>
      </tbody>
    </table>
  </section>
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
}
.k {
  color: var(--mute);
  margin-top: 4px;
  font-size: 12px;
}
section {
  margin-top: var(--s5);
}
.label {
  margin-bottom: var(--s2);
}
.big {
  font-size: 28px;
  font-weight: 300;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th {
  font-weight: 400;
  color: var(--mute);
  font-size: var(--fs-sm);
  text-align: left;
}
th,
td {
  padding: var(--s1) var(--s2) var(--s1) 0;
  border-bottom: 1px solid var(--line);
}
</style>
