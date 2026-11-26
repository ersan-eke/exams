<script setup lang="ts">
import { computed } from 'vue'
import CropImage from '@/components/ui/CropImage.vue'
import DrawCanvas, { type Pen } from './DrawCanvas.vue'
import type { SheetPart } from '@/lib/sheet'
import type { Stroke } from '@/types/attempt'

/**
 * One answer part's crops with the answer on them, like a filled-in PDF: the text field sits in
 * the printed answer box (or below the crops when none was found), the drawing covers everything.
 * With a pen the drawing takes the input, otherwise the text field (unless readonly).
 */
const props = defineProps<{
  examId: string
  part: SheetPart
  text: string
  strokes: Stroke[]
  pen?: Pen | null
  readonly?: boolean
}>()
const emit = defineEmits<{ 'update:text': [string]; 'update:strokes': [Stroke[]] }>()

const pct = (v: number) => `${+(v * 100).toFixed(2)}%`
const box = computed(() => {
  const b = props.part.box
  if (!b) return null
  const { x0, y0, x1, y1 } = b.bbox
  return {
    region: b.region,
    style: { left: pct(x0), top: pct(y0), width: pct(x1 - x0), height: pct(y1 - y0) },
  }
})
const onText = (e: Event) => emit('update:text', (e.target as HTMLTextAreaElement).value)
</script>

<template>
  <div class="sheet" :class="{ drawing: !!pen }">
    <div v-for="c in part.crops" :key="c.name" class="crop-wrap">
      <CropImage :exam-id="examId" variant="blank" :name="c.name" />
      <textarea
        v-if="box?.region === c.regionIndex"
        class="text in-box"
        :style="box.style"
        aria-label="Your answer"
        :readonly="readonly"
        :value="text"
        @input="onText"
      />
    </div>
    <textarea
      v-if="!box"
      class="text below"
      aria-label="Your answer"
      :readonly="readonly"
      :value="text"
      @input="onText"
    />
    <DrawCanvas
      :strokes="strokes"
      :pen="readonly ? null : pen"
      @update:strokes="emit('update:strokes', $event)"
    />
  </div>
</template>

<style scoped>
.sheet {
  position: relative;
}
.crop-wrap {
  position: relative;
}
.crop-wrap + .crop-wrap :deep(.crop) {
  border-top: 0;
}
.text {
  display: block;
  resize: none;
  padding: var(--s2) var(--s3);
  font: inherit;
  font-size: var(--fs-lg);
  color: var(--ink);
  background: transparent;
  border: 0;
  border-radius: 0;
}
.text:focus {
  outline: 1px solid var(--ink);
  outline-offset: -1px;
}
.in-box {
  position: absolute;
}
/* no printed box found: a sheet-wide box under the crops */
.below {
  width: 100%;
  aspect-ratio: 3 / 1;
  background: var(--white);
  border: 1px solid var(--line);
  border-top: 0;
}
.drawing .text {
  pointer-events: none;
}
</style>
