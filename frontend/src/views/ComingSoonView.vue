<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <div class="soon">
    <h2>{{ route.meta.title }}</h2>
    <p class="label">Coming soon</p>
  </div>
</template>

<style scoped>
.soon {
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: var(--s2);
}
h2 {
  font-weight: 500;
  font-size: var(--fs-lg);
}
</style>
