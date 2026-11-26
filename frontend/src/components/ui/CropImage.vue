<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { getImage, type ImageVariant } from '@/lib/db'

const props = defineProps<{ examId: string; variant: ImageVariant; name: string }>()

const src = ref<string | null>(null)
let alive = true

function release() {
  if (src.value) URL.revokeObjectURL(src.value)
  src.value = null
}

watch(
  () => [props.examId, props.variant, props.name] as const,
  async ([examId, variant, name]) => {
    let blob: Blob | undefined
    try {
      blob = await getImage(examId, variant, name)
    } catch {
      blob = undefined // keep the placeholder
    }
    // props may have changed while loading
    if (!alive || examId !== props.examId || variant !== props.variant || name !== props.name) return
    release()
    if (blob) src.value = URL.createObjectURL(blob)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  alive = false
  release()
})
</script>

<template>
  <img v-if="src" class="crop" :src="src" alt="" />
  <div v-else class="crop placeholder"></div>
</template>

<style scoped>
.crop {
  display: block;
  width: 100%;
  border: 1px solid var(--line);
  background: var(--white);
}
.crop + .crop {
  border-top: 0;
}
.placeholder {
  aspect-ratio: 4 / 1;
}
</style>
