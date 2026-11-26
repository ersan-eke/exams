<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import CropImage from '@/components/ui/CropImage.vue'
import { getExam } from '@/lib/db'
import { crops } from '@/lib/sheet'
import type { StoredExam } from '@/types/attempt'
import type { Region } from '@/types/exam'

const route = useRoute()
const exam = ref<StoredExam | null>()
/** ?ink=1 shows the solution ink, when the exam has it */
const ink = computed(() => route.query.ink === '1' && !!exam.value?.hasInk)

watch(
  () => route.params.examId as string,
  async (id) => {
    exam.value = undefined
    exam.value = (await getExam(id).catch(() => undefined)) ?? null
    await nextTick()
    jump()
  },
  { immediate: true },
)

/** ?subtask=<key> (Slack's "Open in exam-sim" link) scrolls to that question */
function jump() {
  const key = route.query.subtask
  if (typeof key !== 'string') return
  const go = () => document.querySelector(`[data-subtask="${CSS.escape(key)}"]`)?.scrollIntoView()
  go()
  // shortcut: crops load from IndexedDB and shift the layout, so scroll again once they have settled; use image sizes if this ever flickers
  setTimeout(go, 400)
}

const images = (regions: Region[]) => regions.flatMap((r) => (r.image === null ? [] : [r.image]))
</script>

<template>
  <main class="preview">
    <p v-if="exam === null" class="kicker">This exam could not be opened.</p>
    <template v-else-if="exam">
      <p class="kicker">{{ ink ? 'Solution' : 'Exam' }}</p>
      <header>
        <h1>{{ exam.title }}</h1>
        <RouterLink
          v-if="!exam.solutionFor"
          class="btn"
          :to="{ name: 'exam-settings', params: { examId: exam.id } }"
          >Start</RouterLink
        >
      </header>
      <section v-for="t in exam.structure.tasks" :key="t.id" class="task">
        <div class="label">
          Aufgabe {{ t.number }} {{ t.title }}<template v-if="t.points !== null">
            · {{ t.points }} P</template
          >
        </div>
        <div v-for="c in t.context" :key="c.id" class="crops">
          <CropImage
            v-for="name in images(c.regions)"
            :key="name"
            :exam-id="exam.id"
            :variant="ink ? 'ink' : 'blank'"
            :name="name"
          />
        </div>
        <div v-for="s in t.subtasks" :key="s.id" class="crops" :data-subtask="s.id">
          <CropImage
            v-for="c in crops(s)"
            :key="c.name"
            :exam-id="exam.id"
            :variant="ink ? 'ink' : 'blank'"
            :name="c.name"
          />
        </div>
      </section>
    </template>
  </main>
</template>

<style scoped>
.preview {
  max-width: 720px;
  margin: 0 auto;
  padding: 36px 48px;
}
.kicker {
  color: var(--mute);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  margin: 0 0 6px;
}
header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s3);
  margin-bottom: var(--s5);
}
h1 {
  font-weight: 500;
  font-size: 18px;
}
.btn {
  padding: 7px 16px;
  border: 1px solid var(--ink);
  text-decoration: none;
}
.task {
  margin-bottom: var(--s5);
}
.task .label {
  margin-bottom: var(--s2);
}
.crops + .crops {
  margin-top: var(--s2);
}
@media (max-width: 600px) {
  .preview {
    padding: 28px 16px;
  }
}
</style>
