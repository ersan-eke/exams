<script setup lang="ts">
import { ref } from 'vue'
import Modal from '@/components/ui/Modal.vue'
import { GradeError, gradeErrorMessage, type GradePart, type GradeRequest } from '@/lib/grading'

/** dev-only: shows exactly what one grading request sends to the model */
const props = defineProps<{ build: () => Promise<GradeRequest | null> }>()

const open = ref(false)
const loading = ref(false)
const request = ref<GradeRequest | null>(null)
const error = ref('')

async function show() {
  open.value = true
  loading.value = true
  error.value = ''
  request.value = null
  try {
    request.value = await props.build()
  } catch (e) {
    error.value = gradeErrorMessage(e instanceof GradeError ? e.code : '')
  } finally {
    loading.value = false
  }
}

const src = (b64: string) => `data:image/png;base64,${b64}`
const kb = (r: GradeRequest) => Math.round(JSON.stringify(r).length / 1024)
const sections = (r: GradeRequest): { title: string; part: GradePart; rubric?: string[] }[] => [
  { title: 'Question', part: r.question },
  ...(r.solution
    ? [{ title: 'Solution', part: r.solution, rubric: r.solution.rubric.map((l) => `${l.item} (${l.max} P, ${l.source})`) }]
    : []),
  ...r.references.flatMap((x, i) => [
    { title: `Reference ${i + 1} · question (${x.points} P)`, part: x.question },
    { title: `Reference ${i + 1} · solution`, part: x.solution, rubric: x.solution.rubric.map((l) => `${l.item} (${l.max} P)`) },
  ]),
  { title: 'Your answer', part: r.answer },
]
</script>

<template>
  <button type="button" class="mode" data-request-preview @click="show">What the model gets</button>
  <Modal :open="open" @close="open = false">
    <div class="preview">
      <header class="head">
        <span>What the model gets</span>
        <button type="button" class="mode" @click="open = false">Close</button>
      </header>
      <p v-if="loading" class="mute">Building the request…</p>
      <p v-else-if="error" class="mute">{{ error }}</p>
      <p v-else-if="!request" class="mute">This subtask is not sent to the model.</p>
      <template v-else>
        <p class="mute">
          {{ request.provider }} · {{ request.model }} · Max points: {{ request.points }} ·
          {{ request.solution ? 'grades against the solution' : 'solves it first' }} · about {{ kb(request) }} KB
        </p>
        <section v-for="s in sections(request)" :key="s.title" class="section">
          <h4>{{ s.title }}</h4>
          <p v-if="s.part.text" class="text">{{ s.part.text }}</p>
          <ul v-if="s.rubric?.length" class="rubric">
            <li v-for="l in s.rubric" :key="l">{{ l }}</li>
          </ul>
          <img v-for="(b64, i) in s.part.images" :key="i" :src="src(b64)" alt="" />
          <p v-if="!s.part.text && !s.part.images.length" class="mute">(empty)</p>
        </section>
      </template>
    </div>
  </Modal>
</template>

<style scoped>
.preview {
  width: min(720px, 92vw);
  max-height: 85vh;
  overflow-y: auto;
  font-size: 12px;
}
.head {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--s3);
}
.section {
  margin-top: var(--s4);
}
h4 {
  margin: 0 0 var(--s1);
  font-weight: 500;
}
.text {
  white-space: pre-wrap;
  margin: 0 0 var(--s2);
}
.rubric {
  margin: 0 0 var(--s2);
  padding-left: var(--s4);
}
img {
  display: block;
  width: 100%;
  border: 1px solid var(--line);
  margin-bottom: var(--s2);
}
.mute {
  color: var(--mute);
}
.mode {
  padding: 0 0 2px;
  font-size: var(--fs-sm);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--mute);
}
</style>
