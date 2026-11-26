<script setup lang="ts">
import { computed } from 'vue'
import FoldBar from '@/components/ui/FoldBar.vue'
import CropImage from '@/components/ui/CropImage.vue'
import SubtaskBlock from './SubtaskBlock.vue'
import { useAttemptStore } from '@/stores/attempt'
import { includedTasks, orderedShown, sheetBlocks } from '@/lib/sheet'
import type { Region } from '@/types/exam'

const store = useAttemptStore()

const groups = computed(() => {
  const e = store.exam
  const a = store.attempt
  if (!e || !a) return []
  const shown = orderedShown(e.structure, a.view.shown)
  return includedTasks(e.structure, a).flatMap((task) => {
    const blocks = sheetBlocks(task, shown)
    return blocks.length ? [{ task, blocks }] : []
  })
})

const isFolded = (id: string) => store.attempt?.view.folded.includes(id) ?? false
const images = (regions: Region[]) => regions.flatMap((r) => (r.image === null ? [] : [r.image]))
</script>

<template>
  <div class="sheet">
    <template v-for="g in groups" :key="g.task.id">
      <template v-for="b in g.blocks" :key="b.kind === 'context' ? b.context.id : b.subtask.id">
        <div v-if="b.kind === 'context'" class="block" :data-block="b.context.id">
          <FoldBar
            :title="`Context · Aufgabe ${g.task.number}`"
            :meta="g.task.title || undefined"
            :folded="isFolded(b.context.id)"
            @toggle="store.toggleFold(b.context.id)"
          >
            <div class="crops">
              <CropImage
                v-for="name in images(b.context.regions)"
                :key="name"
                :exam-id="store.exam!.id"
                variant="blank"
                :name="name"
              />
            </div>
          </FoldBar>
        </div>
        <SubtaskBlock v-else :task="g.task" :subtask="b.subtask" />
      </template>
    </template>
  </div>
</template>

<style scoped>
.sheet {
  max-width: 640px;
  margin: 0 auto;
  padding: var(--s5) var(--s4) var(--s6);
}
.block + .block {
  margin-top: var(--s5);
}
.crops {
  margin-top: var(--s2);
}
</style>
