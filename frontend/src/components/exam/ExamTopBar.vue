<script setup lang="ts">
import { useAttemptStore } from '@/stores/attempt'

const store = useAttemptStore()
</script>

<template>
  <header class="top">
    <span class="title">{{ store.exam?.title }}</span>
    <span class="clock" :class="{ over: store.isOvertime }" role="timer">{{
      store.clockText
    }}</span>
    <button class="handin" @click="store.requestHandIn()">Hand in</button>
  </header>
</template>

<style scoped>
.top {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: var(--s3);
  padding: var(--s3) 20px;
  padding-top: calc(var(--s3) + env(safe-area-inset-top, 0px));
  border-bottom: 1px solid var(--line);
}
.title {
  color: var(--mute);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.clock {
  font-size: var(--fs-lg);
  font-variant-numeric: tabular-nums;
}
.clock.over {
  color: var(--over);
}
.handin {
  justify-self: end;
  color: var(--ink);
  padding: 2px 0;
  border-bottom: 1px solid var(--line);
}
.handin:hover {
  border-bottom-color: var(--ink);
}
</style>
