<script setup lang="ts">
import { computed, ref } from 'vue'
import PdfDropZone from '@/components/ui/PdfDropZone.vue'
import SubjectSelect from '@/components/material/SubjectSelect.vue'
import { AlreadyUploadedError, materialRoute, uploadDocument, type DocumentKind } from '@/lib/documents'
import { useAccountStore } from '@/stores/account'

const props = defineProps<{ subject?: string }>()
const emit = defineEmits<{ done: [] }>()
const account = useAccountStore()

const picked = ref('')
const target = computed(() => props.subject || picked.value)
const kind = ref<DocumentKind>('slides')
const pending = ref(0)
const error = ref('')
const existing = ref<AlreadyUploadedError | null>(null)
let chain: Promise<void> = Promise.resolve()

/** several files arrive at once; they are read one after another so the Decks keep their order */
function add(file: File) {
  pending.value++
  const k = kind.value
  const subject = target.value
  chain = chain.then(async () => {
    try {
      await uploadDocument(file, { subject, kind: k })
      error.value = ''
      existing.value = null
    } catch (e) {
      existing.value = e instanceof AlreadyUploadedError ? e : null
      if (existing.value) error.value = existing.value.subject ? `Already in ${existing.value.subject}.` : 'Already uploaded.'
      else error.value = e instanceof Error && e.message === 'not_pdf' ? `${file.name} isn't a PDF.` : `Couldn't read ${file.name}.`
    } finally {
      pending.value--
      emit('done')
    }
  })
}
</script>

<template>
  <p v-if="!account.user" class="hint">Sign in to add Decks.</p>
  <div v-else class="add">
    <label>
      Type
      <select v-model="kind">
        <option value="slides">Slides</option>
        <option value="script">Script</option>
        <option value="exercises">Exercises</option>
      </select>
    </label>
    <SubjectSelect v-if="!subject" v-model="picked" />
    <PdfDropZone
      v-if="target"
      multiple
      heading="Add a Deck"
      :hint="`One PDF per Deck. Filed under ${target}.`"
      :busy="pending > 0"
      :busy-text="`Reading ${pending} file${pending === 1 ? '' : 's'}…`"
      :error="error"
      @file="add"
    >
      <template #error>
        {{ error }}
        <RouterLink v-if="existing" :to="materialRoute(existing.documentId)">Open the Deck</RouterLink>
      </template>
    </PdfDropZone>
  </div>
</template>

<style scoped>
.add {
  display: flex;
  flex-direction: column;
  gap: var(--s3);
}
label {
  color: var(--mute);
  display: flex;
  gap: var(--s2);
  align-items: center;
}
.hint {
  color: var(--mute);
}
</style>
