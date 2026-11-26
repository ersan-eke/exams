import { ref, watch, type Ref } from 'vue'
import { getExam } from '@/lib/db'
import { useAttemptStore } from '@/stores/attempt'
import type { StoredExam } from '@/types/attempt'

/**
 * The solution exam linked to the loaded attempt (exams without ink only).
 * undefined while loading or when none is linked, null when it can't be loaded.
 */
export function useSolutionExam(): Ref<StoredExam | null | undefined> {
  const store = useAttemptStore()
  const solutionExam = ref<StoredExam | null | undefined>(undefined)
  watch(
    () => (store.exam?.hasInk ? null : store.attempt?.solutionExamId),
    async (id) => {
      solutionExam.value = undefined
      if (!id) return
      let e: StoredExam | null
      try {
        e = (await getExam(id)) ?? null
      } catch {
        e = null
      }
      if (id === store.attempt?.solutionExamId) solutionExam.value = e
    },
    { immediate: true },
  )
  return solutionExam
}
