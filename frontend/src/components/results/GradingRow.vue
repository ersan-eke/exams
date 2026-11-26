<script lang="ts">
import { ref as moduleRef } from 'vue'
import type { McOption } from '@/types/exam'
import type { PenColor, Tools } from '@/components/exam/PenTools.vue'

export interface SolutionView {
  /** '' when no matching solution subtask was found */
  examId: string
  images: { name: string; regionIndex: number }[]
  text: string
  /** answer key of the solution subtask, drawn on its crop (some PDFs hide the printed ticks) */
  mc: { options: McOption[]; key: number[] } | null
}

const MARK_COLORS: PenColor[] = [
  { css: '#c62828', label: 'Red' },
  { css: '#2e7d32', label: 'Green' },
]

/** shared by all rows, so a chosen pen stays chosen */
const markTools = moduleRef<Tools>({
  erase: false,
  color: MARK_COLORS[0]!.css,
  penSize: 1,
  eraserSize: 1,
})
</script>

<script setup lang="ts">
import { computed, ref } from 'vue'
import CropImage from '@/components/ui/CropImage.vue'
import PointsPicker from '@/components/ui/PointsPicker.vue'
import LlmCard from './LlmCard.vue'
import RequestPreview from './RequestPreview.vue'
import AnswerSheet from '@/components/exam/AnswerSheet.vue'
import DrawCanvas from '@/components/exam/DrawCanvas.vue'
import McOverlay from '@/components/exam/McOverlay.vue'
import PenTools, { penFor } from '@/components/exam/PenTools.vue'
import { isAnswered, onPaperOnly } from '@/lib/answers'
import { changedInOvertime, maxPoints, mcPoints } from '@/lib/scoring'
import { answerParts, crops, mcOverlayUsable, subtaskTitle } from '@/lib/sheet'
import { lookupMaterial, materialRoute, type MaterialLink } from '@/lib/documents'
import { subjectOf } from '@/lib/stats'
import { useAccountStore } from '@/stores/account'
import { useAttemptStore } from '@/stores/attempt'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'
import type { Answer, Stroke } from '@/types/attempt'
import type { Subtask, Task } from '@/types/exam'

const props = defineProps<{
  task: Task
  subtask: Subtask
  solution: SolutionView | null
  /** effective MC key: the subtask's own, else the attached solution's */
  mcKey: number[] | null
}>()
const account = useAccountStore()
const store = useAttemptStore()
const settings = useSettingsStore()
const library = useLibraryStore()
const editingPoints = ref(false)
function onPoints(e: Event) {
  const input = e.target as HTMLInputElement
  const v = input.valueAsNumber
  if (input.value === '' || (!Number.isNaN(v) && v >= 0)) {
    void library.setPoints(store.exam!.id, props.subtask.id, input.value === '' ? null : v)
  } else {
    input.value = String(max.value ?? '') // invalid: back to the current max
  }
}

/** null until asked; the lookup is a database search, so it runs on click and not for every row */
const links = ref<MaterialLink[] | null>(null)
const looking = ref(false)
const solutionText = computed(() => props.solution?.text || props.subtask.solution_text)
const canLookup = computed(() => !!account.user && !!(props.subtask.text.trim() || solutionText.value.trim()))
async function findMaterial() {
  looking.value = true
  try {
    links.value = await lookupMaterial(subjectOf(store.exam!), props.subtask.text, solutionText.value)
  } catch {
    links.value = []
  } finally {
    looking.value = false
  }
}

const grade = computed(() => store.attempt?.grades[props.subtask.id])
const max = computed(() => maxPoints(props.task, props.subtask, store.attempt?.mcRule, props.mcKey))
const parts = computed(() => answerParts(props.subtask))
const mcOptions = computed(() => props.subtask.mc_options ?? [])
const hasMc = computed(() => mcOptions.value.length > 0)
const hasBoxes = computed(() => mcOverlayUsable(props.subtask))
const keyKnown = computed(() => hasMc.value && (props.mcKey?.length ?? 0) > 0)
const questionCrops = computed(() => crops(props.subtask))
const solutionBoxes = computed(
  () => props.solution?.mc?.options.some(({ bbox: b }) => b.x0 || b.y0 || b.x1 || b.y1) ?? false,
)

/** MC shows the key on its own crop; the solution crop only when that can't be done */
const showSolution = computed(
  () => !!props.solution && (!hasMc.value || !keyKnown.value || !hasBoxes.value),
)

type VersionKey = 'main' | 'over'
interface Version {
  key: VersionKey
  label: string | null
  answer: Answer | undefined
}

const versions = computed<Version[]>(() => {
  const a = store.attempt
  if (!a) return []
  const id = props.subtask.id
  if (!changedInOvertime(a, id)) return [{ key: 'main', label: null, answer: a.answers[id] }]
  return [
    { key: 'main', label: 'In time', answer: a.snapshot?.[id] },
    { key: 'over', label: 'Overtime', answer: a.answers[id] },
  ]
})

const correct = (answer: Answer | undefined) =>
  mcPoints({ kind: 'all_or_nothing' }, answer?.ticks ?? [], props.mcKey ?? [], 1) === 1

/** what the rule gives these ticks; null when it can't be worked out */
const auto = (answer: Answer | undefined) =>
  keyKnown.value && max.value !== null
    ? mcPoints(props.task.mc_rule ?? store.attempt!.mcRule, answer?.ticks ?? [], props.mcKey!, max.value)
    : null

/** 0 P and full points, plus what a per-tick rule gives in between (e.g. half points) */
function mcSteps(answer: Answer | undefined): number[] | undefined {
  if (max.value === null) return undefined
  const a = auto(answer)
  return [...new Set([0, ...(a === null ? [] : [a]), max.value])].sort((x, y) => x - y)
}

const ticked = (answer: Answer | undefined) =>
  (answer?.ticks ?? []).flatMap((i) =>
    mcOptions.value[i] ? [{ index: i, text: mcOptions.value[i]!.text }] : [],
  )
const keyText = computed(() =>
  (props.mcKey ?? []).map((i) => mcOptions.value[i]?.text ?? '').join(', '),
)

function pick(key: VersionKey, value: number | undefined) {
  if (value !== undefined) store.setGrade(props.subtask.id, { [key]: value })
  else store.clearGrade(props.subtask.id, key)
}

const jobKey = (v: VersionKey) => `${props.subtask.id}:${v}`
const regrade = (v: VersionKey) => void store.regrade(jobKey(v), settings.keys)
const DEV = import.meta.env.DEV

const marking = ref(false)
const markPen = computed(() => (marking.value ? penFor(markTools.value, MARK_COLORS) : null))
const marks = (key: VersionKey, i: number): Stroke[] => grade.value?.marks?.[key]?.[i] ?? []
function setMarks(key: VersionKey, i: number, strokes: Stroke[]) {
  const next = parts.value.map((_, k) => marks(key, k))
  next[i] = strokes
  store.setGrade(props.subtask.id, { marks: { ...grade.value?.marks, [key]: next } })
}
function clearMarks() {
  store.setGrade(props.subtask.id, { marks: {} })
}

const commenting = ref(!!grade.value?.comment)
const onComment = (e: Event) =>
  store.setGrade(props.subtask.id, { comment: (e.target as HTMLTextAreaElement).value })
</script>

<template>
  <section class="row" :data-grade-row="subtask.id">
    <header class="head">
      <span class="title">{{ subtaskTitle(task, subtask) }}</span>
      <span v-if="max !== null || editingPoints" class="meta">
        <input
          class="max"
          type="number"
          step="0.5"
          min="0"
          aria-label="Max points"
          :value="max ?? ''"
          @change="onPoints"
        />
        P
      </span>
      <button v-else type="button" class="mode" @click="editingPoints = true">set points</button>
    </header>

    <div v-if="canLookup" class="read-again">
      <button v-if="links === null" type="button" class="mode" :disabled="looking" @click="findMaterial">
        {{ looking ? 'Looking…' : 'Where to read this' }}
      </button>
      <span v-else-if="!links.length" class="none">No matching material found.</span>
      <template v-else>
        <span class="none">Read again:</span>
        <RouterLink v-for="l in links" :key="`${l.document_id}#${l.page}`" :to="materialRoute(l.document_id, l.page)">
          {{ l.title }}{{ l.page ? `, p. ${l.page}` : '' }}
        </RouterLink>
      </template>
    </div>

    <div v-if="showSolution && solution" class="solution" data-solution>
      <div class="label">Solution</div>
      <template v-if="solution.examId">
        <div v-for="c in solution.images" :key="c.name" class="crop-wrap">
          <CropImage :exam-id="solution.examId" variant="ink" :name="c.name" />
          <McOverlay
            v-if="solutionBoxes"
            :options="solution.mc!.options"
            :region-index="c.regionIndex"
            :ticks="[]"
            :marked="solution.mc!.key"
            :readonly="true"
          />
        </div>
        <p v-if="!solution.images.length && solution.text" class="answer text">
          {{ solution.text }}
        </p>
      </template>
      <p v-else class="answer none">No matching solution found.</p>
    </div>

    <div v-for="v in versions" :key="v.key" class="version">
      <div class="label" :class="{ over: v.key === 'over' }">{{ v.label ?? 'Your answer' }}</div>

      <template v-if="hasMc">
        <!-- one crop: the ticks as crosses, the key outlined in red -->
        <template v-if="hasBoxes">
          <div v-for="c in questionCrops" :key="c.name" class="crop-wrap">
            <CropImage :exam-id="store.exam!.id" variant="blank" :name="c.name" />
            <McOverlay
              :options="mcOptions"
              :region-index="c.regionIndex"
              :ticks="v.answer?.ticks ?? []"
              :marked="mcKey ?? []"
              :readonly="true"
            />
          </div>
        </template>
        <template v-else>
          <p class="answer">
            <template v-if="ticked(v.answer).length">
              <span v-for="t in ticked(v.answer)" :key="t.index" class="tick">✕ {{ t.text }}</span>
            </template>
            <span v-else class="none">No answer</span>
          </p>
          <p v-if="keyKnown && !(showSolution && solutionBoxes)" class="key-text">
            Correct: {{ keyText }}
          </p>
        </template>
        <p v-if="keyKnown" class="verdict" :class="correct(v.answer) ? 'good' : 'bad'" data-verdict>
          {{ correct(v.answer) ? 'Correct' : 'Incorrect' }}
        </p>
      </template>

      <p v-else-if="!isAnswered(v.answer)" class="answer none">No answer</p>
      <p v-else-if="onPaperOnly(v.answer!)" class="answer none">Answered on paper</p>
      <template v-else>
        <div v-for="(p, i) in parts" :key="i" class="part">
          <AnswerSheet
            :exam-id="store.exam!.id"
            :part="p"
            :text="v.answer!.parts[i]?.text ?? ''"
            :strokes="v.answer!.parts[i]?.strokes ?? []"
            readonly
          />
          <DrawCanvas
            class="marks"
            data-marks
            :strokes="marks(v.key, i)"
            :pen="markPen"
            @update:strokes="setMarks(v.key, i, $event)"
          />
        </div>
      </template>

      <div class="points">
        <PointsPicker
          :model-value="grade?.[v.key] ?? auto(v.answer) ?? undefined"
          :max="max"
          :options="hasMc ? mcSteps(v.answer) : undefined"
          :unit="hasMc ? 'P' : undefined"
          :free="hasMc"
          :label="v.label ? `${v.label} points` : 'Points'"
          @update:model-value="pick(v.key, $event)"
        />
        <span v-if="grade?.[v.key] === undefined && auto(v.answer) !== null" class="auto"
          >automatic</span
        >
      </div>
      <LlmCard
        :grade="grade?.llm?.[v.key]"
        :max="max"
        :pending="store.llm.pending[jobKey(v.key)]"
        :error="store.llm.errors[jobKey(v.key)]"
        :skipped="store.llm.skipped[subtask.id]"
        @regrade="regrade(v.key)"
      />
    </div>

    <div class="tools-bar">
      <button
        type="button"
        class="mode"
        :class="{ on: commenting }"
        @click="commenting = !commenting"
      >
        Comment
      </button>
      <RequestPreview
        v-for="v in DEV ? versions : []"
        :key="'preview-' + v.key"
        :build="() => store.buildLlmRequest(jobKey(v.key))"
      />
      <template
        v-if="!hasMc && versions.some((v) => isAnswered(v.answer) && !onPaperOnly(v.answer!))"
      >
        <button
          type="button"
          class="mode"
          :class="{ on: marking }"
          :aria-pressed="marking"
          data-mark
          @click="marking = !marking"
        >
          Mark
        </button>
        <PenTools v-if="marking" v-model="markTools" :colors="MARK_COLORS" @clear="clearMarks" />
      </template>
    </div>
    <textarea
      v-if="commenting"
      class="comment"
      aria-label="Comment"
      placeholder="Add a comment"
      :value="grade?.comment ?? ''"
      @input="onComment"
    />
  </section>
</template>

<style scoped>
.row {
  padding: var(--s4) 0;
  border-bottom: 1px solid var(--line);
}
.head {
  display: flex;
  justify-content: space-between;
  gap: var(--s3);
  margin-bottom: var(--s3);
}
.title {
  font-weight: 500;
}
.meta {
  color: var(--mute);
  font-variant-numeric: tabular-nums;
}
.max {
  width: 4.5ch;
  padding: 0;
  font: inherit;
  text-align: right;
  color: inherit;
  border-bottom: 1px solid transparent;
}
.max:hover,
.max:focus {
  border-bottom-color: var(--line);
}
.solution {
  margin-bottom: var(--s4);
}
.version + .version {
  margin-top: var(--s4);
}
.label {
  margin-bottom: var(--s1);
}
.label.over {
  color: var(--over);
}
.crop-wrap,
.part {
  position: relative;
}
.crop-wrap + .crop-wrap :deep(.crop) {
  border-top: 0;
}
.part + .part {
  margin-top: var(--s3);
}
.answer {
  padding: var(--s2) var(--s3);
  background: var(--paper);
  border: 1px solid var(--line);
}
.text {
  white-space: pre-wrap;
}
.none {
  color: var(--mute);
}
.tick {
  display: block;
}
.key-text {
  margin-top: var(--s1);
  color: var(--bad);
}
.verdict {
  margin-top: var(--s2);
  font-weight: 500;
}
.good {
  color: var(--good);
}
.bad {
  color: var(--bad);
}
.points {
  display: flex;
  align-items: center;
  gap: var(--s2);
  margin-top: var(--s2);
}
.auto {
  color: var(--mute);
  font-size: var(--fs-sm);
}
.tools-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s2) var(--s4);
  margin-top: var(--s3);
}
.mode {
  padding: 0 0 2px;
  font-size: var(--fs-sm);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--mute);
  border-bottom: 1px solid transparent;
}
.mode.on {
  color: var(--ink);
  border-bottom-color: var(--ink);
}
.comment {
  display: block;
  width: 100%;
  min-height: 56px;
  margin-top: var(--s2);
  padding: var(--s2) var(--s3);
  font: inherit;
  border: 1px solid var(--line);
  resize: vertical;
}
.read-again {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s3);
  align-items: baseline;
}
</style>
