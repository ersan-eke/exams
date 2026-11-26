<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAttemptStore } from '@/stores/attempt'
import { includedTasks } from '@/lib/sheet'
import { isAnswered } from '@/lib/answers'
import type { Context, Task } from '@/types/exam'

const store = useAttemptStore()
const emit = defineEmits<{ collapse: []; pick: [] }>()
const hovered = ref<string | null>(null)

const tasks = computed(() =>
  store.exam && store.attempt ? includedTasks(store.exam.structure, store.attempt) : [],
)

const view = computed(() => store.attempt?.view)
const isSingle = (t: Task) => t.subtasks.length === 1 && t.subtasks[0]!.label === ''
const isExpanded = (t: Task) => view.value?.expandedTasks.includes(t.id) ?? false
const isShown = (id: string) => view.value?.shown.includes(id) ?? false
const answered = (id: string) => isAnswered(store.attempt?.answers[id])

function taskPoints(t: Task): string {
  if (t.points !== null) return String(t.points)
  const pts = t.subtasks.flatMap((s) => (s.points === null ? [] : [s.points]))
  return pts.length ? String(pts.reduce((a, b) => a + b, 0)) : ''
}

function jumpToContext(t: Task, c: Context) {
  const target = c.applies_from ?? t.subtasks[0]?.id
  if (!target) return
  store.showOnly(target)
  if (view.value?.folded.includes(c.id)) store.toggleFold(c.id)
  emit('pick')
}

function pick(id: string) {
  store.showOnly(id)
  emit('pick')
}
</script>

<template>
  <nav class="outline" aria-label="Exam outline">
    <div class="head">
      <span class="label">Outline</span>
      <button
        class="collapse"
        aria-label="Collapse outline"
        @click="emit('collapse')"
      >
        «
      </button>
    </div>
    <ul>
      <template v-for="t in tasks" :key="t.id">
        <li
          v-if="isSingle(t)"
          class="row task sub-single"
          :class="{ answered: answered(t.subtasks[0]!.id), shown: isShown(t.subtasks[0]!.id) }"
          :data-id="t.subtasks[0]!.id"
          tabindex="0"
          @click="pick(t.subtasks[0]!.id)"
          @keydown.enter.self="pick(t.subtasks[0]!.id)"
          @mouseenter="hovered = t.subtasks[0]!.id"
          @mouseleave="hovered = null"
          @focusin="hovered = t.subtasks[0]!.id"
          @focusout="hovered = null"
        >
          <span class="name"><span class="dot"></span>{{ t.number }} {{ t.title }}</span>
          <span class="end">
            <span class="pts">{{ taskPoints(t) }}</span>
            <button
              class="eye"
              :class="{
                ghost: !isShown(t.subtasks[0]!.id),
                visible: hovered === t.subtasks[0]!.id || isShown(t.subtasks[0]!.id),
              }"
              :aria-label="isShown(t.subtasks[0]!.id) ? 'Remove from sheet' : 'Add to sheet'"
              @click.stop="store.toggleShown(t.subtasks[0]!.id)"
            >
              {{ isShown(t.subtasks[0]!.id) ? '◉' : '◎' }}
            </button>
          </span>
        </li>
        <template v-else>
          <li
            class="row task"
            :data-id="t.id"
            :aria-expanded="isExpanded(t)"
            @click="store.toggleTask(t.id)"
          >
            <span class="name"
              ><button
                class="chev"
                :aria-label="isExpanded(t) ? 'Fold task' : 'Unfold task'"
                @click.stop="store.toggleTask(t.id)"
              >
                {{ isExpanded(t) ? '⌄' : '›' }}</button
              >{{ t.number }} {{ t.title }}</span
            >
            <span class="pts">{{ taskPoints(t) }}</span>
          </li>
          <template v-if="isExpanded(t)">
            <li
              v-for="c in t.context"
              :key="c.id"
              class="row context"
              :data-id="c.id"
              tabindex="0"
              @click="jumpToContext(t, c)"
              @keydown.enter.self="jumpToContext(t, c)"
            >
              <i>Context</i>
            </li>
            <li
              v-for="s in t.subtasks"
              :key="s.id"
              class="row sub"
              :class="{ answered: answered(s.id), shown: isShown(s.id) }"
              :data-id="s.id"
              tabindex="0"
              @click="pick(s.id)"
              @keydown.enter.self="pick(s.id)"
              @mouseenter="hovered = s.id"
              @mouseleave="hovered = null"
              @focusin="hovered = s.id"
              @focusout="hovered = null"
            >
              <span class="name"
                ><span class="dot"></span>{{ s.label || t.title || 'Question' }}</span
              >
              <span class="end">
                <span class="pts">{{ s.points ?? '' }}</span>
                <button
                  class="eye"
                  :class="{ ghost: !isShown(s.id), visible: hovered === s.id || isShown(s.id) }"
                  :aria-label="isShown(s.id) ? 'Remove from sheet' : 'Add to sheet'"
                  @click.stop="store.toggleShown(s.id)"
                >
                  {{ isShown(s.id) ? '◉' : '◎' }}
                </button>
              </span>
            </li>
          </template>
        </template>
      </template>
    </ul>
  </nav>
</template>

<style scoped>
.outline {
  padding: var(--s3) 0;
  font-size: 12px;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 16px 10px;
}
.collapse {
  color: var(--mute);
}
ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--s2);
  padding: 5px 16px 5px 38px;
  color: var(--mute);
  border-left: 2px solid transparent;
  cursor: pointer;
  user-select: none;
}
.row:hover {
  background: #fafaf8;
}
.row.task {
  padding-left: 14px;
  color: var(--ink);
}
.row.context {
  font-style: italic;
}
.name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chev {
  display: inline-block;
  width: 14px;
  color: var(--mute);
  text-align: left;
}
.end {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.pts {
  color: var(--mute);
  font-variant-numeric: tabular-nums;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  border: 1px solid #c9c8c2;
  display: inline-block;
  margin-right: 8px;
  vertical-align: middle;
}
.answered {
  color: var(--ink);
}
.answered .dot {
  background: var(--ink);
  border-color: var(--ink);
}
.row.shown {
  color: var(--ink);
  background: var(--soft);
  border-left-color: var(--ink);
}
.eye {
  margin-left: 6px;
  font-size: 12px;
  line-height: 1;
  color: var(--ink);
}
.eye.ghost {
  color: #c9c8c2;
}
/* mouse: the eye appears on hover/focus; touch and pen: always there */
.eye:not(.visible) {
  visibility: hidden;
}
@media (hover: none), (pointer: coarse) {
  .eye:not(.visible) {
    visibility: visible;
  }
  .eye {
    padding: 4px 6px;
    margin: -4px -6px -4px 0;
  }
}
</style>
