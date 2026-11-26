<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ExamModals from '@/components/exam/ExamModals.vue'
import ExamTopBar from '@/components/exam/ExamTopBar.vue'
import OutlineTree from '@/components/exam/OutlineTree.vue'
import Sheet from '@/components/exam/Sheet.vue'
import { useAttemptStore } from '@/stores/attempt'
import { neighbors, orderedShown } from '@/lib/sheet'

const route = useRoute()
const router = useRouter()
const store = useAttemptStore()
const ready = ref(false)
const error = ref<string | null>(null)

let timer: ReturnType<typeof setInterval> | null = null

// below 760 px the outline is a drawer that always starts closed; its state is
// local, so the stored outlineCollapsed (a wide-screen preference) is untouched
const NARROW = '(max-width: 759px)'
const mq = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(NARROW) : null
const narrow = ref(mq?.matches ?? false)
const drawerOpen = ref(false)
const onMedia = (e: MediaQueryListEvent) => {
  narrow.value = e.matches
  drawerOpen.value = false
}

async function open(id: string) {
  ready.value = false
  error.value = null
  try {
    await store.load(id)
    if (store.attempt?.status === 'handed_in') {
      await router.replace({ name: 'results', params: { attemptId: id } })
      return
    }
    store.tick()
    ready.value = true
  } catch {
    error.value = 'This exam could not be opened.'
  }
}

watch(
  () => route.params.attemptId as string,
  (id) => void open(id),
  { immediate: true },
)

onMounted(() => {
  timer = setInterval(() => store.tick(), 1000)
  mq?.addEventListener('change', onMedia)
})
onBeforeUnmount(() => {
  if (timer !== null) clearInterval(timer)
  mq?.removeEventListener('change', onMedia)
})

const collapsed = computed(() => store.attempt?.view.outlineCollapsed ?? false)
const showRail = computed(() => narrow.value || collapsed.value)
const showOutline = computed(() => (narrow.value ? drawerOpen.value : !collapsed.value))

function openOutline() {
  if (narrow.value) drawerOpen.value = true
  else store.setOutlineCollapsed(false)
}
function closeOutline() {
  if (narrow.value) drawerOpen.value = false
  else store.setOutlineCollapsed(true)
}
function onPick() {
  if (narrow.value) drawerOpen.value = false
}

function labelFor(id: string | null, currentTaskId: string | undefined): string | null {
  if (id === null || !store.exam) return null
  const task = store.exam.structure.tasks.find((t) => t.subtasks.some((s) => s.id === id))
  const sub = task?.subtasks.find((s) => s.id === id)
  if (!task || !sub) return null
  if (sub.label === '') return `Aufgabe ${task.number}`
  return task.id === currentTaskId ? sub.label : `Aufgabe ${task.number} · ${sub.label}`
}

const nav = computed(() => {
  const e = store.exam
  const a = store.attempt
  if (!e || !a) return { prev: null, next: null }
  const shown = orderedShown(e.structure, a.view.shown)
  const last = shown[shown.length - 1]
  if (last === undefined) return { prev: null, next: null }
  const n = neighbors(e.structure, a, last)
  const taskId = e.structure.tasks.find((t) => t.subtasks.some((s) => s.id === last))?.id
  return { prev: labelFor(n.prev, taskId), next: labelFor(n.next, taskId) }
})
</script>

<template>
  <div class="exam">
    <p v-if="error" class="message">{{ error }}</p>
    <template v-else-if="ready">
      <ExamTopBar />
      <div class="body" :class="{ collapsed: showRail, narrow }">
        <div v-if="showRail" class="rail">
          <button aria-label="Show outline" @click="openOutline">»</button>
        </div>
        <template v-if="showOutline">
          <OutlineTree class="tree" @collapse="closeOutline" @pick="onPick" />
          <div v-if="narrow" class="scrim" @click="closeOutline"></div>
        </template>
        <main class="page">
          <Sheet />
        </main>
      </div>
      <footer class="foot">
        <button v-if="nav.prev" class="prev" @click="store.goPrev()">← {{ nav.prev }}</button>
        <span v-else></span>
        <button v-if="nav.next" class="next" @click="store.goNext()">{{ nav.next }} →</button>
      </footer>
      <ExamModals />
    </template>
  </div>
</template>

<style scoped>
.exam {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  background: var(--white);
  font-size: 12px;
}
.message {
  margin: var(--s6) auto;
  color: var(--mute);
}
.body {
  position: relative;
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 220px 1fr;
}
.body.collapsed {
  grid-template-columns: 36px 1fr;
}
.tree {
  border-right: 1px solid var(--line);
  overflow-y: auto;
}
.rail {
  border-right: 1px solid var(--line);
  display: flex;
  justify-content: center;
  padding-top: var(--s3);
}
.rail button {
  color: var(--mute);
  height: fit-content;
}
.page {
  overflow-y: auto;
  min-width: 0;
}
.foot {
  display: flex;
  justify-content: space-between;
  padding: var(--s3) 20px;
  padding-bottom: calc(var(--s3) + env(safe-area-inset-bottom, 0px));
  border-top: 1px solid var(--line);
}
.prev {
  color: var(--mute);
}
.next {
  color: var(--ink);
  font-weight: 500;
}

.body.narrow .tree {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: min(260px, 85vw);
  background: var(--white);
  z-index: 2;
}
.scrim {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.6);
  z-index: 1;
}
.body.narrow .page {
  grid-column: 2;
}
</style>
