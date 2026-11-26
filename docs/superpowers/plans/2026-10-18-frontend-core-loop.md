# Frontend Core Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upload an old exam, simulate it in a focused, timed exam screen built from the original crops, then see time statistics and grade the attempt.

**Architecture:** FastAPI gets one stateless upload endpoint that runs the existing pipeline and returns the exam structure plus crops (base64). The Vue app stores exams, crops and attempts in IndexedDB; all exam logic (clock, timing, scoring, snapshot) lives in small pure TS modules driven by one Pinia attempt store. Track 2 (Tasks 14–16) extends the pipeline with duration, MC options/answer key and MC grading rule; the frontend consumes those optional fields from day one.

**Tech Stack:** Vue 3.5 + TypeScript + Pinia + Vue Router 5 + Vite + Vitest (jsdom), `idb` (+ `fake-indexeddb` in tests); FastAPI, pdfplumber/pypdfium2 pipeline, pytest.

**Spec:** `docs/superpowers/specs/2026-10-18-frontend-core-loop-design.md`

## Global Constraints

- No git commits or pushes (user: "forget git for right now… just work locally"). Skip every commit step.
- Exams live only in the browser (IndexedDB). The backend writes to a temp dir and deletes it before responding.
- Colors: ink `#1c1c1c`, muted `#8a8a85`, lines `#e8e7e3`, answer areas `#fbfbf9`, soft fill `#f4f3ef`, overtime tone muted warm `#9a6a3a`. White background. No other accent colors, no shadows, no rounded cards.
- One sans-serif family (`Inter`, then `-apple-system, "Helvetica Neue", sans-serif`); small uppercase letter-spaced labels; `font-variant-numeric: tabular-nums` for times and points.
- Visual reference: mockups `exam-layout-v3.html`, `home-v1.html`, `results-v1.html`, `mc-overlay.html` in `.superpowers/brainstorm/64859-1792318174/content/`.
- PrimeVue is not used for styling. Hand-written components with CSS variables from `src/styles/tokens.css`.
- Placeholder product name: "Examen".
- Default time limit 90 min when the exam has none; points step 0.5; attendance check once at a random moment in the first 30 min, lasts 5 s, clock keeps running; default answer mode Type; default MC rule all-or-nothing.
- Non-core menu pages (My exams, Statistics, Practice, Quizzes, Ask), the account icon and "Ask an LLM to grade" show "coming soon".
- Data contract: TS types mirror `backend/app/pipeline/models.py` field names exactly (snake_case, no conversion).
- Commands: frontend `cd frontend && npx vitest run <path>`; backend `cd backend && .venv/bin/python -m pytest <path> -q`.

## Review Focus

1. **Tab closed across the time limit, then reopened** → the clock shows overtime, the time-up dialog appears, and a snapshot exists (taken at reopen; no answers changed while closed). Test in Task 7.
2. **Handing in before the limit** → no snapshot, results show only the main score, no overtime row. Tests in Tasks 6 and 12.
3. **Subtasks with unknown points (`points: null`) and tasks without labels (`label: ""`, implicit quiz task)** → outline shows the task title/"Question"; grading uses a free number field; totals skip unknown maxima. Tests in Tasks 6, 8, 13.
4. **Upload of a non-PDF, a scanned PDF, or a PDF without tasks** → specific message, nothing stored. Tests in Tasks 1 and 4.
5. **Tasks excluded on the settings screen** → never appear in the outline, the time bars, or scoring. Tests in Tasks 5 and 6.

---

## File Structure

```
backend/
  app/api/routes.py              # POST /api/exams (replaces the upload-pdf stub)
  app/pipeline/meta.py           # Task 14: duration + MC rule parsing
  app/pipeline/mc.py             # Task 15: MC option + answer key detection
  app/pipeline/models.py         # + duration_minutes, mc_rule, McOption, Subtask.mc_options/mc_key
  main.py                        # drop layout_analyzer import, mount router under /api
  requirements-dev.txt           # pytest
  tests/conftest.py, tests/test_api.py, tests/test_meta.py, tests/test_mc.py
frontend/src/
  styles/tokens.css              # design tokens + base reset
  types/exam.ts                  # mirrors models.py
  types/attempt.ts               # Answer, Attempt, McRule, ...
  lib/api.ts                     # uploadExam()
  lib/db.ts                      # IndexedDB access
  lib/clock.ts                   # elapsed / remaining / format
  lib/timing.ts                  # time per subtask accumulation
  lib/answers.ts                 # isAnswered, sameAnswer, emptyAnswer
  lib/scoring.ts                 # mcPoints, totals
  lib/sheet.ts                   # outline rows, contexts for shown subtasks, ordering
  lib/solution.ts                # match solution exam to exam by ids
  stores/settings.ts             # app-wide settings (localStorage)
  stores/library.ts              # exams list, import upload, recent
  stores/attempt.ts              # running attempt
  components/frame/AppFrame.vue, SideMenu.vue, SettingsPanel.vue
  components/ui/FoldBar.vue, Modal.vue, PointsPicker.vue, CropImage.vue
  components/exam/ExamTopBar.vue, OutlineTree.vue, Sheet.vue, SubtaskBlock.vue,
                  AnswerArea.vue, DrawCanvas.vue, McOverlay.vue, McButtonList.vue,
                  ExamModals.vue
  components/results/TimeStats.vue, TimeBars.vue, GradingList.vue
  views/NewExamView.vue, ExamSettingsView.vue, ExamView.vue, ResultsView.vue, ComingSoonView.vue
  router/index.ts, App.vue, main.ts
```
Scaffold leftovers (`HelloWorld.vue`, `TheWelcome.vue`, `WelcomeItem.vue`, `icons/`, `AboutView.vue`, `HomeView.vue`, `stores/counter.ts`, `assets/*`, `components/__tests__/HelloWorld.spec.ts`) are deleted in Task 2.

---

### Task 1: Upload endpoint

**Files:**
- Modify: `backend/app/api/routes.py` (replace contents), `backend/main.py`, `backend/app/pipeline/__init__.py`
- Create: `backend/requirements-dev.txt`, `backend/tests/conftest.py`, `backend/tests/test_api.py`

**Interfaces:**
- Produces: `POST /api/exams` multipart field `file`, optional form field `role` = `"exam"` (default) | `"solution"`.
  Response 200: `{"exam": ExamStructure, "images": {name: base64png}, "solution_images": {name: base64png} | null}`.
  `images` are blank (solution ink hidden when `exam.is_solution`). `solution_images` are rendered with ink and present when `exam.is_solution` or `role == "solution"`.
  Errors: 400 `{"detail": {"code": "not_pdf"}}`; 422 `{"detail": {"code": "scanned" | "no_tasks", "message": str}}`.
- Produces: new `render_variants(pdf_path, exam, pages, out_dir, ink: bool) -> dict[str, Path | None]` in `app/pipeline/__init__.py` returning `{"blank": crops_dir, "ink": crops_dir | None}`; it calls `render_exam` once with `strip_solutions=exam.is_solution` into `out_dir/blank` and, when `ink`, once with `strip_solutions=False` into `out_dir/ink` (debug off). `process()` keeps its signature for the CLI.

- [ ] **Step 1:** Create `requirements-dev.txt` with `pytest` and `httpx`; install: `uv pip install --python .venv/bin/python -r requirements-dev.txt`.
- [ ] **Step 2: Write failing tests** in `tests/test_api.py` using `fastapi.testclient.TestClient(app)`; `conftest.py` adds `backend/` to `sys.path` and defines `SAMPLES = Path(__file__).parents[2] / "samples"`; sample-based tests use `pytest.mark.skipif(not path.exists())`.
  - `test_rejects_non_pdf`: post `b"hello"` as `x.txt` → 400, `detail.code == "not_pdf"`.
  - `test_exam_upload`: `samples/grnvs/endterm_2019.pdf` → 200; `len(exam.tasks) == 6`; every `region.image` of every context/subtask is a key of `images`; `solution_images is None`.
  - `test_solution_upload_has_both_variants`: `samples/grnvs/endterm_2019-solution.pdf` → `exam.is_solution` true; `images.keys() == solution_images.keys()`; for image `"A2b_0.png"` the two base64 strings differ.
  - `test_scanned_pdf`: `samples/gdb/17_endterm.pdf` → 422, `detail.code == "scanned"`.
  - `test_temp_files_removed`: monkeypatch `tempfile.mkdtemp`/`TemporaryDirectory` to record the path; after the request the path does not exist.
- [ ] **Step 3:** Run `.venv/bin/python -m pytest tests/test_api.py -q` → FAIL (404 / import errors).
- [ ] **Step 4: Implement** the route as a plain `def` (runs in FastAPI's threadpool) using `tempfile.TemporaryDirectory()`; save upload via `shutil.copyfileobj`; reject when the first 5 bytes are not `b"%PDF-"`; `scanned` when `exam.kind == "scanned"` or (no tasks and any issue mentions "scanned"); `no_tasks` when `exam.tasks` is empty. Base64 with `base64.b64encode(path.read_bytes()).decode()`. In `main.py` remove the `layout_analyzer` usage and `app.include_router(router, prefix="/api")`; delete `app/ml_services/layout_analyzer.py` usage from routes.
- [ ] **Step 5:** Run tests → PASS. Also `curl -F file=@../samples/grnvs/endterm_2019.pdf localhost:8000/api/exams | head -c 300` with `fastapi dev main.py` running shows JSON.

### Task 2: App frame, tokens, routing, settings

**Files:**
- Delete: scaffold leftovers listed above.
- Create: `src/styles/tokens.css`, `src/types/exam.ts`, `src/types/attempt.ts`, `src/stores/settings.ts`, `src/components/frame/AppFrame.vue`, `SideMenu.vue`, `SettingsPanel.vue`, `src/views/ComingSoonView.vue`, `src/components/ui/Modal.vue`
- Modify: `src/main.ts`, `src/App.vue`, `src/router/index.ts`, `vite.config.ts`
- Test: `src/components/frame/__tests__/SideMenu.spec.ts`, `src/router/__tests__/router.spec.ts`

**Interfaces:**
- Produces `types/exam.ts`: `BBox {x0,y0,x1,y1}`, `Region {page, bbox, image}`, `McOption {region: number; bbox: BBox /* relative 0..1 inside that region's image */; text: string}`, `Subtask {id,label,points: number|null,independent,regions,text,solution_text, mc_options?: McOption[], mc_key?: number[] | null}`, `Context {id, applies_from: string|null, regions, text}`, `Task {id,number,title,points: number|null,context,subtasks}`, `McRule = {kind:'all_or_nothing'} | {kind:'per_tick'; right:number; wrong:number; floor:number}`, `ExamStructure {source,page_count,page_sizes,kind,is_solution,total_points_stated,tasks,issues, duration_minutes?: number|null, mc_rule?: McRule|null}`.
- Produces `types/attempt.ts`: `AnswerMode = 'type'|'draw'|'paper'`; `Stroke {points: [number, number][] /* 0..1 of canvas */; erase: boolean}`; `Answer {mode: AnswerMode; text: string; strokes: Stroke[]; done: boolean; ticks: number[]}`; `SubtaskTime {main: number; over: number}` (ms); `Grade {main?: number; over?: number}`; `ViewState {shown: string[]; folded: string[]; expandedTasks: string[]; outlineCollapsed: boolean}`; `Attempt {id; examId; status: 'running'|'handed_in'; fresh: boolean; startedAt: number; timeLimitMs: number; includedTaskIds: string[]; attendanceAt: number|null /* ms after start */; attendanceDone: boolean; mcRule: McRule; extended: boolean; answers: Record<string, Answer>; snapshot: Record<string, Answer> | null; handedInAt: number|null; time: Record<string, SubtaskTime>; view: ViewState; grades: Record<string, Grade>; solutionExamId: string|null}`; `StoredExam {id; title; structure: ExamStructure; createdAt: number; hasInk: boolean}`.
- Produces `useSettingsStore()` with state `{defaultAnswerMode: AnswerMode; attendanceDefault: boolean}` persisted to `localStorage["examen.settings"]`; defaults `'type'`, `true`.
- Produces routes: `/` name `new`; `/exams/:examId/settings` name `exam-settings`; `/attempts/:attemptId` name `exam`; `/attempts/:attemptId/results` name `results`; `/my-exams`, `/statistics`, `/practice`, `/quizzes`, `/ask` → `ComingSoonView` with `meta.title`. Route `exam` has `meta.focus = true` (App.vue renders it without `AppFrame`).
- Produces `<Modal :open :dismissible @close>` with default slot and focus trap; `<AppFrame>` slot for page content.

- [ ] **Step 1: Write failing tests.** `SideMenu.spec.ts`: renders the six entries in order `New exam, My exams, Statistics, Practice, Quizzes, Ask`; clicking « adds class `collapsed` and hides labels; state persists in `localStorage["examen.menuCollapsed"]`. `router.spec.ts`: resolving `/statistics` gives `ComingSoonView` with `meta.title === 'Statistics'`; `/attempts/x` has `meta.focus === true`.
- [ ] **Step 2:** Run `npx vitest run src/components/frame src/router` → FAIL.
- [ ] **Step 3: Implement.** Tokens as CSS custom properties (`--ink`, `--mute`, `--line`, `--paper`, `--soft`, `--over`, spacing scale, font stack) plus a minimal reset; import in `main.ts`. `AppFrame`: top bar (brand left; gear opens `SettingsPanel` in a `Modal`; account icon shows a small "Accounts are coming soon" popover) + `SideMenu` + slot. `vite.config.ts`: `server.proxy['/api'] = 'http://localhost:8000'`.
- [ ] **Step 4:** Run tests → PASS; `npm run type-check` passes; `npm run dev` shows the frame with an empty middle on `/`.

### Task 3: Storage, API client, library store

**Files:**
- Create: `src/lib/db.ts`, `src/lib/api.ts`, `src/stores/library.ts`
- Test: `src/lib/__tests__/db.spec.ts`, `src/stores/__tests__/library.spec.ts`
- Dependencies: `npm i idb`, `npm i -D fake-indexeddb` (import `fake-indexeddb/auto` in the two specs).

**Interfaces:**
- Produces `db.ts` (database `examen`, version 1, stores `exams` (key `id`), `images` (key string), `attempts` (key `id`, index `examId`)): `putExam(e: StoredExam)`, `getExam(id): Promise<StoredExam|undefined>`, `listExams(): Promise<StoredExam[]>` (newest first), `putImages(examId, variant: 'blank'|'ink', images: Record<string, Blob>)`, `getImage(examId, variant, name): Promise<Blob|undefined>`, `putAttempt(a: Attempt)`, `getAttempt(id)`, `attemptsForExam(examId): Promise<Attempt[]>`, `runningAttempt(): Promise<Attempt|undefined>`. Image key format `${examId}/${variant}/${name}`.
- Produces `api.ts`: `class UploadError extends Error {code: 'not_pdf'|'scanned'|'no_tasks'|'network'|'server'}`; `uploadExam(file: File, role?: 'exam'|'solution'): Promise<{exam: ExamStructure; images: Record<string, Blob>; solution_images: Record<string, Blob> | null}>` (decodes base64 to `image/png` Blobs).
- Produces `useLibraryStore()`: `importUpload(file: File): Promise<string /* examId */>` (title = `source` without `.pdf`; stores exam + blank images + ink images if present, `hasInk` accordingly), `recent(limit = 5): Promise<{exam: StoredExam; latest: Attempt|undefined}[]>`, `running(): Promise<Attempt|undefined>`.

- [ ] **Step 1: Write failing tests.** `db.spec.ts`: round-trip exam, images (Blob size preserved), attempts; `listExams` newest first; `runningAttempt` returns only `status === 'running'`. `library.spec.ts` (mock `uploadExam`): `importUpload` stores structure and both image variants for a solution exam, sets `hasInk`; when `uploadExam` rejects with `UploadError('scanned')`, nothing is stored and the error propagates.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement with `openDB` from `idb`; `uploadExam` maps HTTP 400/422 `detail.code` to `UploadError`, fetch failure to `'network'`, other statuses to `'server'`.
- [ ] **Step 4:** Run → PASS.

### Task 4: New exam (start page)

**Files:**
- Create: `src/views/NewExamView.vue`
- Test: `src/views/__tests__/NewExamView.spec.ts`

**Interfaces:**
- Consumes: `useLibraryStore().importUpload/recent/running`, `UploadError`.
- Produces: after a successful upload navigates to `{name: 'exam-settings', params: {examId}}`.

- [ ] **Step 1: Write failing tests** (library store mocked):
  - shows drop zone text "Drop an old exam here" and "PDF · exam or solution · stays on this device";
  - while `importUpload` is pending shows "Reading the exam…";
  - error messages per code: `not_pdf` → "That file isn't a PDF.", `scanned` → "Scanned exams aren't supported yet.", `no_tasks` → "No tasks found in this PDF.", `network`/`server` → "Couldn't reach the server. Try again." — and the drop zone is back;
  - when `running()` returns an attempt, a "Continue exam" link to `{name:'exam'}` is shown;
  - recent list shows up to 5 titles; an exam whose latest attempt is handed in links to `results`, running → `exam`, none → `exam-settings`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement: drag-and-drop + hidden `<input type=file accept="application/pdf">`; layout per `home-v1.html`.
- [ ] **Step 4:** Run → PASS.

### Task 5: Exam settings + starting an attempt

**Files:**
- Create: `src/views/ExamSettingsView.vue`
- Modify: `src/stores/library.ts` (add `startAttempt`)
- Test: `src/views/__tests__/ExamSettingsView.spec.ts`, extend `library.spec.ts`

**Interfaces:**
- Produces `useLibraryStore().startAttempt(examId, opts: {title: string; timeLimitMin: number; includedTaskIds: string[]; attendance: boolean; mcRule: McRule}): Promise<string /* attemptId */>`. Creates `Attempt` with `status 'running'`, `startedAt = Date.now()`, `fresh = no handed_in attempt exists for examId`, `attendanceAt = attendance ? random in [120_000, 1_800_000) : null`, `view.shown = [first subtask id of first included task]`, `view.expandedTasks = [that task id]`, empty answers/time/grades, `snapshot null`, `extended false`. Updates the stored exam title. Rejects with `Error('another exam is running')` if a running attempt exists.

- [ ] **Step 1: Write failing tests.** `startAttempt`: second attempt for the same exam after a handed-in one has `fresh === false`; `attendanceAt` within bounds or `null`; running-attempt guard. View: time limit prefilled with `structure.duration_minutes` or `90`; MC rule select shown only if any subtask has `mc_options?.length`, prefilled from `structure.mc_rule` or all-or-nothing; unticking a task removes it from `includedTaskIds` passed to `startAttempt`; Start disabled when no task is included; `structure.issues` are listed in a quiet note "Notes from reading the exam" (muted text, no color), absent when empty.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement; summary line "N tasks · P points" (P = sum of known task points); Start navigates to `{name:'exam', params:{attemptId}}`.
- [ ] **Step 4:** Run → PASS.

### Task 6: Pure exam logic

**Files:**
- Create: `src/lib/clock.ts`, `src/lib/timing.ts`, `src/lib/answers.ts`, `src/lib/scoring.ts`, `src/lib/sheet.ts`
- Test: `src/lib/__tests__/{clock,timing,answers,scoring,sheet}.spec.ts`

**Interfaces (all pure):**
- `clock.ts`: `elapsed(a: Attempt, now: number): number`; `isOvertime(a, now): boolean` (`elapsed >= timeLimitMs`); `formatClock(ms: number): string` → `"1:12:40"` / `"12:40"` (no hours when < 1 h); `formatOvertime(ms): string` → `"+4:12"`; `remaining(a, now): number` (≥ 0).
- `timing.ts`: `addTime(time: Record<string, SubtaskTime>, openIds: string[], dtMs: number, overtime: boolean): Record<string, SubtaskTime>` — splits `dtMs` evenly over `openIds`, adds to `over` if `overtime` else `main`; no-op for empty `openIds`.
- `answers.ts`: `emptyAnswer(mode: AnswerMode): Answer`; `isAnswered(a?: Answer): boolean` (non-blank text, ≥1 non-erase stroke, `done`, or ≥1 tick); `sameAnswer(a?: Answer, b?: Answer): boolean` (deep equal; undefined equals empty).
- `scoring.ts`: `mcPoints(rule: McRule, ticks: number[], key: number[], max: number): number` — all-or-nothing: `max` iff tick set equals key set else 0; per_tick: `max(floor, right·|ticks∩key| + wrong·|ticks∖key|)` capped at `max`. `changedInOvertime(a: Attempt, subtaskId): boolean` (`snapshot !== null && !sameAnswer(snapshot[id], answers[id])`). `scores(a: Attempt, exam: ExamStructure): {main: number; over: number | null; maxKnown: number}` — over subtasks of included tasks: grade source per subtask is `grades[id].main` (fallback auto MC points on snapshot-or-final answers when `mc_key` present); overtime uses `grades[id].over` when `changedInOvertime`, else the main value; `over` is `null` when `snapshot === null`. `maxKnown` sums non-null subtask points.
- `sheet.ts`: `includedTasks(exam, a): Task[]`; `orderedShown(exam, shownIds: string[]): string[]` (exam order); `contextsFor(task: Task, shownSubtaskIds: string[]): Context[]` (contexts with `applies_from === null` or whose `applies_from` subtask index ≤ the max shown index in that task); `subtaskTitle(task, sub): string` → `"Aufgabe 2 · b)"`, or `"Aufgabe 2"` when `label === ""`; `neighbors(exam, a, id): {prev: string|null; next: string|null}` over included tasks.

- [ ] **Step 1: Write failing tests** with exact values:
  - `formatClock(4_360_000) === "1:12:40"`, `formatClock(760_000) === "12:40"`, `formatOvertime(252_000) === "+4:12"`.
  - `addTime({}, ['A2b','A2c'], 1000, false)` → `{A2b:{main:500,over:0}, A2c:{main:500,over:0}}`; overtime flag goes to `over`.
  - `mcPoints({kind:'per_tick',right:1,wrong:-1,floor:0}, [0,2], [0,1], 2) === 0`; same with ticks `[0,1]` → `2`; ticks `[0,1,3]` key `[0,1]` → `1`; all-or-nothing `[0,1]` vs `[0,1]` max 1 → `1`, `[0]` → `0`.
  - `scores`: handed in before limit (`snapshot null`) → `over === null`; subtask graded `{main:2, over:3}` and changed in overtime → main 2, over 3; unchanged subtask with `{main:2}` → contributes 2 to both; subtask with `points: null` excluded from `maxKnown` but its grade counts; subtasks of excluded tasks never count.
  - `contextsFor` with GRNVS-like task (ctx0 null, ctx1 applies_from `A1b`, ctx2 applies_from `A1c`): shown `['A1a']` → `[ctx0]`; shown `['A1c']` → `[ctx0, ctx1, ctx2]`.
  - `subtaskTitle` for `label ""` → `"Aufgabe 1"`.
- [ ] **Step 2:** Run `npx vitest run src/lib` → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.

### Task 7: Attempt store

**Files:**
- Create: `src/stores/attempt.ts`
- Test: `src/stores/__tests__/attempt.spec.ts` (fake-indexeddb, `vi.useFakeTimers()`)

**Interfaces:**
- Consumes: Task 3 db, Task 6 libs.
- Produces `useAttemptStore()`:
  state `{attempt: Attempt | null; exam: StoredExam | null; now: number; modal: null | 'attendance' | 'timeup' | 'handin'}`;
  actions `load(attemptId): Promise<void>`; `tick(now = Date.now())` (called every 1 s by `ExamView`: updates `now`; adds time for open subtasks — shown minus folded — only when `document.visibilityState === 'visible'` and `modal === null`; takes the snapshot when crossing the limit and `snapshot === null`; opens `'timeup'` when overtime and `!extended`; opens `'attendance'` when `attendanceAt !== null && !attendanceDone && elapsed >= attendanceAt` and not overtime); `finishAttendance()`; `extend()`; `requestHandIn()` / `cancelHandIn()`; `handIn(): Promise<void>` (sets `status 'handed_in'`, `handedInAt`, persists immediately);
  view actions `showOnly(subtaskId)`, `toggleShown(subtaskId)` (never leaves `shown` empty), `toggleFold(blockId)`, `toggleTask(taskId)`, `setOutlineCollapsed(v)`, `goNext()`, `goPrev()`;
  answer actions `setAnswer(subtaskId, patch: Partial<Answer>)`, `setGrade(subtaskId, g: Grade)`;
  persistence: every mutation schedules `putAttempt` debounced 500 ms; also flush on `visibilitychange` to hidden.
- Getters: `openIds: string[]`, `isOvertime: boolean`, `clockText: string` (remaining time, or `formatOvertime` when overtime).

- [ ] **Step 1: Write failing tests:**
  - tick 3 s with `shown ['A2b','A2c']`, `folded ['A2b']` → `time.A2c.main === 3000`, `A2b` absent.
  - crossing the limit takes a snapshot equal to current answers and opens `'timeup'`; after `extend()` further ticks don't reopen it and time goes to `over`.
  - Review Focus 1: attempt with `startedAt = now − (limit + 10 min)`, `snapshot null` → after `load` + first `tick`, `snapshot` is set, `modal === 'timeup'`, clock text starts with `+`.
  - attendance opens at `attendanceAt`, no time is added while it is open, `finishAttendance()` sets `attendanceDone`.
  - `toggleShown` keeps exam order via `orderedShown` and never empties `shown`.
  - reload: `setAnswer`, advance 600 ms, new store instance `load` → answer present.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.

### Task 8: Exam screen layout (outline, sheet, fold bars, crops)

**Files:**
- Create: `src/views/ExamView.vue`, `src/components/exam/ExamTopBar.vue`, `OutlineTree.vue`, `Sheet.vue`, `SubtaskBlock.vue`, `src/components/ui/FoldBar.vue`, `CropImage.vue`
- Test: `src/components/exam/__tests__/OutlineTree.spec.ts`, `Sheet.spec.ts`

**Interfaces:**
- Consumes: `useAttemptStore()`, `sheet.ts`, `db.getImage`.
- Produces `<CropImage :exam-id :variant :name>` (object URL from IndexedDB, revoked on unmount; `width:100%`, hairline border); `<FoldBar :title :meta :folded @toggle>` with a slot; `<SubtaskBlock :task :subtask>` = FoldBar + crops (all regions stacked) + `<AnswerArea>` slot placeholder (filled in Task 9).
- `ExamView` starts a 1 s `setInterval` calling `tick()`; layout per `exam-layout-v3.html`: top bar (title · clock · "Hand in"), outline left (collapsible to a rail), sheet centered max-width ≈ 640 px, prev/next footer. No app frame.

- [ ] **Step 1: Write failing tests.** `OutlineTree.spec.ts`: renders tasks with points; clicking the chevron toggles subtasks; clicking a row calls `showOnly`; hovering a row reveals an eye button; clicking it calls `toggleShown` and does not call `showOnly`; answered subtasks have class `answered`; shown ones `shown`; a task with a single `label ""` subtask renders as one row titled with the task title (Review Focus 3); excluded tasks are absent (Review Focus 5). `Sheet.spec.ts`: with shown `['A1c','A1a']` renders blocks in order `A1a, A1c` preceded by context fold bars for ctx0..ctx2 per `contextsFor`; toggling a fold bar calls `toggleFold` with the block id.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement; on narrow screens (< 760 px) the outline becomes an overlay drawer; in overtime the clock text uses `--over`.
- [ ] **Step 4:** Run → PASS; manual: `npm run dev`, upload GRNVS 2019, start, check outline/eye/fold behavior.

### Task 9: Answer area (Type · Draw · On paper)

**Files:**
- Create: `src/components/exam/AnswerArea.vue`, `DrawCanvas.vue`
- Modify: `SubtaskBlock.vue`
- Test: `src/components/exam/__tests__/AnswerArea.spec.ts`, `DrawCanvas.spec.ts`

**Interfaces:**
- `<AnswerArea :subtask-id>` reads/writes via `setAnswer`; mode switch "Type · Draw · On paper"; initial mode = existing answer's mode or `settings.defaultAnswerMode`. Hidden when the subtask has `mc_options` (Task 10 replaces it).
- `<DrawCanvas v-model:strokes :height="320">` — Pointer Events (pen, touch, mouse), `touch-action: none`; tools Pen / Eraser / Clear; points stored normalized 0..1; redraws on resize.

- [ ] **Step 1: Write failing tests:** typing updates `answers[id].text`; switching to "On paper" shows a "Mark as done" toggle that sets `done`; switching modes keeps previously entered text; `DrawCanvas`: pointerdown/move/up sequence emits one stroke with normalized points; Clear emits `[]`; eraser strokes have `erase: true`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.

### Task 10: Multiple choice on the crop

**Files:**
- Create: `src/components/exam/McOverlay.vue`, `McButtonList.vue`
- Modify: `SubtaskBlock.vue`
- Test: `src/components/exam/__tests__/Mc.spec.ts`

**Interfaces:**
- `<McOverlay :options="McOption[]" :region-index :ticks @toggle="(i: number) => void">` — absolutely positioned hit areas over the crop using percentage `left/top/width/height` from the option bbox (padded 30 %), ✕ mark when ticked; option `text` region to the right is also clickable when `text` is non-empty.
- `<McButtonList :options :ticks @toggle>` — fallback when options have no usable bbox (all bbox fields 0): buttons in order with their text.
- Ticks are stored as option indices in `answers[id].ticks`.

- [ ] **Step 1: Write failing tests** with the GRNVS 2019 6e fixture (6 options, bbox x0 0.027/0.526): renders 6 hit areas at `left: 2.7%`-ish (assert style contains `%`), clicking the 2nd emits `toggle(1)`; ticked index shows ✕; options with zero bboxes render `McButtonList` instead.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.

### Task 11: Exam modals (attendance, time up, hand in)

**Files:**
- Create: `src/components/exam/ExamModals.vue`
- Modify: `ExamView.vue`
- Test: `src/components/exam/__tests__/ExamModals.spec.ts`

**Interfaces:**
- Consumes store `modal`, `finishAttendance`, `extend`, `requestHandIn`, `cancelHandIn`, `handIn`.
- Copy (exact): attendance — title "Attendance check", body "A tutor is checking your ID. Please wait.", a 5-second countdown, not dismissible, calls `finishAttendance()` at 0. Time up — title "Time is up", body "The exam has ended. Please hand in.", buttons "Hand in" (primary) and "Keep going". Hand in — title "Hand in?", body "You can't change your answers afterwards.", buttons "Hand in" and "Back to exam". After `handIn()` navigate to `results`.

- [ ] **Step 1: Write failing tests:** attendance modal has no close button and calls `finishAttendance` after 5 s of fake time; time-up "Keep going" calls `extend`; "Hand in" in either dialog ends at the results route.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement with `Modal.vue`.
- [ ] **Step 4:** Run → PASS.

### Task 12: Results — time

**Files:**
- Create: `src/views/ResultsView.vue`, `src/components/results/TimeStats.vue`, `TimeBars.vue`
- Test: `src/components/results/__tests__/TimeStats.spec.ts`, `TimeBars.spec.ts`

**Interfaces:**
- `<TimeStats :attempt :exam>`: "within the limit" = `min(handedInAt − startedAt, timeLimitMs)`; "overtime" = the rest (row hidden when 0 — Review Focus 2); "subtasks answered in time" = `isAnswered` over `snapshot ?? answers`, out of included subtasks.
- `<TimeBars :attempt :exam>` behind a "Time per subtask · show" toggle: rows `"2 b)"` with bar width relative to the max, value `formatClock(main+over)`, sorted descending, excluded tasks absent.
- `ResultsView` (inside AppFrame): kicker "Handed in · {title}", heading "Done. Here is how you used your time.", TimeStats, TimeBars, then the grading section (Task 13). Layout per `results-v1.html`.

- [ ] **Step 1: Write failing tests:** handed in at limit − 5 min → no overtime row; handed in at limit + 12:40 → "+12:40"; bars sorted descending; answered-in-time uses the snapshot.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.

### Task 13: Grading and scores

**Files:**
- Create: `src/components/results/GradingList.vue`, `src/components/ui/PointsPicker.vue`, `src/lib/solution.ts`
- Modify: `ResultsView.vue`, `src/stores/library.ts` (add `attachSolution`)
- Test: `src/lib/__tests__/solution.spec.ts`, `src/components/results/__tests__/GradingList.spec.ts`

**Interfaces:**
- `solution.ts`: `matchSolution(exam: ExamStructure, solution: ExamStructure): Record<string /* exam subtask id */, Subtask /* solution subtask */>` — match by identical subtask id; for unmatched ids fall back to same task number + same label.
- `useLibraryStore().attachSolution(attemptId, file): Promise<void>` — `uploadExam(file, 'solution')`, stores it as its own exam (with ink images), sets `attempt.solutionExamId`.
- `<PointsPicker v-model :max>`: when `max` is a number, buttons 0..max in 0.5 steps; when `null`, a number input (Review Focus 3).
- `<GradingList :mode="'solution'|'self'">`: per included subtask a row with title, the student's answer (text; drawing rendered read-only via `DrawCanvas` in readonly mode; MC ticks drawn on the crop; "Answered on paper"), the solution crop (ink variant: from the same exam when `hasInk`, else from the matched solution exam) in `'solution'` mode, and one `PointsPicker` → `setGrade({main})`, or two labelled "In time" / "Overtime" when `changedInOvertime` (the "In time" one shows the snapshot answer). MC subtasks with `mc_key` show the automatic points with an "Override" link that reveals the picker.
- Buttons above the list: "Compare with solution" (enabled when `hasInk` or `solutionExamId`; otherwise it opens a solution upload drop zone), "Grade myself", "Ask an LLM to grade" (disabled, "coming soon").
- Score header: main score large ("62 / 90"), overtime score smaller ("With overtime 71 / 90"), only when `scores().over !== null`.

- [ ] **Step 1: Write failing tests:** `matchSolution` by id and by task+label fallback; GradingList shows two pickers only for subtasks changed in overtime; picking 1.5 calls `setGrade(id, {main: 1.5})`; MC subtask with key shows auto points and no picker until "Override"; "Ask an LLM to grade" disabled.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS. Full suite `npx vitest run` and `npm run type-check` pass.

---

## Track 2 — Pipeline additions

### Task 14: Exam duration and MC grading rule

**Files:**
- Create: `backend/app/pipeline/meta.py`, `backend/tests/test_meta.py`
- Modify: `backend/app/pipeline/models.py` (`ExamStructure.duration_minutes: int | None = None`, `ExamStructure.mc_rule: McRule | None = None` with `McRule(kind: Literal['all_or_nothing','per_tick'], right: float = 1, wrong: float = 0, floor: float = 0)`), `structure.py` (call both on the front-matter lines and on task-1 context text)

**Interfaces:**
- `parse_duration(texts: list[str]) -> int | None`; `parse_mc_rule(texts: list[str]) -> McRule | None`.

- [ ] **Step 1: Write failing tests** with real strings: `"Uhrzeit: 11:30–13:00"` → 90; `"Uhrzeit: 11:00-12:30"` → 90; `"Die Arbeitszeit beträgt 150 Minuten."` → 150; `"Bearbeitungszeit: 90 Minuten"` → 90; unrelated text → None. MC rule: `"Teilaufgaben mit mehr als einer richtigen Antwort werden mit 1 Punkt pro richtigem und -1 Punkt pro falschem Kreuz bewertet"` + `"Die minimale Punktzahl pro Teilaufgabe beträgt 0 Punkte"` → `per_tick(1, -1, 0)`; `"Bei Multiple Choice Fragen müssen alle Antworten korrekt angekreuzt sein"` → `all_or_nothing`; nothing → None. Sample-based (skipif): `grnvs/retake_2024.pdf` → `duration_minutes == 90` and `mc_rule.kind == 'per_tick'`.
- [ ] **Step 2:** Run `pytest tests/test_meta.py -q` → FAIL.
- [ ] **Step 3:** Implement (regexes tolerant to missing spaces, since some PDFs lose them).
- [ ] **Step 4:** Run → PASS; batch `python -m app.pipeline.cli ../samples --no-debug` shows no new errors.

### Task 15: MC options and answer key

**Files:**
- Create: `backend/app/pipeline/mc.py`, `backend/tests/test_mc.py`
- Modify: `models.py` (`McOption(region: int, bbox: BBox, text: str)`; `Subtask.mc_options: list[McOption] = []`, `Subtask.mc_key: list[int] | None = None`), `extract.py` (keep checkbox candidates: rects 5–14 pt square, and box/circle glyph chars from fonts like `MSAM10` `(cid:3)`, `LCIRCLE10`), `structure.py` (attach options per subtask after regions are known)

**Interfaces:**
- `find_options(page: Page, region: Region, region_index: int) -> list[McOption]` — boxes inside the region in reading order (row, then x); `bbox` relative 0..1 to the region bbox; `text` = body text on the same line right of the box up to the next box. A subtask is MC when it has ≥ 2 options.
- `answer_key(pdf_path, page_index, options_abs: list[BBox]) -> list[int]` — for solution exams, an option is ticked when solution-ink objects (the bluish test from `render._is_solution_ink`) overlap its absolute box by ≥ 30 %.

- [ ] **Step 1: Write failing tests** (skipif samples missing): `grnvs/endterm_2019.pdf` subtask `A6e` has 6 options, sorted rows first, first option bbox `x0 ≈ 0.027 ± 0.01`, `y0 ≈ 0.282 ± 0.02`, and option texts contain `"Signalpegel"` for one of them; `A2b` (free text) has none. `grnvs/endterm_2019-solution.pdf` `A6e` has non-empty `mc_key`, every index < 6; `endterm_2019.pdf` (no ink) has `mc_key is None`. Pure unit test of the row/column ordering helper with synthetic boxes.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS; frontend `McOverlay` shows them (manual check with GRNVS 2019 6e).

### Task 16: End-to-end acceptance

**Files:** none new (fixes go to the owning task's files).

- [ ] **Step 1:** Start `fastapi dev main.py` and `npm run dev`. For each of `grnvs/endterm_2019-solution.pdf`, `gbs/2023 Endterm Lösungsvorschlag.pdf`, `it-sec/23_retake.pdf`: upload → settings (duration prefilled; MC rule shown) → start → attendance check appears within 30 min (temporarily set `attendanceAt` low via devtools to verify) → answer by typing, drawing and MC on the crop → let the limit pass (set a 1-min limit) → "Keep going", change one answer → hand in → time stats and bars → Compare with solution → two pickers for the changed subtask → main and overtime scores.
- [ ] **Step 2:** Reload during the exam and during results; everything persists.
- [ ] **Step 3:** Run the full suites: `npx vitest run`, `npm run type-check`, `pytest -q`. All pass.
