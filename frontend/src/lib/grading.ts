import { getImage, type ImageVariant } from '@/lib/db'
import { isAnswered, onPaperOnly } from '@/lib/answers'
import { changedInOvertime, maxPoints } from '@/lib/scoring'
import { answerParts, includedTasks, sheetBlocks, subtaskTitle, type SheetPart } from '@/lib/sheet'
import { matchSolution } from '@/lib/solution'
import { subjectOf } from '@/lib/stats'
import { paintStroke } from '@/lib/strokes'
import type { Answer, Attempt, LlmGrade, Provider, RubricLine, StoredExam, Stroke } from '@/types/attempt'
import type { Region, Subtask, Task } from '@/types/exam'

export interface GradePart {
  text: string
  /** base64 PNG, no data: prefix */
  images: string[]
}
export interface GradeSolution extends GradePart {
  rubric: RubricLine[]
}
export interface GradeReference {
  question: GradePart
  solution: GradeSolution
  points: number
}
export interface GradeRequest {
  provider: Provider
  model: string
  points: number
  question: GradePart
  solution: GradeSolution | null
  references: GradeReference[]
  answer: GradePart
  /** signed in: the server adds matching course material to a request that has no solution */
  subject?: string
  /** the exam being graded and its solution exam, so the server leaves their tasks out of the material */
  exclude_exams?: string[]
}

export type Version = 'main' | 'over'
export type SkipReason = 'no_answer' | 'auto'

export function skipReason(
  task: Task,
  subtask: Subtask,
  answer: Answer | undefined,
  mcKey: number[] | null,
): SkipReason | null {
  if (!answer || !isAnswered(answer) || onPaperOnly(answer)) return 'no_answer'
  if ((subtask.mc_options?.length ?? 0) > 0 && mcKey?.length) return 'auto'
  return null
}

// shortcut: word overlap on 4+ letter words, upgrade to vector search in Phase 4
const words = (s: string) => new Set(s.toLowerCase().match(/\p{L}{4,}/gu) ?? [])
function overlap(a: string, b: string): number {
  const x = words(a)
  const y = words(b)
  const both = [...x].filter((w) => y.has(w)).length
  const all = x.size + y.size - both
  return all === 0 ? 0 : both / all
}

export interface Similar {
  exam: StoredExam
  task: Task
  subtask: Subtask
}

/** the best two solved subtasks of the same subject whose text resembles this one */
export function similarSubtasks(
  subtask: Subtask,
  exams: StoredExam[],
  subject: string,
  excludeExamIds: string[],
): Similar[] {
  return exams
    .filter(
      (e) =>
        !excludeExamIds.includes(e.id) &&
        subjectOf(e) === subject &&
        (e.hasInk || e.structure.is_solution),
    )
    .flatMap((exam) =>
      exam.structure.tasks.flatMap((task) =>
        task.subtasks.map((s) => ({ exam, task, subtask: s, score: overlap(subtask.text, s.text) })),
      ),
    )
    .filter((c) => c.score >= 0.2)
    .sort((a, b) => b.score - a.score)
    .slice(0, 2)
    .map(({ exam, task, subtask: s }) => ({ exam, task, subtask: s }))
}

export interface LlmJob {
  /** `${subtaskId}:${version}` */
  key: string
  subtaskId: string
  version: Version
  build: () => Promise<GradeRequest>
  /** where a rubric the LLM infers is stored */
  rubricTarget: { examId: string; subtaskId: string } | null
}

export interface PlanContext {
  exam: StoredExam
  attempt: Attempt
  solutionExam: StoredExam | null
  /** MC answer keys by subtask id */
  mcKeys: Record<string, number[]>
  library: StoredExam[]
  provider: Provider
  model: string
  withReferences?: boolean
  /** signed in: the server supplies similar tasks and slides as short text, so no reference images are sent */
  material?: boolean
}

export async function blobBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer())
  let bin = ''
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(bin)
}

async function cropImages(examId: string, variant: ImageVariant, names: string[]): Promise<string[]> {
  const blobs = await Promise.all(names.map((n) => getImage(examId, variant, n)))
  return Promise.all(blobs.flatMap((b) => (b ? [blobBase64(b)] : [])))
}

/** crops worth sending: plain-text regions go as text only */
const regionNames = (regions: Region[]) =>
  regions.flatMap((r) => (r.image && r.visual !== false ? [r.image] : []))

const STUDENT_INK = '#1f5fd6' // the prompt says the student's marks are blue

/**
 * The sheet the strokes were drawn on (AnswerSheet.vue): crops stacked at one width, plus a 3:1 text box
 * below them when no answer box is printed. Stroke points are fractions of this whole area.
 */
export function sheetLayout(sizes: { width: number; height: number }[], below: boolean) {
  const width = Math.max(...sizes.map((s) => s.width))
  let y = 0
  const rects = sizes.map((s) => {
    const r = { y, height: (s.height * width) / s.width }
    y += r.height
    return r
  })
  return { width, height: y + (below ? width / 3 : 0), rects }
}

async function answerImage(examId: string, part: SheetPart, strokes: Stroke[]): Promise<string | null> {
  if (!strokes.some((s) => !s.erase)) return null
  const blobs = await Promise.all(part.crops.map((c) => getImage(examId, 'blank', c.name)))
  const bitmaps = await Promise.all(blobs.flatMap((b) => (b ? [createImageBitmap(b)] : [])))
  if (!bitmaps.length) return null
  const { width: w, height: h, rects } = sheetLayout(bitmaps, part.box === null)
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = Math.round(h)
  const c = canvas.getContext('2d')!
  c.fillStyle = '#fff'
  c.fillRect(0, 0, w, h)
  bitmaps.forEach((b, i) => {
    c.drawImage(b, 0, rects[i]!.y, w, rects[i]!.height)
    b.close()
  })
  if (part.box === null) {
    c.strokeStyle = '#ccc'
    c.strokeRect(0.5, h - w / 3, w - 1, w / 3 - 1)
  }
  // strokes go on their own layer so erasing doesn't cut holes in the crops
  const ink = document.createElement('canvas')
  ink.width = w
  ink.height = canvas.height
  const ic = ink.getContext('2d')!
  // the student's marks in one color the prompt names, so the model can tell them from the print
  for (const s of strokes) paintStroke(ic, s.erase ? s : { ...s, color: STUDENT_INK }, w, h)
  c.drawImage(ink, 0, 0)
  return canvas.toDataURL('image/png').replace(/^data:[^,]*,/, '')
}

async function answerPart(examId: string, sub: Subtask, answer: Answer): Promise<GradePart> {
  const ticked = answer.ticks.flatMap((i) => sub.mc_options?.[i]?.text ?? [])
  const typed = answer.parts.map((p) => p.text.trim()).filter(Boolean)
  const imgs = await Promise.all(
    answerParts(sub).map((part, i) => answerImage(examId, part, answer.parts[i]?.strokes ?? [])),
  )
  return {
    text: [...ticked, ...typed].join('\n\n'),
    images: imgs.filter((x): x is string => x !== null),
  }
}

/** `subtaskCrops` false when another image already shows the subtask (a drawn answer, an ink solution) */
async function questionPart(
  examId: string,
  task: Task,
  sub: Subtask,
  variant: ImageVariant,
  subtaskCrops = true,
): Promise<GradePart> {
  const blocks = sheetBlocks(task, [sub.id])
  const texts = blocks.map((b) => (b.kind === 'context' ? b.context.text : b.subtask.text))
  const names = blocks.flatMap((b) =>
    b.kind === 'context' ? regionNames(b.context.regions) : subtaskCrops ? regionNames(b.subtask.regions) : [],
  )
  return {
    text: [subtaskTitle(task, sub), ...texts].filter(Boolean).join('\n\n'),
    images: await cropImages(examId, variant, names),
  }
}

async function solutionPart(
  exam: StoredExam,
  sub: Subtask,
): Promise<GradeSolution> {
  return {
    text: sub.solution_text || sub.text,
    images: await cropImages(exam.id, 'ink', regionNames(sub.regions)),
    rubric: exam.rubrics?.[sub.id] ?? [],
  }
}

const MAX_IMAGES = 20 // the server's cap per request

const imageCount = (r: GradeRequest) =>
  r.question.images.length +
  (r.solution?.images.length ?? 0) +
  r.answer.images.length +
  r.references.reduce((n, x) => n + x.question.images.length + x.solution.images.length, 0)

/** drop references (last first) until the request fits; GradeError if it never will */
function capImages(r: GradeRequest): GradeRequest {
  const refs = [...r.references]
  while (refs.length && imageCount({ ...r, references: refs }) > MAX_IMAGES) refs.pop()
  const out = { ...r, references: refs }
  if (imageCount(out) > MAX_IMAGES) throw new GradeError('too_many_images')
  return out
}

export function planGrading(ctx: PlanContext): { jobs: LlmJob[]; skipped: Record<string, SkipReason> } {
  const { exam, attempt, solutionExam } = ctx
  const matches = solutionExam ? matchSolution(exam.structure, solutionExam.structure) : {}
  const subject = subjectOf(exam)
  const exclude = [exam.id, ...(solutionExam ? [solutionExam.id] : [])]
  const jobs: LlmJob[] = []
  const skipped: Record<string, SkipReason> = {}

  for (const task of includedTasks(exam.structure, attempt)) {
    for (const sub of task.subtasks) {
      const changed = changedInOvertime(attempt, sub.id)
      const versions: [Version, Answer | undefined][] = changed
        ? [['main', attempt.snapshot?.[sub.id]], ['over', attempt.answers[sub.id]]]
        : [['main', attempt.answers[sub.id]]]
      const reasons = versions.map(([, a]) => skipReason(task, sub, a, ctx.mcKeys[sub.id] ?? null))
      if (reasons.every((r) => r !== null)) {
        skipped[sub.id] = reasons[0]!
        continue
      }
      // a solution: the ink exam itself, else the matched subtask of the attached solution exam
      const own = exam.hasInk ? { exam, sub } : null
      const matched = solutionExam && matches[sub.id] ? { exam: solutionExam, sub: matches[sub.id]! } : null
      const sol = own ?? matched
      const refs = ctx.material ? [] : !sol || ctx.withReferences ? similarSubtasks(sub, ctx.library, subject, exclude) : []

      versions.forEach(([version, answer], i) => {
        if (reasons[i] !== null) return
        jobs.push({
          key: `${sub.id}:${version}`,
          subtaskId: sub.id,
          version,
          rubricTarget: sol ? { examId: sol.exam.id, subtaskId: sol.sub.id } : null,
          build: async () => {
            const answerOut = await answerPart(exam.id, sub, answer!)
            const solution = sol ? await solutionPart(sol.exam, sol.sub) : null
            // an ink solution of this very subtask shows the question too
            const inkShowsQuestion = sol?.exam.id === exam.id && !!solution?.images.length
            return capImages({
              provider: ctx.provider,
              model: ctx.model,
              // no printed point value: graded on a 1-point scale, shown as correct / partly / wrong
              points: maxPoints(task, sub, attempt.mcRule, ctx.mcKeys[sub.id]) ?? 1,
              question: await questionPart(exam.id, task, sub, 'blank', !answerOut.images.length && !inkShowsQuestion),
              solution,
              ...(ctx.material ? { subject, exclude_exams: exclude } : {}),
              references: await Promise.all(
                refs.map(async (r) => {
                  const refSolution = await solutionPart(r.exam, r.subtask)
                  return {
                    question: await questionPart(r.exam.id, r.task, r.subtask, 'blank', !refSolution.images.length),
                    solution: refSolution,
                    points: maxPoints(r.task, r.subtask, attempt.mcRule, r.subtask.mc_key) ?? 1,
                  }
                }),
              ),
              answer: answerOut,
            })
          },
        })
      })
    }
  }
  return { jobs, skipped }
}

export class GradeError extends Error {
  code: string
  constructor(code: string) {
    super(code)
    this.name = 'GradeError'
    this.code = code
  }
}

const errorMessages: Record<string, string> = {
  bad_key: 'Your API key was rejected.',
  no_credits: 'Your OpenRouter account has no credits left.',
  rate_limited: 'The provider is rate-limiting this model. Wait a minute, or pick another model in settings.',
  overloaded: 'The model is overloaded right now. Try again later, or pick another model or provider in settings.',
  refused: 'The model declined to grade this subtask.',
  no_key: 'Add an API key in settings.',
  sign_in: 'Sign in to grade answers.',
  too_many_images: 'This subtask has too many images to send.',
  timeout: 'No answer from the model for 2 minutes, it is probably overloaded. Try again, or pick another model in settings.',
}

export const gradeErrorMessage = (code: string): string =>
  errorMessages[code] ?? "The LLM couldn't grade this. Try Re-grade, or pick another model in settings."

/** complete `data: <json>` events in the buffer, and the unfinished rest */
export function sseEvents(buffer: string): { events: unknown[]; rest: string } {
  const chunks = buffer.replace(/\r\n/g, '\n').split('\n\n')
  const rest = chunks.pop() ?? ''
  const events = chunks.flatMap((c) => {
    // comment lines (": ping" keepalives) start with a colon
    const data = c.split('\n').filter((l) => l.startsWith('data:'))
    if (data.length === 0) return []
    try {
      return [JSON.parse(data.map((l) => l.slice(5).replace(/^ /, '')).join('\n')) as unknown]
    } catch {
      throw new GradeError('llm_failed')
    }
  })
  return { events, rest }
}

export async function streamGrade(
  body: GradeRequest,
  key: string,
  signal: AbortSignal,
  onThinking: (text: string) => void,
): Promise<LlmGrade> {
  const res = await fetch('/api/grade', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-LLM-Key': key.trim() },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { code?: string } } | null
    const fallback = res.status === 429 ? 'rate_limited' : res.status === 413 ? 'too_many_images' : res.status === 401 ? 'sign_in' : 'llm_failed'
    throw new GradeError(j?.detail?.code ?? fallback)
  }
  const reader = res.body!.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (let end = false; !end; ) {
    const { done, value } = await reader.read()
    end = done
    buf += done ? dec.decode() + '\n\n' : dec.decode(value, { stream: true })
    const { events, rest } = sseEvents(buf)
    buf = rest
    for (const e of events as Record<string, any>[]) {
      if (e.type === 'thinking') onThinking(e.text)
      else if (e.type === 'error') throw new GradeError(e.code)
      else if (e.type === 'done') {
        const { points_min, points_max, ...g } = e.grade
        return { ...g, min: points_min, max: points_max } as LlmGrade
      }
    }
  }
  throw new GradeError('llm_failed')
}

/** one JSON line per eval case */
export const evalCasesJsonl = (cases: { id: string; expected: number; request: GradeRequest }[]): string =>
  cases.map((c) => JSON.stringify(c)).join('\n') + '\n'
