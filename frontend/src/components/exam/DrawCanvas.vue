<script lang="ts">
/** what the next stroke looks like; size = line width ÷ canvas width */
export interface Pen {
  erase: boolean
  color: string
  size: number
}
</script>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Stroke } from '@/types/attempt'
import { paintStroke } from '@/lib/strokes'

/** Transparent layer filling its positioned parent. Without a pen it only shows the strokes. */
const props = defineProps<{ pen?: Pen | null }>()
const strokes = defineModel<Stroke[]>('strokes', { required: true })

const canvas = ref<HTMLCanvasElement | null>(null)
let current: Stroke | null = null
let activePointer: number | null = null
let observer: ResizeObserver | null = null

function redraw() {
  const el = canvas.value
  const c = el?.getContext('2d')
  if (!el || !c) return
  const w = el.clientWidth
  const h = el.clientHeight
  const dpr = window.devicePixelRatio || 1
  if (w > 0 && (el.width !== Math.round(w * dpr) || el.height !== Math.round(h * dpr))) {
    el.width = Math.round(w * dpr)
    el.height = Math.round(h * dpr)
  }
  c.setTransform(1, 0, 0, 1, 0, 0)
  c.clearRect(0, 0, el.width, el.height)
  c.scale(dpr, dpr)
  const all = current ? [...strokes.value, current] : strokes.value
  for (const s of all) paintStroke(c, s, w, h)
}

function point(e: PointerEvent): [number, number] {
  const r = canvas.value!.getBoundingClientRect()
  const x = r.width > 0 ? (e.clientX - r.left) / r.width : 0
  const y = r.height > 0 ? (e.clientY - r.top) / r.height : 0
  return [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))]
}

function down(e: PointerEvent) {
  const pen = props.pen
  if (!pen || e.isPrimary === false || activePointer !== null) return
  activePointer = e.pointerId
  canvas.value?.setPointerCapture?.(e.pointerId)
  current = { points: [point(e)], erase: pen.erase, color: pen.color, size: pen.size }
  redraw()
}

function move(e: PointerEvent) {
  if (!current || e.pointerId !== activePointer) return
  current.points.push(point(e))
  redraw()
}

function up(e: PointerEvent) {
  if (!current || e.pointerId !== activePointer) return
  current.points.push(point(e))
  const done = current
  current = null
  activePointer = null
  canvas.value?.releasePointerCapture?.(e.pointerId)
  strokes.value = [...strokes.value, done]
}

onMounted(() => {
  redraw()
  if (typeof ResizeObserver !== 'undefined' && canvas.value) {
    observer = new ResizeObserver(redraw)
    observer.observe(canvas.value)
  }
})
onBeforeUnmount(() => observer?.disconnect())
watch(strokes, redraw, { flush: 'post' })
</script>

<template>
  <canvas
    ref="canvas"
    class="surface"
    :class="{ active: !!pen }"
    @pointerdown="down"
    @pointermove="move"
    @pointerup="up"
    @pointercancel="up"
  />
</template>

<style scoped>
.surface {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  /* the marker tints the page like a highlighter instead of veiling it */
  mix-blend-mode: multiply;
  pointer-events: none;
}
.surface.active {
  pointer-events: auto;
  touch-action: none;
  cursor: crosshair;
}
</style>
