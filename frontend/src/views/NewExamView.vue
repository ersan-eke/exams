<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { pulled } from '@/lib/sync'
import { useRouter } from 'vue-router'
import PdfDropZone from '@/components/ui/PdfDropZone.vue'
import { uploadErrorMessage } from '@/lib/api'
import { useAccountStore } from '@/stores/account'
import { useLibraryStore } from '@/stores/library'
import type { Attempt, StoredExam } from '@/types/attempt'

const library = useLibraryStore()
const account = useAccountStore()
const router = useRouter()

const reading = ref(false)
const error = ref('')
const runningAttempt = ref<Attempt>()
const recent = ref<{ exam: StoredExam; latest: Attempt | undefined }[]>([])

async function load() {
  runningAttempt.value = await library.running()
  recent.value = await library.recent(5)
}
onMounted(load)
watch(pulled, load)

async function upload(file: File) {
  error.value = ''
  reading.value = true
  try {
    const examId = await library.importUpload(file)
    await router.push({ name: 'exam-settings', params: { examId } })
  } catch (e) {
    error.value = uploadErrorMessage(e)
  } finally {
    reading.value = false
  }
}

function target(item: { exam: StoredExam; latest: Attempt | undefined }) {
  const { exam, latest } = item
  if (latest?.status === 'handed_in') return { name: 'results', params: { attemptId: latest.id } }
  if (latest?.status === 'running') return { name: 'exam', params: { attemptId: latest.id } }
  return { name: 'exam-settings', params: { examId: exam.id } }
}
</script>

<template>
  <div class="new">
    <PdfDropZone
      class="drop"
      heading="Drop an old exam here"
      :hint="`PDF · exam or solution · ${account.user ? 'kept in your account' : 'stays on this device'}`"
      :busy="reading"
      busy-text="Reading the exam…"
      :error="error"
      @file="upload"
    />

    <RouterLink
      v-if="runningAttempt"
      class="continue"
      :to="{ name: 'exam', params: { attemptId: runningAttempt.id } }"
      >Continue exam</RouterLink
    >

    <section v-if="recent.length" class="recent">
      <div class="label">Recent</div>
      <RouterLink v-for="item in recent" :key="item.exam.id" :to="target(item)">{{
        item.exam.title
      }}</RouterLink>
    </section>
  </div>
</template>

<style scoped>
.new {
  width: 100%;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--s4);
  padding: var(--s5);
}
.drop {
  width: 360px;
  max-width: 100%;
}
.continue {
  padding: 9px var(--s4);
  border: 1px solid var(--ink);
  text-decoration: none;
}
.recent {
  width: 360px;
  max-width: 100%;
  display: flex;
  flex-direction: column;
}
.recent .label {
  padding-bottom: var(--s2);
}
.recent a {
  padding: var(--s2) 0;
  border-top: 1px solid var(--line);
  text-decoration: none;
}
</style>
