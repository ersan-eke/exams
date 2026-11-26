<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { createSubject, listSubjects } from '@/lib/subjects'
import { bySubject, ownExams } from '@/lib/stats'
import { useLibraryStore } from '@/stores/library'

/** the one Subject dropdown: server subjects and the exams' subjects together; a new name typed into it creates the Subject */
defineProps<{ label?: string }>()
const model = defineModel<string>({ default: '' })
const emit = defineEmits<{ created: [name: string] }>()
const library = useLibraryStore()
const names = ref<string[]>([])
const id = `subject-${Math.random().toString(36).slice(2)}`

const options = computed(() => [...names.value].sort((a, b) => a.localeCompare(b)))

onMounted(async () => {
  const local = bySubject(ownExams((await library.catalog()).exams)).map(([name]) => name)
  const server = (await listSubjects().catch(() => [])).map((s) => s.name)
  names.value = [...server, ...local.filter((n) => !server.some((s) => s.toLowerCase() === n.toLowerCase()))]
})

async function commit(e: Event) {
  const typed = (e.target as HTMLInputElement).value.trim()
  if (!typed) return (model.value = '')
  const known = names.value.find((n) => n.toLowerCase() === typed.toLowerCase())
  if (known) return (model.value = known)
  const created = await createSubject(typed)
  names.value = [...names.value, created.name]
  model.value = created.name
  emit('created', created.name)
}
</script>

<template>
  <label class="subject">
    {{ label ?? 'Subject' }}
    <input :value="model" :list="id" placeholder="Pick one or type a new name" maxlength="100" @change="commit" />
    <datalist :id="id"><option v-for="s in options" :key="s" :value="s" /></datalist>
  </label>
</template>

<style scoped>
.subject {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--mute);
}
</style>
