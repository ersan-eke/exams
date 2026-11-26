<script lang="ts">
import type { Pen } from './DrawCanvas.vue'

const PEN_SIZES = [0.002, 0.004, 0.008]
const ERASER_SIZES = [0.015, 0.035, 0.07]
const SIZE_LABELS = ['Small', 'Medium', 'Large']

export interface PenColor {
  css: string
  label: string
  /** line width multiplier, e.g. a marker draws wider than the pen */
  scale?: number
}

export interface Tools {
  erase: boolean
  color: string
  penSize: number
  eraserSize: number
}

export function penFor(t: Tools, colors: PenColor[]): Pen {
  if (t.erase) return { erase: true, color: '#000', size: ERASER_SIZES[t.eraserSize]! }
  const scale = colors.find((c) => c.css === t.color)?.scale ?? 1
  return { erase: false, color: t.color, size: PEN_SIZES[t.penSize]! * scale }
}
</script>

<script setup lang="ts">
import { computed } from 'vue'

/** Pen / Eraser / Clear, three sizes each, and the pen colors */
defineProps<{ colors: PenColor[] }>()
const tools = defineModel<Tools>({ required: true })
const emit = defineEmits<{ clear: [] }>()

const set = (patch: Partial<Tools>) => (tools.value = { ...tools.value, ...patch })
const sizes = computed(() => (tools.value.erase ? ERASER_SIZES : PEN_SIZES))
const sizeOn = (i: number) =>
  (tools.value.erase ? tools.value.eraserSize : tools.value.penSize) === i
const pickSize = (i: number) => set(tools.value.erase ? { eraserSize: i } : { penSize: i })
</script>

<template>
  <div class="tools" role="toolbar" aria-label="Drawing tools">
    <button
      type="button"
      class="mode"
      :class="{ on: !tools.erase }"
      :aria-pressed="!tools.erase"
      @click="set({ erase: false })"
    >
      Pen
    </button>
    <button
      type="button"
      class="mode"
      :class="{ on: tools.erase }"
      :aria-pressed="tools.erase"
      @click="set({ erase: true })"
    >
      Eraser
    </button>
    <button type="button" class="mode" @click="emit('clear')">Clear</button>
    <span class="sep" />
    <button
      v-for="(_, k) in sizes"
      :key="`size${k}`"
      type="button"
      class="size"
      :class="{ on: sizeOn(k), eraser: tools.erase }"
      :aria-pressed="sizeOn(k)"
      :aria-label="`${SIZE_LABELS[k]} ${tools.erase ? 'eraser' : 'pen'}`"
      @click="pickSize(k)"
    >
      <span class="dot" :style="{ width: `${4 + k * 4}px`, height: `${4 + k * 4}px` }" />
    </button>
    <template v-if="!tools.erase">
      <span class="sep" />
      <button
        v-for="c in colors"
        :key="c.label"
        type="button"
        class="color"
        :class="{ on: tools.color === c.css }"
        :aria-pressed="tools.color === c.css"
        :aria-label="c.label"
        :title="c.label"
        @click="set({ color: c.css, erase: false })"
      >
        <span class="swatch" :style="{ background: c.css }" />
      </button>
    </template>
  </div>
</template>

<style scoped>
.tools {
  display: flex;
  align-items: center;
  gap: var(--s3);
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
.sep {
  width: 1px;
  height: 14px;
  background: var(--line);
}
.size,
.color {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border: 1px solid transparent;
  border-radius: 50%;
}
.size.on,
.color.on {
  border-color: var(--ink);
}
.dot {
  border-radius: 50%;
  background: var(--ink);
}
.size.eraser .dot {
  background: var(--white);
  border: 1px solid var(--ink);
}
.swatch {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 1px solid var(--line);
}
</style>
