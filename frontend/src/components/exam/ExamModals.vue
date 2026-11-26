<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Modal from '@/components/ui/Modal.vue'
import { useAttemptStore } from '@/stores/attempt'

const ATTENDANCE_SECONDS = 5

const store = useAttemptStore()
const route = useRoute()
const router = useRouter()
const remaining = ref(ATTENDANCE_SECONDS)
let timer: ReturnType<typeof setInterval> | null = null

function stop() {
  if (timer !== null) clearInterval(timer)
  timer = null
}

watch(
  () => store.modal,
  (m) => {
    stop()
    if (m !== 'attendance') return
    remaining.value = ATTENDANCE_SECONDS
    timer = setInterval(() => {
      remaining.value -= 1
      if (remaining.value <= 0) {
        stop()
        store.finishAttendance()
      }
    }, 1000)
  },
  { immediate: true },
)
onBeforeUnmount(stop)

async function handIn() {
  await store.handIn()
  // replace: browser Back must not return to the editable exam
  await router.replace({ name: 'results', params: { attemptId: route.params.attemptId as string } })
}
</script>

<template>
  <Modal :open="store.modal === 'attendance'" :dismissible="false">
    <h2>Attendance check</h2>
    <p>A tutor is checking your ID. Please wait.</p>
    <p class="count" aria-live="off">{{ remaining }}</p>
  </Modal>
  <Modal :open="store.modal === 'timeup'" :dismissible="false">
    <h2>Time is up</h2>
    <p>The exam has ended. Please hand in.</p>
    <div class="actions">
      <button class="primary" @click="handIn">Hand in</button>
      <button @click="store.extend()">Keep going</button>
    </div>
  </Modal>
  <Modal :open="store.modal === 'handin'" @close="store.cancelHandIn()">
    <h2>Hand in?</h2>
    <p>You can't change your answers afterwards.</p>
    <div class="actions">
      <button class="primary" @click="handIn">Hand in</button>
      <button @click="store.cancelHandIn()">Back to exam</button>
    </div>
  </Modal>
</template>

<style scoped>
h2 {
  margin: 0 0 var(--s3);
  font-size: var(--fs-lg);
  font-weight: 500;
}
p {
  margin: 0 0 var(--s4);
  color: var(--mute);
}
.count {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-lg);
  font-variant-numeric: tabular-nums;
}
.actions {
  display: flex;
  gap: var(--s4);
  align-items: baseline;
}
.primary {
  color: var(--ink);
  font-weight: 500;
  padding: 2px 0;
  border-bottom: 1px solid var(--ink);
}
</style>
