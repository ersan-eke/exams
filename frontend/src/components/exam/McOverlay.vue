<script setup lang="ts">
import { computed } from 'vue'
import type { McOption } from '@/types/exam'

const props = defineProps<{
  options: McOption[]
  regionIndex: number
  ticks: number[]
  readonly?: boolean
  /** outlined in red, e.g. the answer key while grading */
  marked?: number[]
}>()
const emit = defineEmits<{ toggle: [index: number] }>()

const PAD = 0.3
const clamp = (v: number) => Math.min(1, Math.max(0, v))
const pct = (v: number) => `${+(v * 100).toFixed(2)}%`

interface Hit {
  index: number
  text: string
  box: string
  /** the printed box, relative to the hit area */
  outline: string
  textBox: string | null
}

const hits = computed<Hit[]>(() => {
  const mine = props.options
    .map((o, index) => ({ o, index }))
    .filter(({ o }) => o.region === props.regionIndex)
  return mine.map(({ o, index }) => {
    const { x0, y0, x1, y1 } = o.bbox
    const w = x1 - x0
    const h = y1 - y0
    const left = clamp(x0 - w * PAD)
    const top = clamp(y0 - h * PAD)
    const right = clamp(x1 + w * PAD)
    const bottom = clamp(y1 + h * PAD)
    const rect = (l: number, t: number, r: number, b: number) =>
      `left: ${pct(l)}; top: ${pct(t)}; width: ${pct(r - l)}; height: ${pct(b - t)};`
    let textBox: string | null = null
    if (o.text.trim()) {
      // text runs from the box to the next box on the same row (or the image edge)
      const next = mine
        .map((m) => m.o.bbox)
        .filter((b) => b.x0 >= x1 && b.y0 < y1 && b.y1 > y0)
        .reduce((m, b) => Math.min(m, b.x0), 1)
      if (next > right) textBox = rect(right, top, next, bottom)
    }
    // a zero-size box (b === a) fills the hit area instead of giving NaN
    const inner = (v: number, a: number, b: number, fallback: number) =>
      b > a ? (v - a) / (b - a) : fallback
    const outline = rect(
      inner(x0, left, right, 0),
      inner(y0, top, bottom, 0),
      inner(x1, left, right, 1),
      inner(y1, top, bottom, 1),
    )
    return { index, text: o.text, box: rect(left, top, right, bottom), outline, textBox }
  })
})

function hit(index: number) {
  if (!props.readonly) emit('toggle', index)
}
</script>

<template>
  <div class="overlay" :class="{ readonly }">
    <template v-for="h in hits" :key="h.index">
      <span
        class="hit"
        :class="{ on: ticks.includes(h.index) }"
        :data-mc-box="h.index"
        :style="h.box"
        @click="hit(h.index)"
        ><span
          class="outline"
          :class="{ key: marked?.includes(h.index) }"
          data-mc-outline
          :style="h.outline"
        ></span
        ><span v-if="ticks.includes(h.index)" class="x">✕</span></span
      >
      <span
        v-if="h.textBox"
        class="hit text"
        :data-mc-text="h.index"
        :style="h.textBox"
        @click="hit(h.index)"
      ></span>
    </template>
  </div>
</template>

<style scoped>
.overlay {
  position: absolute;
  inset: 0;
}
.hit {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 2px;
  cursor: pointer;
  font-size: 15px;
  line-height: 1;
  font-weight: 600;
  color: var(--ink);
  transition: background 0.12s;
  container-type: size;
}
/* the cross follows the box size, so it fits small (read-only) crops too */
.x {
  font-size: min(15px, 60cqh);
}
/* some PDFs paint a white rect over the checkbox column; this keeps the box visible */
.outline {
  position: absolute;
  border: 1px solid var(--ink);
  pointer-events: none;
}
.outline.key {
  border-color: var(--bad);
  outline: 2px solid var(--bad);
  outline-offset: 1px;
}
/* touch keeps :hover after a tap, which would leave the row grey */
@media (hover: hover) {
  .hit:hover {
    background: rgba(28, 28, 28, 0.08);
  }
}
.readonly .hit {
  cursor: default;
  pointer-events: none;
}
</style>
