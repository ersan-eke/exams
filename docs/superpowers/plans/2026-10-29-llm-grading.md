# LLM Grading + Eval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "Ask an LLM to grade" grades every included subtask with the user's own key on Anthropic, Google AI Studio
or OpenRouter — against the solution's point guide when there is one, else with the model's own solution plus
same-subject references — shows the result as a card per subtask plus a per-task summary, and an offline eval
compares it with the user's self-grades.

**Architecture:** The client builds one JSON request per subtask version from IndexedDB (crops as base64 PNG, answer
text + rendered drawing, solution or references, saved rubric) and POSTs it with `X-LLM-Key` to `/api/grade`. The
server turns it into provider-neutral prompt items, hands them to one provider adapter, validates the model's JSON,
clamps the numbers, and streams SSE events (`thinking`* → `done` | `error`). The attempt store runs up to 3 requests
at a time, can stop them, and saves solution rubrics on the solution exam.

**Tech Stack:** FastAPI + `fastapi.sse.EventSourceResponse`, Pydantic v2, `anthropic`, `google-genai`, `openai`
(for OpenRouter); Vue 3 + Pinia + IndexedDB, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-29-llm-grading-design.md`

## Global Constraints

- Providers and models (server allow-list): `anthropic`: `claude-sonnet-5-5` (default), `claude-haiku-5-5`;
  `google`: the Gemini Flash id (default) and the Gemini Pro id confirmed in Task 1; `openrouter`: any id matching
  `^[\w.\-]+/[\w.\-:]+$`, ≤ 100 chars, default chosen in Task 1 (reads images + supports structured outputs). Anything else → 422.
- Base URLs fixed in code (OpenRouter `https://openrouter.ai/api/v1`), never from the request.
- Key only from header `X-LLM-Key`; never stored, logged, or in any response/event/error text.
- Anthropic: `thinking={"type": "adaptive", "display": "summarized"}`, `max_tokens=16000`; Sonnet only:
  `fallbacks="default"` + beta `server-side-fallback-2026-07-01`; prompt caching via the `CacheBreak` item.
- SSE events: `{"type": "thinking", "text"}`, `{"type": "done", "grade"}`, `{"type": "error", "code"}`.
- Error codes: `no_key` (400), `rate_limited` (our 429 or any upstream 429), `bad_key`, `no_credits`, `refused`, `llm_failed`.
- Server never trusts model numbers: clamp to `0..max`, `min ≤ points ≤ max`, `certain = (min == max)`,
  `basis = "solution" if solution else "own_solution"`.
- Request caps: ≤ 20 images total, each ≤ 4,000,000 base64 chars and a PNG; each text ≤ 20,000 chars; ≤ 3 references;
  `points` in `(0, 1000]`; `Content-Length` ≤ 25,000,000 → else 413. Rate limit: 30 / 60 s per client IP.
- Feedback and notes are plain text (no Markdown): one-line rubric notes, feedback ≤ 4 short sentences.
- Client concurrency 3. The LLM grade never overwrites the self-grade.
- `backend/evals/grading/cases.jsonl` gitignored. `uv` only. Deliberate simplifications get a `shortcut:` comment.

## Review Focus

- Answer that is only a drawing (no text): the request must carry the rendered drawing. → Task 7.
- Switching to another attempt while a pass runs: late results must not land on the new attempt. → Task 8.
- A key pasted with spaces/newline: trimmed before it goes in the header. → Task 7.
- Subtask without point value, unanswered, or MC with a key: not sent, the row says why. → Task 7, Task 9.
- A model that returns prose or broken JSON (common on OpenRouter/free models): `llm_failed`, not a crash or a half grade. → Task 1.

---

### Task 1: Grading core (models, prompt items, grader)

**Files:**
- Modify: `backend/pyproject.toml`, `backend/uv.lock` (`uv add anthropic google-genai openai`)
- Create: `backend/app/grading/__init__.py`, `models.py`, `prompt.py`, `grader.py`, `providers/__init__.py`
- Test: `backend/tests/test_grading.py`

**Interfaces:**
- Produces (`app.grading.models`):
  `Part(text: str = "", images: list[Png] = [])` (`Png` = str validated as base64 → bytes starting `b"\x89PNG"`);
  `RubricLine(item: str, max: float, source: Literal["solution", "inferred"])`; `Solution(Part)(rubric: list[RubricLine] = [])`;
  `Reference(question: Part, solution: Solution, points: float)`;
  `Provider = Literal["anthropic", "google", "openrouter"]`; `MODELS: dict[str, tuple[str, ...]]` for anthropic/google, `DEFAULT_MODEL: dict[Provider, str]`;
  `GradeIn(provider: Provider = "anthropic", model: str | None = None /* → DEFAULT_MODEL */, points: float, question: Part, solution: Solution | None = None, references: list[Reference] = [], answer: Part)`
  with validators for the allow-list and the total image count;
  `LlmLine(item, max, hit: float, note: str, source)`; `LlmOut(points, points_min, points_max: float, rubric: list[LlmLine], feedback: str)`;
  `GradeOut(LlmOut)(certain: bool, basis: Literal["solution", "own_solution"], provider: Provider, model: str)`.
- Produces (`app.grading.prompt`): `PROMPT_VERSION = "2026-10-29.1"`, `SYSTEM_SOLUTION`, `SYSTEM_OWN`,
  `system_for(req) -> str`; items `Text(text: str)`, `Image(png: bytes)`, `CacheBreak()` (dataclasses);
  `build_content(req: GradeIn) -> list[Text | Image | CacheBreak]`.
- Produces (`app.grading.grader`): `class GradingError(Exception)` with `.code`; `Thinking(text)`, `Final(text, model)`;
  `Adapter = Callable[[GradeIn, str, str, list[Item]], AsyncIterator[Thinking | Final]]`;
  `ADAPTERS: dict[Provider, Adapter]` (filled by Tasks 2–4; tests insert fakes);
  `finalize(out: LlmOut, max_points: float, basis, provider, model) -> GradeOut`;
  `async def grade_stream(req: GradeIn, key: str) -> AsyncIterator[dict]` (the SSE events);
  `async def grade(req, key) -> GradeOut` (raises `GradingError`).

- [ ] **Step 1: `cd backend && uv add anthropic google-genai openai`.** Confirm call shapes for Tasks 2–4 now, so their
  implementers don't guess: Anthropic via the claude-api skill (`python/claude-api/streaming.md`, structured outputs in
  `tool-use.md`, whether `fallbacks` is a kwarg or `extra_body`, schema helper such as `anthropic.transform_schema`);
  Google via Context7 `/googleapis/python-genai` (async stream, `response_schema`, `ThinkingConfig(include_thoughts=True)`
  and how thought parts are flagged, error classes and codes, current Flash/Pro model ids and free-tier availability);
  OpenRouter via Context7 `/websites/openrouter_ai` (`response_format` json_schema strict, `provider.require_parameters`,
  `content_filter` finish reason, a current default model that reads images and supports structured outputs).
  Append the findings to "Call shapes" at the end of this plan — no adapter code yet.
- [ ] **Step 2: Write failing tests** in `backend/tests/test_grading.py` (a fake adapter in `ADAPTERS["anthropic"]`):
  - `test_finalize_clamps_and_orders`: max 4; `(points=5, points_min=-1, points_max=9)` → `4, 0, 4, certain False`;
    `(points=3, points_min=3.5, points_max=2)` → `min 3, max 3, certain True`.
  - `test_basis_follows_solution`: with a solution the adapter gets `SYSTEM_SOLUTION` and `done.grade.basis == "solution"`;
    without, `SYSTEM_OWN` / `"own_solution"`; `done.grade.provider/model` = request's.
  - `test_items_order`: question text + images → solution text, saved rubric lines as text, solution images (or each
    reference) → exactly one `CacheBreak` → `"Max points: N"` → answer text + images.
  - `test_thinking_then_done`: fake yields `Thinking("a")`, `Thinking("b")`, `Final(json)` → events `thinking a`, `thinking b`, `done`.
  - `test_invalid_json_is_llm_failed`: `Final("Sure! Here is the grade: …")` and `Final('{"points": 1}')` → `error llm_failed`.
  - `test_adapter_error_code_passes_through`: fake raises `GradingError("no_credits")` → `error no_credits`.
  - `test_unexpected_exception_is_llm_failed_and_key_not_logged`: fake raises `RuntimeError(key)`; with `caplog` at DEBUG
    the key appears in no record and no event.
  - `test_rejects_bad_input`: non-PNG base64; 21 images; 4 references; `points=0`; `provider="anthropic", model="gpt-4o"`;
    `provider="openrouter", model="bad id"` → `ValidationError`; `provider="google"` without model → its default.
- [ ] **Step 3: Run** `uv run pytest tests/test_grading.py -v` → FAIL.
- [ ] **Step 4: Implement.** Prompts: `SYSTEM_SOLUTION` — first read the point split from the saved rubric (wins) or the
  solution's guide, then grade strictly against it, no own view of correctness; guide lines `source "solution"`, lines it
  had to infer `"inferred"`. `SYSTEM_OWN` — solve first, build a rubric (all `"inferred"`), then grade; references show how
  this course hands out points, they are not the answer. Both: widen `points_min/points_max` only when the answer is
  genuinely ambiguous or unreadable; plain text, no Markdown; reply with the JSON only. `grade_stream` catches
  `GradingError` → its code, any other exception → `llm_failed`, logging only `type(e).__name__`.
- [ ] **Step 5: Run** → PASS. **Step 6: Commit** `git commit -m "Grading core: models, prompt items, grader"`

### Task 2: Anthropic adapter

**Files:** Create `backend/app/grading/providers/anthropic.py`; Test `backend/tests/test_providers.py`

**Interfaces:** Consumes Task 1 types. Produces `async def stream(req, key, system, items)` registered as `ADAPTERS["anthropic"]`.
Monkeypatch point for tests: module-level `AsyncAnthropic`.

- [ ] **Step 1: Failing tests** (fake `AsyncAnthropic`: `.beta.messages.stream(**kw)` records kwargs, async context manager
  iterating given events, `get_final_message()` → `.content`, `.stop_reason`, `.model`; `__aexit__` recorded):
  - request: images as base64 `image` blocks, `cache_control` on the block before the `CacheBreak`, system passed,
    `thinking.display == "summarized"`, structured-output schema from `LlmOut`; Sonnet sends the fallback beta and
    `fallbacks == "default"`, Haiku sends neither.
  - `thinking_delta` events → `Thinking`; final text → `Final(text, message.model)`.
  - errors: `AuthenticationError` → `bad_key`; `RateLimitError` → `rate_limited`; `APIConnectionError` and other
    `APIStatusError` → `llm_failed`; `stop_reason == "refusal"` → `refused`.
  - closing the generator after the first `Thinking` runs the fake's `__aexit__`.
- [ ] **Step 2: Run** `uv run pytest tests/test_providers.py -k anthropic -v` → FAIL. **Step 3: Implement** per "Call shapes".
  **Step 4: Run** → PASS. **Step 5: Commit** `git commit -m "Anthropic grading adapter"`

### Task 3: Google AI Studio adapter

**Files:** Create `backend/app/grading/providers/google.py`; Test `backend/tests/test_providers.py`

**Interfaces:** Produces `stream(...)` registered as `ADAPTERS["google"]`. Monkeypatch point: module-level `genai.Client`.

- [ ] **Step 1: Failing tests** (fake client: `client.aio.models.generate_content_stream(model, contents, config)` records args,
  returns an async iterator of chunks with parts):
  - request: `Image` items → `types.Part.from_bytes(data, mime_type="image/png")`, text items as text parts,
    `CacheBreak` dropped; config has the system instruction, `response_mime_type="application/json"`, the `LlmOut`
    schema, thought summaries on.
  - thought parts → `Thinking`; answer parts joined → `Final(text, model)`.
  - errors: invalid key (400 with API_KEY_INVALID, 401, 403) → `bad_key`; 429 → `rate_limited`; blocked prompt or a
    `SAFETY` finish → `refused`; other API and connection errors → `llm_failed`.
  - closing the generator mid-stream stops the upstream iterator (fake records `aclose`).
- [ ] **Step 2: Run** `-k google` → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `git commit -m "Google AI Studio grading adapter"`

### Task 4: OpenRouter adapter

**Files:** Create `backend/app/grading/providers/openrouter.py`; Test `backend/tests/test_providers.py`

**Interfaces:** Produces `stream(...)` registered as `ADAPTERS["openrouter"]`. Monkeypatch point: module-level `AsyncOpenAI`.

- [ ] **Step 1: Failing tests** (fake `AsyncOpenAI(base_url, api_key)`; `chat.completions.create(stream=True, **kw)` returns an
  async iterator of chunks):
  - client built with `base_url="https://openrouter.ai/api/v1"`; messages: system + one user message whose content is
    `text` / `image_url` (`data:image/png;base64,…`) parts, `CacheBreak` dropped; `response_format` json_schema `strict` from
    `LlmOut`; `provider.require_parameters` sent (as Task 1 found).
  - content deltas joined → `Final(text, chunk.model)`; no `Thinking`. `shortcut:` comment: reasoning deltas later.
  - errors: `AuthenticationError` → `bad_key`; status 402 → `no_credits`; `RateLimitError` → `rate_limited`;
    `finish_reason == "content_filter"` → `refused`; others → `llm_failed`.
- [ ] **Step 2: Run** `-k openrouter` → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `git commit -m "OpenRouter grading adapter"`

### Task 5: `POST /api/grade` route + limits

**Files:** Create `backend/app/grading/limits.py`; Modify `backend/app/api/routes.py`; Test `backend/tests/test_grading_api.py`

**Interfaces:** Consumes `GradeIn`, `grade_stream`. Produces `RateLimiter(limit: int = 30, window: float = 60.0)` with
`allow(client: str, now: float | None = None) -> bool`, module-level `grade_limiter`; route `POST /api/grade`.

- [ ] **Step 1: Failing tests** (`TestClient(app)`; a fake adapter in `ADAPTERS`; reset `grade_limiter`):
  `test_missing_key_400` (no header and `"  "` → `detail.code == "no_key"`); `test_too_large_413` (`Content-Length: 25000001`);
  `test_invalid_body_422`; `test_streams_events` (content-type `text/event-stream`, last `data:` event `done`);
  `test_error_event` (adapter raises `GradingError("bad_key")` → 200, last event `error bad_key`, key not in body);
  `test_rate_limit_31st` (31st → 429 `rate_limited`; `allow` with `now` past the window lets calls through again).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** The route takes `request: Request` and reads the body itself so the
  size check runs first: `content-length` → 413, key → 400, limiter on `request.client.host` → 429, then
  `GradeIn.model_validate_json(await request.body())` (→ 422), then `EventSourceResponse` over `grade_stream` like
  `job_events`. `shortcut:` comments: limiter in-memory per process; IP is the direct peer (read the forwarded header
  behind a proxy); chunked bodies without `Content-Length` skip the size check.
- [ ] **Step 4: Run** `uv run pytest -v` (whole suite, DB up) → PASS. **Step 5: Commit** `git commit -m "POST /api/grade with size cap and rate limit"`

### Task 6: Eval runner

**Files:** Create `backend/evals/__init__.py`, `backend/evals/grading/__init__.py`, `run_eval.py`, `README.md`;
Modify `.gitignore` (`/backend/evals/grading/cases.jsonl`); Test `backend/tests/test_eval.py`

**Interfaces:** Consumes `grade`, `GradingError`, `GradeIn`, `GradeOut`, `DEFAULT_MODEL`, `PROMPT_VERSION`. Case line:
`{"id": str, "expected": float, "request": GradeIn}`. Produces `metrics(rows: list[tuple[float, GradeOut]]) -> dict`
(`n`, `exact` = share with `|points − expected| < 1e-9`, `in_range`, `mae`, `calibration` = share of `certain` rows
that are exact, or `None`) and `main(argv) -> Path`.

- [ ] **Step 1: Failing test** `test_metrics`: rows `(2, out(2,2,2))`, `(1, out(points=3,min=0,max=4))`, `(4, out(2,2,2))` →
  `n 3, exact 1/3, in_range 2/3, mae 4/3, calibration 1/2`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**: `--provider` (default `anthropic`) and `--model` (default the provider's
  default) override each case; key from `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `OPENROUTER_API_KEY` (exit with a message
  when unset); each case in `solution` mode when it has one and in `own_solution` mode with `solution=None`; failures counted
  per code, not scored. Report `backend/evals/grading/results/<YYYY-MM-DD>-<provider>-<model slug>.md`: provider, model,
  `PROMPT_VERSION`, case count, a metrics table per basis, failure counts. Run from `backend/`:
  `uv run python -m evals.grading.run_eval --provider google evals/grading/cases.jsonl`. README: exporting cases (Task 9,
  dev server only), running, what each metric means, comparing providers; the cases file holds exam crops and stays
  uncommitted; free tiers may use inputs for training — check the provider's terms.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `git commit -m "Grading eval runner"`

### Task 7: Client grading library + provider settings

**Files:** Modify `frontend/src/stores/settings.ts`, `components/frame/SettingsPanel.vue`, `types/attempt.ts`,
`components/exam/DrawCanvas.vue`; Create `frontend/src/lib/strokes.ts`, `frontend/src/lib/grading.ts`;
Test `stores/__tests__/settings.spec.ts`, `lib/__tests__/grading.spec.ts`

**Interfaces:**
- `types/attempt.ts`: `Provider = 'anthropic' | 'google' | 'openrouter'`; `RubricLine {item: string; max: number; source: 'solution' | 'inferred'}`;
  `LlmGrade {points; min; max: number; certain: boolean; basis: 'solution' | 'own_solution'; provider: Provider; model: string;
  rubric: (RubricLine & {hit: number; note: string})[]; feedback: string}`; `Grade.llm?: Partial<Record<'main' | 'over', LlmGrade>>`;
  `StoredExam.rubrics?: Record<string, RubricLine[]>`.
- settings: `provider: Provider` (default `'anthropic'`), `keys: Record<Provider, string>` (all `''`),
  `models: Record<Provider, string>` (defaults = server defaults from Task 1); callers read `keys[provider]` / `models[provider]`.
- `lib/strokes.ts`: `paintStroke(c: CanvasRenderingContext2D, s: Stroke, w: number, h: number): void` (moved from DrawCanvas).
- `lib/grading.ts`:
  - `GradePart {text: string; images: string[]}`, `GradeSolution extends GradePart {rubric: RubricLine[]}`,
    `GradeReference {question: GradePart; solution: GradeSolution; points: number}`,
    `GradeRequest {provider: Provider; model: string; points: number; question: GradePart; solution: GradeSolution | null; references: GradeReference[]; answer: GradePart}`.
  - `Version = 'main' | 'over'`; `SkipReason = 'no_points' | 'no_answer' | 'auto'`;
    `skipReason(task, subtask, answer: Answer | undefined, mcKey: number[] | null): SkipReason | null`.
  - `similarSubtasks(subtask, exams: StoredExam[], subject: string, excludeExamIds: string[]): {exam; task; subtask}[]`.
  - `LlmJob {key: string /* `${subtaskId}:${version}` */; subtaskId: string; version: Version; build: () => Promise<GradeRequest>; rubricTarget: {examId: string; subtaskId: string} | null}`.
  - `planGrading(ctx: {exam: StoredExam; attempt: Attempt; solutionExam: StoredExam | null; keys: Record<string, number[]>;
    library: StoredExam[]; provider: Provider; model: string; withReferences?: boolean}): {jobs: LlmJob[]; skipped: Record<string, SkipReason>}`.
  - `class GradeError extends Error { code: string }`; `gradeErrorMessage(code: string): string`;
    `streamGrade(body: GradeRequest, key: string, signal: AbortSignal, onThinking: (text: string) => void): Promise<LlmGrade>`;
    `sseEvents(buffer: string): {events: unknown[]; rest: string}`;
    `evalCasesJsonl(cases: {id: string; expected: number; request: GradeRequest}[]): string`.

- [ ] **Step 1: Failing tests.**
  - settings: defaults as above; persisted like the other fields; an unknown stored `provider` or a missing `keys`/`models`
    entry falls back to the defaults.
  - `skipReason`: max null → `'no_points'`; unanswered → `'no_answer'`; MC with key → `'auto'`; MC without key but ticked → `null`.
  - `similarSubtasks`: same subject + solution (`hasInk` or `structure.is_solution`) only, never another subject; ranked by
    word overlap; at most 2; overlap below 0.2 dropped; `excludeExamIds` respected.
  - `planGrading` (mock `getImage` via `vi.mock('@/lib/db')`, mock the canvas render):
    every request carries `ctx.provider`/`ctx.model`; matched solution → `solution` with ink crops and `rubric` from
    `solutionExam.rubrics`, no references, `rubricTarget` = solution exam + matched subtask; `hasInk` exam → question `blank`,
    solution `ink`, same exam; unmatched or no solution → `solution: null`, references, `rubricTarget: null`;
    `withReferences: true` + a match → both filled; overtime-changed subtask → `:main` (from `attempt.snapshot`) and `:over` jobs;
    MC without key → `answer.text` lists ticked option texts; **drawing-only answer → `answer.images.length === 1`**;
    skipped subtasks only in `skipped`.
  - `sseEvents`: `'data: {"a":1}\n\ndata: {"b"'` → one event, rest `'data: {"b"'`; rest + `':2}\n\n'` → the second.
  - `streamGrade` (mocked `fetch`, `ReadableStream` body): header `X-LLM-Key` is the **trimmed** key (`' k\n'` → `'k'`);
    `thinking` → `onThinking`; `done` maps `points_min/points_max` → `min/max`; HTTP 400 `no_key`, 429 and event errors
    `bad_key`/`no_credits` reject with `GradeError` of that code; an aborted signal rejects with `AbortError`.
  - `gradeErrorMessage`: `bad_key` "Your API key was rejected.", `no_credits` "Your OpenRouter account has no credits left.",
    `rate_limited` "Rate limited, try again in a minute.", `refused` "The model declined to grade this subtask.",
    `no_key` "Add an API key in settings.", other "The LLM couldn't grade this."
- [ ] **Step 2: Run** `npx vitest run src/lib/__tests__/grading.spec.ts src/stores/__tests__/settings.spec.ts` → FAIL.
- [ ] **Step 3: Implement.** Reuse `crops`, `answerParts`, `sheetBlocks` (applying context), `subtaskTitle` (`lib/sheet.ts`),
  `maxPoints` (`lib/scoring.ts`), `matchSolution` (`lib/solution.ts`), `subjectOf` (`lib/stats.ts`), `isAnswered`/`onPaperOnly`
  (`lib/answers.ts`), `getImage` (`lib/db.ts`). Internal `answerImage(examId, part, strokes)`: stack the part's `blank` crops at
  natural width, paint with `paintStroke`, return base64 PNG, `null` without strokes; `shortcut:` strokes over the
  below-the-crops text field are scaled onto the crops. Word overlap: lowercase `\p{L}{4,}` tokens, Jaccard;
  `shortcut:` → Phase 4 vector search. SettingsPanel: provider radio (Anthropic / Google AI Studio / OpenRouter); one
  `<input type="password" autocomplete="off">` "API key" bound to `keys[provider]`; model `<select>` for anthropic
  ("Sonnet 5.5 (best)" / "Haiku 5.5 (about 20× cheaper, for testing)") and google ("Gemini Flash (free tier)" / "Gemini Pro"),
  text field for openrouter with hint "Pick a model that reads images"; hint "Stays on this device, sent only with grading
  requests." plus where to get the key (console.anthropic.com / aistudio.google.com / openrouter.ai).
- [ ] **Step 4: Run** `npx vitest run` → PASS (DrawCanvas tests still green). **Step 5: Commit** `git commit -m "Client grading requests, SSE reader, provider settings"`

### Task 8: Attempt store — run, stop, save rubrics

**Files:** Modify `frontend/src/stores/attempt.ts`; Test `stores/__tests__/attempt.spec.ts`

**Interfaces:** Consumes `LlmJob`, `SkipReason`, `streamGrade`, `GradeError`, `gradeErrorMessage`; `getExam`/`putExam`.
Produces on the store: `llm` (reactive, not persisted) `{pending: Record<string, string> /* job key → thinking so far */;
errors: Record<string, string>; skipped: Record<string, SkipReason>; total: number; done: number}`;
`gradeWithLlm(jobs: LlmJob[], skipped: Record<string, SkipReason>, key: string, opts?: {force?: boolean}): Promise<void>`
(without `force`, versions that already have an LLM grade are skipped); `regrade(jobKey: string, key: string): Promise<void>`;
`stopLlm(): void`.

- [ ] **Step 1: Failing tests** (mock `streamGrade`): at most 3 in flight, 5 jobs finish, `done === total === 5`; a result lands in
  `grades[id].llm[version]` and is saved while the self-grade stays untouched; `basis 'solution'` + `rubricTarget` → target exam
  re-read and saved with `rubrics[subtaskId]` = the `{item, max, source}` lines, `own_solution` saves nothing; a
  `GradeError('bad_key')` → `llm.errors[key]` is the message, other jobs continue; `stopLlm()` aborts in-flight signals, queued jobs
  never start, `pending` empties, finished grades stay, no error recorded; **attempt switch**: start, `load()` another attempt,
  resolve the pending call → nothing written to either; an already graded version is not re-sent without `force`, `regrade` sends it.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**: one `AbortController` per pass; `load()` calls `stopLlm()`; writes check the
  pass's attempt id; rubric save re-reads via `getExam` then `putExam({...e, rubrics: {...e.rubrics, [id]: lines}})`.
- [ ] **Step 4: Run** `npx vitest run` → PASS. **Step 5: Commit** `git commit -m "Attempt store: run, stop and save LLM grading"`

### Task 9: Grading UI — LLM card, summary, progress, results button, eval export

**Files:** Create `frontend/src/components/results/LlmCard.vue`, `LlmSummary.vue`; Modify `GradingRow.vue`, `GradingList.vue`,
`views/GradingView.vue`, `views/ResultsView.vue`; Test `components/results/__tests__/LlmCard.spec.ts`, `LlmSummary.spec.ts`,
`GradingList.spec.ts`, `views/__tests__/GradingView.spec.ts`, `ResultsView.spec.ts`

**Interfaces:** Consumes Task 7 (`planGrading`, `evalCasesJsonl`), Task 8 (`llm`, `gradeWithLlm`, `regrade`, `stopLlm`),
`listExams`, settings. Produces `LlmCard` props `{grade?: LlmGrade; max: number; pending?: string; error?: string; skipped?: SkipReason}`,
emits `regrade`; `LlmSummary` props `{exam: StoredExam; attempt: Attempt}`, emits `jump(subtaskId)`.

Layout (spec "Frontend layout of the LLM output"): the card sits under each answer version below the PointsPicker.
Header: `4 / 6 P` or `3–5 / 6 P · unsure`, right side basis ("from the solution" / "own solution") and a short model name.
Rubric table: marker (✓ hit = max, ◐ 0 < hit < max, ✗ hit = 0), item, `hit / max`, tag "guide" / "inferred", note below in
muted text. Then "Feedback: …" and a "Re-grade" link. Mobile (≤ 600px): item + points on one line, note below. Summary: one
line per task, chips `a) 4/6`, task total, "you: X P · LLM: Y P"; a chip click emits `jump`. Use the existing tokens and the
quiet button styles (`.mode`, `.btn`); follow `frontend-design:frontend-design` within the existing look.

- [ ] **Step 1: Failing tests.**
  - LlmCard: certain → `4 / 6 P`; uncertain → `3–5 / 6 P · unsure`; markers ✓/◐/✗ by hit; tags "guide"/"inferred"; feedback shown;
    pending → "grading…" + the thinking text; error → message + "Retry" emitting `regrade`; skipped `no_points` → "No point value",
    `no_answer` → "No answer, not sent", `auto` → renders nothing.
  - LlmSummary: renders only when some LLM grade exists; per task the chips and totals ("you" sums self-grades incl. automatic MC
    via `subtaskScore`, "LLM" sums LLM points of the version that counts — `over` if extended, else `main`); chip click emits `jump`.
  - GradingList: with `?llm=1` and the solution loaded, `gradeWithLlm` is called once with `planGrading`'s jobs (provider/model/key
    from settings) and the query is removed via `router.replace`; without the query it is not called.
  - GradingView: while `llm.done < llm.total` the top bar shows "<Provider> is grading · 2 / 5", a `role="progressbar"` with
    `aria-valuenow`/`aria-valuemax`, and "Stop" calling `stopLlm`; hidden when idle; LlmSummary above the list, `jump` scrolls the row
    into view.
  - ResultsView (replaces the "coming soon" test): no key for the chosen provider → disabled, hint "Add an API key in settings";
    with a key + solution → hint "using the solution", navigates to `grade` mode `solution` with `query.llm === '1'`; no solution →
    "no solution: the model solves it first", mode `self`; LlmSummary shown once LLM grades exist.
- [ ] **Step 2: Run** the spec files → FAIL.
- [ ] **Step 3: Implement.** GradingList waits until `useSolutionExam()` is not `undefined`, then
  `planGrading({..., library: await listExams()})`. Rows get an `id` anchor for `jump`. Dev-only (`import.meta.env.DEV`)
  "Export eval cases" link in the GradingView top bar: plan with `withReferences: true`, `build()` each job whose version has a
  self-grade, download `evalCasesJsonl(...)` as `cases.jsonl` (Blob + temporary `<a download>`).
- [ ] **Step 4: Run** `npx vitest run` → PASS; `npm run build` → OK. Start `npm run dev` + backend and look at a graded attempt at
  desktop and 375px width (fake a grade by writing `grades[id].llm` in devtools if no key) — card and summary read cleanly.
- [ ] **Step 5: Commit** `git commit -m "LLM grading UI: cards, summary, progress, stop, results button, eval export"`

### Task 10: Docs + full verification

**Files:** Create `docs/2026-10-29-llm-grading-handoff.md`; Modify `docs/roadmap.md` (Phase 2 status), `CLAUDE.md`
(latest handoff pointer; rule "The user's Anthropic key…" → "The user's LLM key (Anthropic, Google, OpenRouter)…").

- [ ] **Step 1:** `uv run pytest` (DB up) and `npx vitest run` → green; note counts in the handoff.
- [ ] **Step 2:** Handoff in the style of `docs/2026-10-29-subject-names-handoff.md`: done / not done (manual checks with a real key,
  eval not run on real cases, OpenRouter reasoning stream, lecturer-style summaries and vector references → Phase 4) /
  decisions already made (the spec's design calls) / where things live.
- [ ] **Step 3: Commit** `git commit -m "Docs: Phase 2 LLM grading handoff, roadmap status"`
- [ ] **Step 4 (user, free with a Google AI Studio key):** set provider + key; grade one attempt with and one without a solution;
  Stop mid-pass; a wrong key shows "rejected" per row; export cases and run
  `GOOGLE_API_KEY=... uv run python -m evals.grading.run_eval --provider google evals/grading/cases.jsonl`.

## Call shapes

Shared: `llm_schema()` in `app/grading/models.py` returns the strict JSON schema of `LlmOut` (`additionalProperties: false`,
all fields required, no `$ref`/`$defs`, no `default`). Adapters get `(req, key, system, items)` and map `Text`/`Image` items;
`CacheBreak` only matters to Anthropic (others skip it). Never put `key` in an exception message.

**Anthropic** (SDK 2.3.0, verified against signatures): `client = anthropic.AsyncAnthropic(api_key=key)`;
`async with client.beta.messages.stream(model=..., max_tokens=16000, system=[{"type":"text","text":system}], messages=[{"role":"user","content":blocks}], thinking={"type":"adaptive","display":"summarized"}, output_config={"format":{"type":"json_schema","schema":llm_schema()}}, betas=[...], fallbacks="default") as stream:`.
- `fallbacks`, `output_config`, `betas`, `thinking` are real kwargs of `beta.messages.stream`; no `extra_body` needed. `fallbacks="default"` needs `betas=["server-side-fallback-2026-07-01"]` (Sonnet only; for Haiku omit both).
- Blocks: `{"type":"text","text":..}`, `{"type":"image","source":{"type":"base64","media_type":"image/png","data":b64}}`; cache: `"cache_control":{"type":"ephemeral"}` on the last block before the `CacheBreak`.
- Iterate `async for event in stream`: `event.type == "content_block_delta"` with `event.delta.type == "thinking_delta"` (`.thinking`) or `"text_delta"` (`.text`). Final: `msg = await stream.get_final_message()`; `msg.stop_reason == "refusal"` -> `GradingError("refused")`; `msg.model` is the serving model; JSON text = concatenated text blocks (structured output guarantees valid JSON).
- Errors (`anthropic.*`): `AuthenticationError`/`PermissionDeniedError` -> `bad_key`, `RateLimitError` -> `rate_limited`, `APIStatusError` with `status_code == 402` -> `no_credits`; other -> `llm_failed`. `anthropic.transform_schema(schema)` exists if the schema needs adapting.
- Models: `claude-sonnet-5-5` (default), `claude-haiku-5-5`.

**Google** (`google-genai` 2.34.0): `client = genai.Client(api_key=key)`;
`stream = await client.aio.models.generate_content_stream(model=..., contents=[types.Content(role="user", parts=[types.Part(text=..), types.Part.from_bytes(data=png, mime_type="image/png")])], config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", response_schema=LlmOut, thinking_config=types.ThinkingConfig(include_thoughts=True)))`, then `async for chunk in stream`.
- Note the double `await`/`async for`: the call is awaited first, then iterated.
- Per chunk: `for part in chunk.candidates[0].content.parts`: `part.thought` truthy -> `Thinking(part.text)`, else append `part.text` to the answer. Guard `chunk.candidates` empty/None and `content` None.
- Blocked: `chunk.prompt_feedback.block_reason` set (candidates empty) or `candidate.finish_reason == types.FinishReason.SAFETY` -> `GradingError("refused")`.
- Errors: `google.genai.errors.APIError` (`.code` int, `.status` str, `.message`); subclasses `ClientError` (4xx), `ServerError` (5xx). 429 -> `rate_limited`; 400/401/403 with bad key (Google returns 400 `API_KEY_INVALID`) -> `bad_key`; else `llm_failed`.
- Models (Context7 confirms the aliases exist): `gemini-flash-latest` (default), `gemini-pro-latest`. Free-tier status: unconfirmed, needs a live key.
- Schema: pass the Pydantic class `LlmOut` itself as `response_schema` (the SDK converts it), NOT `llm_schema()`: Gemini's schema subset may reject `additionalProperties`.

**OpenRouter** (`openai` SDK 3.41.0): `client = openai.AsyncOpenAI(api_key=key, base_url="https://openrouter.ai/api/v1")`;
`stream = await client.chat.completions.create(model=..., stream=True, messages=[{"role":"system","content":system},{"role":"user","content":[{"type":"text","text":..},{"type":"image_url","image_url":{"url":"data:image/png;base64,.."}}]}], response_format={"type":"json_schema","json_schema":{"name":"grade","strict":True,"schema":llm_schema()}}, extra_body={"provider":{"require_parameters":True}})`.
- `provider.require_parameters` is not an openai SDK kwarg: pass through `extra_body`.
- Iterate `async for chunk in stream`: `delta = chunk.choices[0].delta` (guard empty `choices`); answer = `delta.content`; reasoning, when present, is non-standard (`getattr(delta, "reasoning", None)`) -> `Thinking`. `chunk.model` names the serving model.
- `choices[0].finish_reason == "content_filter"` -> `refused`.
- Errors (`openai.*`): `AuthenticationError` -> `bad_key`, `RateLimitError` -> `rate_limited`, `APIStatusError` with `status_code == 402` -> `no_credits`; other -> `llm_failed`.
- Default model: `google/gemini-2.5-flash` (confirmed against the public `GET /api/v1/models`: `architecture.input_modalities` = file, image, text, audio, video; `supported_parameters` includes `structured_outputs` and `response_format`). Ids must match `^[\w.\-]+/[\w.\-:]+$`.
