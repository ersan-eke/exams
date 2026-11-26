<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ heading: string; hint: string; busy: boolean; busyText: string; error?: string; multiple?: boolean }>()
const emit = defineEmits<{ file: [file: File] }>()

const dragging = ref(false)
const input = ref<HTMLInputElement>()

function onChange(e: Event) {
  const el = e.target as HTMLInputElement
  const files = [...(el.files ?? [])]
  el.value = ''
  files.forEach((f) => emit('file', f))
}

function onDrop(e: DragEvent) {
  dragging.value = false
  const files = [...(e.dataTransfer?.files ?? [])]
  files.slice(0, props.multiple ? undefined : 1).forEach((f) => emit('file', f))
}
</script>

<template>
  <div
    class="drop"
    :class="{ dragging }"
    @dragover.prevent="dragging = true"
    @dragleave="dragging = false"
    @drop.prevent="onDrop"
  >
    <template v-if="busy">
      <h4>{{ busyText }}</h4>
    </template>
    <template v-else>
      <h4>{{ heading }}</h4>
      <p>{{ hint }}</p>
      <button type="button" class="btn" @click="input?.click()">{{ multiple ? 'Choose files' : 'Choose file' }}</button>
      <p v-if="error" class="error" role="alert"><slot name="error">{{ error }}</slot></p>
    </template>
    <input ref="input" type="file" accept="application/pdf" :multiple="multiple" hidden @change="onChange" />
  </div>
</template>

<style scoped>
.drop {
  border: 1px dashed var(--drop-line);
  padding: var(--s6) var(--s5);
  text-align: center;
  background: var(--paper);
}
.drop.dragging {
  background: var(--soft);
  border-color: var(--ink);
}
h4 {
  font-weight: 500;
  font-size: var(--fs-lg);
  margin: 0 0 6px;
  letter-spacing: 0.01em;
}
p {
  color: var(--mute);
  margin: 0 0 var(--s4);
}
.error {
  color: var(--over);
  margin: var(--s4) 0 0;
}
.btn {
  display: inline-block;
  padding: 9px var(--s4);
  border: 1px solid var(--ink);
}
</style>
