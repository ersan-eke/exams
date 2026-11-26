<script setup lang="ts">
import { computed } from 'vue'
import FoldBar from '@/components/ui/FoldBar.vue'
import CropImage from '@/components/ui/CropImage.vue'
import AnswerArea from './AnswerArea.vue'
import McOverlay from './McOverlay.vue'
import McButtonList from './McButtonList.vue'
import { useAttemptStore } from '@/stores/attempt'
import { mcOverlayUsable, subtaskTitle } from '@/lib/sheet'
import type { Subtask, Task } from '@/types/exam'

const props = defineProps<{ task: Task; subtask: Subtask }>()
const store = useAttemptStore()

const folded = computed(() => store.attempt?.view.folded.includes(props.subtask.id) ?? false)
const crops = computed(() =>
  props.subtask.regions.flatMap((r, regionIndex) =>
    r.image === null ? [] : [{ name: r.image, regionIndex }],
  ),
)
const mcOptions = computed(() => props.subtask.mc_options ?? [])
const hasMc = computed(() => mcOptions.value.length > 0)
const hasBoxes = computed(() => mcOverlayUsable(props.subtask))
const ticks = computed(() => store.attempt?.answers[props.subtask.id]?.ticks ?? [])

function toggle(i: number) {
  const next = ticks.value.includes(i)
    ? ticks.value.filter((t) => t !== i)
    : [...new Set([...ticks.value, i])].sort((a, b) => a - b)
  store.setAnswer(props.subtask.id, { ticks: next })
}
</script>

<template>
  <div class="block" :data-block="subtask.id">
    <FoldBar
      :title="subtaskTitle(task, subtask)"
      :meta="subtask.points === null ? undefined : `${subtask.points} P`"
      :folded="folded"
      @toggle="store.toggleFold(subtask.id)"
    >
      <AnswerArea v-if="!hasMc" :subtask="subtask" />
      <div v-else class="crops">
        <div v-for="c in crops" :key="c.name" class="crop-wrap">
          <CropImage :exam-id="store.exam!.id" variant="blank" :name="c.name" />
          <McOverlay
            v-if="hasBoxes"
            :options="mcOptions"
            :region-index="c.regionIndex"
            :ticks="ticks"
            @toggle="toggle"
          />
        </div>
      </div>
      <McButtonList
        v-if="hasMc && !hasBoxes"
        :options="mcOptions"
        :ticks="ticks"
        @toggle="toggle"
      />
    </FoldBar>
  </div>
</template>

<style scoped>
.crops {
  margin-top: var(--s2);
}
.crop-wrap {
  position: relative;
}
.crop-wrap + .crop-wrap :deep(.crop) {
  border-top: 0;
}
</style>
