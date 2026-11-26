<script lang="ts">
import { ref } from 'vue'
import type { PenColor, Tools } from './PenTools.vue'

const COLORS: PenColor[] = [
  { css: '#1c1c1c', label: 'Black' },
  { css: '#1f56c4', label: 'Blue' },
  { css: '#e67e22', label: 'Orange' },
  // a marker this thin would be useless: it draws wider than the pen
  { css: 'rgba(255, 214, 0, 0.45)', label: 'Marker', scale: 4 },
]

/** shared by all subtasks, so a chosen pen stays chosen */
const tools = ref<Tools>({ erase: false, color: COLORS[0]!.css, penSize: 1, eraserSize: 1 })
</script>

<script setup lang="ts">
import { computed } from 'vue'
import AnswerSheet from './AnswerSheet.vue'
import PenTools, { penFor } from './PenTools.vue'
import { emptyPart } from '@/lib/answers'
import { answerParts } from '@/lib/sheet'
import { useAttemptStore } from '@/stores/attempt'
import { useSettingsStore } from '@/stores/settings'
import type { AnswerMode, AnswerPart } from '@/types/attempt'
import type { Subtask } from '@/types/exam'

const props = defineProps<{ subtask: Subtask }>()
const store = useAttemptStore()
const settings = useSettingsStore()

const MODES: { id: AnswerMode; label: string }[] = [
  { id: 'type', label: 'Text' },
  { id: 'draw', label: 'Draw' },
]

const answer = computed(() => store.attempt?.answers[props.subtask.id])
const parts = computed(() => answerParts(props.subtask))
const initial: AnswerMode =
  (answer.value?.mode ?? settings.defaultAnswerMode) === 'draw' ? 'draw' : 'type'
/** each part has its own Text / Draw switch */
const modes = ref<AnswerMode[]>(parts.value.map(() => initial))

function setMode(i: number, m: AnswerMode) {
  modes.value[i] = m
  store.setAnswer(props.subtask.id, { mode: m })
}

const part = (i: number): AnswerPart => answer.value?.parts[i] ?? emptyPart()
function setPart(i: number, patch: Partial<AnswerPart>) {
  const next = parts.value.map((_, k) => answer.value?.parts[k] ?? emptyPart())
  next[i] = { ...next[i]!, ...patch }
  store.setAnswer(props.subtask.id, { parts: next })
}

const pen = computed(() => penFor(tools.value, COLORS))
</script>

<template>
  <div class="answer">
    <div v-for="(p, i) in parts" :key="i" class="part">
      <AnswerSheet
        :exam-id="store.exam!.id"
        :part="p"
        :text="part(i).text"
        :strokes="part(i).strokes"
        :pen="modes[i] === 'draw' ? pen : null"
        @update:text="setPart(i, { text: $event })"
        @update:strokes="setPart(i, { strokes: $event })"
      />
      <div class="bar">
        <div class="modes" role="tablist" aria-label="Answer mode">
          <button
            v-for="m in MODES"
            :key="m.id"
            type="button"
            role="tab"
            class="mode"
            :class="{ on: modes[i] === m.id }"
            :aria-selected="modes[i] === m.id"
            @click="setMode(i, m.id)"
          >
            {{ m.label }}
          </button>
        </div>
        <PenTools
          v-if="modes[i] === 'draw'"
          v-model="tools"
          :colors="COLORS"
          @clear="setPart(i, { strokes: [] })"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.answer {
  margin-top: var(--s2);
}
.part + .part {
  margin-top: var(--s4);
}
.bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s2) var(--s5);
  margin-top: var(--s3);
  min-height: 24px;
}
.modes {
  display: flex;
  align-items: center;
  gap: var(--s4);
}
.mode {
  padding: 0 0 2px;
  font-size: var(--fs-sm);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--mute);
  border-bottom: 1px solid transparent;
}
.mode.on {
  color: var(--ink);
  border-bottom-color: var(--ink);
}
</style>
