<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ open: boolean; dismissible?: boolean }>(), {
  dismissible: true,
})
const emit = defineEmits<{ close: [] }>()

const panel = ref<HTMLElement | null>(null)
let previous: HTMLElement | null = null

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

watch(
  () => props.open,
  async (open) => {
    if (open) {
      previous = document.activeElement as HTMLElement | null
      await nextTick()
      const first = panel.value?.querySelector<HTMLElement>(FOCUSABLE)
      ;(first ?? panel.value)?.focus()
    } else {
      previous?.focus()
      previous = null
    }
  },
)

function requestClose() {
  if (props.dismissible) emit('close')
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    requestClose()
    return
  }
  if (e.key !== 'Tab' || !panel.value) return
  const items = Array.from(panel.value.querySelectorAll<HTMLElement>(FOCUSABLE))
  if (items.length === 0) {
    e.preventDefault()
    return
  }
  const first = items[0]!
  const last = items[items.length - 1]!
  const active = document.activeElement
  if (e.shiftKey && (active === first || active === panel.value)) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && active === last) {
    e.preventDefault()
    first.focus()
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="backdrop" @mousedown.self="requestClose" @keydown="onKeydown">
      <div ref="panel" class="panel" role="dialog" aria-modal="true" tabindex="-1">
        <slot />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(255, 255, 255, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.panel {
  background: var(--white);
  border: 1px solid var(--line);
  padding: var(--s5);
  min-width: 320px;
  max-width: 90vw;
  outline: none;
}
</style>
