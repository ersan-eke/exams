<script setup lang="ts">
defineProps<{ title: string; meta?: string; folded: boolean }>()
defineEmits<{ toggle: [] }>()
</script>

<template>
  <section class="fold">
    <button class="fold-bar" :aria-expanded="!folded" @click="$emit('toggle')">
      <span class="title"
        ><span class="chev" aria-hidden="true">{{ folded ? '›' : '⌄' }}</span>{{ title }}</span
      >
      <span v-if="meta" class="meta">{{ meta }}</span>
    </button>
    <div v-if="!folded" class="fold-body"><slot /></div>
  </section>
</template>

<style scoped>
.fold-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--s3);
  width: 100%;
  padding: var(--s2) var(--s3);
  border: 1px solid var(--line);
  background: var(--soft);
  font-size: var(--fs-sm);
  text-align: left;
}
.chev {
  display: inline-block;
  width: 14px;
  color: var(--mute);
}
.meta {
  color: var(--mute);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
