<script setup lang="ts">
import type { McOption } from '@/types/exam'

defineProps<{ options: McOption[]; ticks: number[] }>()
const emit = defineEmits<{ toggle: [index: number] }>()
</script>

<template>
  <div class="list">
    <button
      v-for="(o, i) in options"
      :key="i"
      type="button"
      class="opt"
      :class="{ on: ticks.includes(i) }"
      @click="emit('toggle', i)"
    >
      <template v-if="ticks.includes(i)">✕ </template>{{ o.text }}
    </button>
  </div>
</template>

<style scoped>
.list {
  display: flex;
  flex-direction: column;
  gap: var(--s1);
  margin-top: var(--s2);
}
.opt {
  text-align: left;
  padding: var(--s1) var(--s2);
  border: 1px solid var(--line);
  background: var(--white);
  color: var(--ink);
  font: inherit;
  cursor: pointer;
}
.opt.on {
  border-color: var(--ink);
  font-weight: 600;
}
</style>
