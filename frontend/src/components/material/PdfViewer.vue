<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import * as pdfjs from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import 'pdfjs-dist/web/pdf_viewer.css'

const props = defineProps<{ url: string; page: number; terms: string }>()
const emit = defineEmits<{ error: [] }>()

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

const canvas = ref<HTMLCanvasElement>()
const textBox = ref<HTMLDivElement>()
let task: pdfjs.PDFDocumentLoadingTask | null = null
let pdf: pdfjs.PDFDocumentProxy | null = null
let rendering: pdfjs.RenderTask | null = null
let loaded = ''
let drawing = 0

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
// shortcut: words of 1-2 letters are skipped so "is"/"a" from a question stay plain (also loses "IP"); plain substring match on the query words; the server's fuzzy endings (domaene / domaenen) are not mirrored, upgrade if misses show
function highlighter(terms: string) {
  const words = [...new Set(terms.toLowerCase().split(/[^\p{L}\p{N}-]+/u).filter((w) => w.length > 2))]
  return words.length ? new RegExp(`(${words.map(escape).join('|')})`, 'giu') : null
}

function mark(span: HTMLElement, re: RegExp) {
  const text = span.textContent ?? ''
  if (!re.test(text)) return
  re.lastIndex = 0
  span.replaceChildren(
    ...text.split(re).map((part, i) => {
      if (i % 2 === 0) return document.createTextNode(part)
      const m = document.createElement('mark')
      m.textContent = part
      return m
    }),
  )
}

async function draw() {
  const run = ++drawing
  try {
    if (loaded !== props.url) {
      // forget the old document before destroying its task, so a later draw never reuses a destroyed one
      pdf = null
      loaded = ''
      task?.destroy().catch(() => {})
      const mine = (task = pdfjs.getDocument({ url: props.url }))
      const next = await mine.promise
      if (run !== drawing) {
        mine.destroy().catch(() => {})
        return
      }
      pdf = next
      loaded = props.url
    }
    const p = await pdf!.getPage(Math.min(Math.max(1, props.page), pdf!.numPages))
    if (run !== drawing || !canvas.value || !textBox.value) return
    // pdf.js rejects a second render on a canvas still being drawn, and resizing it would clear the old one mid-draw
    if (rendering) {
      rendering.cancel()
      await rendering.promise.catch(() => {})
      if (run !== drawing) return
    }
    const base = p.getViewport({ scale: 1 })
    // shortcut: sized once from the parent's width, no re-render on window resize; add a ResizeObserver if it matters
    const width = canvas.value.parentElement?.clientWidth || base.width
    const viewport = p.getViewport({ scale: width / base.width })
    const ratio = window.devicePixelRatio || 1
    const c = canvas.value
    c.width = viewport.width * ratio
    c.height = viewport.height * ratio
    c.style.width = `${viewport.width}px`
    c.style.height = `${viewport.height}px`
    textBox.value.style.setProperty('--total-scale-factor', String(viewport.scale))
    textBox.value.replaceChildren()
    const mine = (rendering = p.render({ canvas: c, viewport, transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0] }))
    await mine.promise
    if (rendering === mine) rendering = null
    const layer = new pdfjs.TextLayer({ textContentSource: p.streamTextContent(), container: textBox.value, viewport })
    await layer.render()
    const re = highlighter(props.terms)
    if (run === drawing && re) layer.textDivs.forEach((d) => mark(d, re))
  } catch {
    // shortcut: every failure (network, parse, render) shows the same "not found" note; split by error type if users get confused
    if (run === drawing) emit('error')
  }
}

watch(() => [props.url, props.page, props.terms], draw, { flush: 'post' })
// the canvas exists once the parent has rendered it
watch(canvas, (c) => c && draw(), { once: true })
onBeforeUnmount(() => {
  drawing++
  rendering?.cancel()
  task?.destroy().catch(() => {})
})
</script>

<template>
  <div class="pdf">
    <canvas ref="canvas" />
    <div ref="textBox" class="textLayer" />
  </div>
</template>

<style scoped>
.pdf {
  position: relative;
  width: 100%;
  border: 1px solid var(--line);
  overflow: auto;
}
.pdf canvas {
  display: block;
}
.textLayer :deep(mark) {
  background: rgb(255 214 0 / 0.45);
  color: transparent;
  border-radius: 2px;
}
</style>
