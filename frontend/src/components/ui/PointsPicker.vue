<script setup lang="ts">
import { computed } from 'vue'
import { formatPoints } from '@/lib/scoring'

const props = defineProps<{
  max: number | null
  label?: string
  /** buttons to offer instead of 0..max in 0.5 steps */
  options?: number[]
  /** shown after each button's value, e.g. "P" */
  unit?: string
  /** a number field next to the buttons, for any other value */
  free?: boolean
}>()
const model = defineModel<number | undefined>()

/** 0..max in 0.5 steps, always ending at max itself (e.g. 2.25) */
const steps = computed(() => {
  if (props.options) return props.options
  const max = props.max
  if (max === null) return []
  const halves = Array.from({ length: Math.floor(max * 2) + 1 }, (_, i) => i / 2)
  return halves[halves.length - 1] === max ? halves : [...halves, max]
})

function onInput(e: Event) {
  const v = (e.target as HTMLInputElement).valueAsNumber
  if (Number.isFinite(v) && v >= 0) model.value = v
}
</script>

<template>
  <div class="picker" data-picker role="group" :aria-label="label ?? 'Points'">
    <template v-if="steps.length">
      <button
        v-for="p in steps"
        :key="p"
        type="button"
        class="step"
        :class="{ on: model === p }"
        :aria-pressed="model === p"
        @click="model = p"
      >
        {{ formatPoints(p) }}{{ unit ? ` ${unit}` : '' }}
      </button>
    </template>
    <input
      v-if="!steps.length || free"
      class="free"
      type="number"
      min="0"
      step="0.5"
      :aria-label="label ?? 'Points'"
      :placeholder="steps.length ? 'Other' : ''"
      :value="model !== undefined && !steps.includes(model) ? model : ''"
      @input="onInput"
    />
    <button
      v-if="model !== undefined"
      type="button"
      class="clear"
      data-clear
      @click="model = undefined"
    >
      Clear
    </button>
  </div>
</template>

<style scoped>
.picker {
  display: flex;
  flex-wrap: wrap;
}
.step {
  min-width: 34px;
  padding: 5px var(--s2);
  border: 1px solid var(--line);
  margin: 0 -1px -1px 0;
  font-size: var(--fs-sm);
  font-variant-numeric: tabular-nums;
  color: var(--mute);
}
.step.on {
  position: relative;
  border-color: var(--ink);
  color: var(--ink);
  background: var(--soft);
}
.clear {
  margin-left: var(--s2);
  padding: 5px 0;
  font-size: var(--fs-sm);
  color: var(--mute);
}
.step + .free {
  margin-left: var(--s2);
}
.free {
  width: 80px;
  padding: 5px var(--s2);
  border: 1px solid var(--line);
  font: inherit;
  font-variant-numeric: tabular-nums;
}
</style>
