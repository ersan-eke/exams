<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import PdfViewer from '@/components/material/PdfViewer.vue'
import { getDocument, listDocuments, materialRoute, type StudyDocument } from '@/lib/documents'

const route = useRoute()
const doc = ref<StudyDocument | null>(null)
const chapters = ref<StudyDocument[]>([])
const failed = ref(false)

const id = computed(() => String(route.params.id))
const page = computed(() => Math.max(1, Number(route.query.page) || 1))
const terms = computed(() => (typeof route.query.terms === 'string' ? route.query.terms : ''))
const src = computed(() => `/api/documents/${encodeURIComponent(id.value)}/file`)
const at = computed(() => chapters.value.findIndex((d) => d.id === id.value))
const prev = computed(() => chapters.value[at.value - 1])
const next = computed(() => chapters.value[at.value + 1])

watch(
  id,
  async (v) => {
    doc.value = null
    failed.value = false
    try {
      doc.value = await getDocument(v)
      chapters.value = doc.value.subject ? await listDocuments(doc.value.subject) : []
    } catch {
      failed.value = true
    }
  },
  { immediate: true },
)
</script>

<template>
  <main class="material">
    <p v-if="failed" class="note">This Deck wasn't found. <RouterLink :to="{ name: 'ask' }">Back to Ask</RouterLink></p>
    <template v-else-if="doc">
      <header>
        <RouterLink :to="{ name: 'ask', query: doc.subject ? { subject: doc.subject } : {} }">← {{ doc.subject ?? 'Ask' }}</RouterLink>
        <h1>{{ doc.title }}</h1>
        <span class="meta">page {{ page }} of {{ doc.page_count }}</span>
        <RouterLink v-if="prev" :to="materialRoute(prev.id)">Previous: {{ prev.title }}</RouterLink>
        <RouterLink v-if="next" :to="materialRoute(next.id)">Next: {{ next.title }}</RouterLink>
      </header>
      <PdfViewer :url="src" :page="page" :terms="terms" @error="failed = true" />
    </template>
  </main>
</template>

<style scoped>
.material {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 80vh;
  padding: var(--s4) var(--s5);
  gap: var(--s3);
}
header {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s4);
  align-items: baseline;
}
h1 {
  font-weight: 500;
  font-size: 16px;
}
.meta,
.note {
  color: var(--mute);
}
</style>
