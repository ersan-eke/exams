# Phase 2 — LLM grading + eval (Anthropic, Google AI Studio, OpenRouter)

## Context

Roadmap Phase 2 (`docs/roadmap.md`). The user skipped brainstorming: the roadmap's Phase 2 section plus the
answers in this session are the spec. The "Ask an LLM to grade" button on the results page (today disabled,
"coming soon") grades every included subtask with an LLM, using the user's own key. With a solution, it grades
strictly by the solution's point guide; without one, it solves the subtask itself, with same-subject solved
subtasks as references. Plus an offline eval against the user's own self-grades.

New in this revision (user's requests): **three providers** — Anthropic, Google AI Studio (Gemini, has a free
tier) and OpenRouter (one key, many models) — so testing doesn't have to cost money; error codes and output shape
are the same for all; streaming stays where it is cheap, and the LLM result is laid out nicely per subtask.

Branch `phase-2-llm-grading`. Plan: `docs/superpowers/plans/2026-10-29-llm-grading.md`.

## Providers and models

| Provider | Key from | Models offered | Structured output | Live reasoning |
|---|---|---|---|---|
| `anthropic` | console.anthropic.com | `claude-sonnet-5-5` (default), `claude-haiku-5-5` (~20× cheaper) | `output_config.format` json_schema | yes (`display: "summarized"`) |
| `google` | aistudio.google.com | Gemini Flash (default, free tier), Gemini Pro | `response_mime_type="application/json"` + `response_schema=LlmOut` | yes (thought summaries, `include_thoughts`) |
| `openrouter` | openrouter.ai | free-text model id, default = a current vision + structured-output model | `response_format` json_schema `strict` | no (`shortcut:`, add reasoning deltas later) |

- SDKs: `anthropic` (`AsyncAnthropic`, beta messages stream), `google-genai` (`client.aio.models.generate_content_stream`,
  `types.Part.from_bytes`), `openai` (`AsyncOpenAI(base_url="https://openrouter.ai/api/v1")`, chat completions stream).
  Task 1 confirms every call shape and the exact Gemini model ids / OpenRouter default via Context7 + the claude-api skill.
- Server-side allow-list: `anthropic` and `google` accept only their listed ids; `openrouter` accepts an id matching
  `^[\w.\-]+/[\w.\-:]+$` (≤ 100 chars). Base URLs are fixed in code, never taken from the request.
- OpenRouter requests send `provider: {"require_parameters": true}` so they only route to providers that honour
  `response_format` (confirm the field in Task 1).
- Refusal fallback (`fallbacks="default"` + beta `server-side-fallback-2026-07-01`) only on Sonnet.
- Settings hint per provider: where to get a key, and for OpenRouter "pick a model that reads images".
  README notes that free tiers may use inputs for training — check the provider's terms (exam crops).

## Shared design (all providers)

- **One endpoint** `POST /api/grade`, body `GradeIn` with `provider` + `model`, key in header **`X-LLM-Key`**
  (never stored, logged or echoed; CLAUDE.md rule widened from "Anthropic key" to "LLM key").
- **Provider boundary:** `prompt.build_content(req)` returns provider-neutral items (`Text`, `Image(png bytes)`,
  `CacheBreak`); each adapter in `app/grading/providers/{anthropic,google,openrouter}.py` exposes
  `async def stream(req, key, system, items) -> AsyncIterator[Thinking | Final]` (`Final(text, model)`) and raises
  `GradingError(code)`. `grader.grade_stream` picks the adapter, validates `Final.text` with
  `LlmOut.model_validate_json` (invalid → `llm_failed`), runs `finalize`, and yields the SSE events.
  Adding a provider later = one adapter + allow-list entry + tests.
- **SSE events** (same for all): `{"type":"thinking","text"}` (only providers that have it), `{"type":"done","grade"}`,
  `{"type":"error","code"}`. Before the stream (plain HTTP): 400 `no_key`, 413 too large, 429 `rate_limited` (ours),
  422 invalid body.
- **Error codes** (same for all, mapped per adapter, never echoing exception text):
  `bad_key` (Anthropic 401, Google 400 API_KEY_INVALID/401/403, OpenRouter 401), `no_credits` (OpenRouter 402),
  `rate_limited` (429 from any), `refused` (Anthropic `stop_reason refusal` after fallback, Google blocked prompt /
  `SAFETY` finish, OpenRouter `content_filter`), `llm_failed` (everything else, incl. invalid JSON).
- **Output** (same for all): `GradeOut {points, points_min, points_max, certain, basis, provider, model,
  rubric: [{item, max, hit, note, source: "solution"|"inferred"}], feedback}`. Server clamps to `0..max`,
  `min ≤ points ≤ max`, `certain = min == max`, `basis = "solution" if solution else "own_solution"`.
  Prompt asks for plain text (no Markdown): one-line rubric notes, feedback ≤ 4 short sentences.
- Kept from before: Stop (abort per pass, server generator closes upstream), concurrency 3, progress bar, Retry /
  Re-grade, per-IP rate limit 30/min + 25 MB cap (`shortcut:` in-memory), saved solution rubrics in IndexedDB
  (`StoredExam.rubrics`), references by word overlap (`shortcut:` → Phase 4), ink exams, overtime versions,
  skip reasons, request caps (≤ 20 PNGs, ≤ 4 MB each, text ≤ 20k, ≤ 3 references), LLM grade never overwrites
  the self-grade, eval cases gitignored.
- Prompt caching only on Anthropic (the `CacheBreak` item); other adapters ignore it.

## Frontend layout of the LLM output

Per subtask row in the grading view, under each answer version, an **LLM card** (existing tokens in
`styles/tokens.css`, quiet like the rest of the page):

```
┌ a) Explain the handshake ─────────────────────────── 6 P ┐
│ [question crop] [your answer]                             │
│ Points  [ 4 ▾ ]   automatic                               │
│ ┌ LLM ──────────────────────────────────────────────────┐ │
│ │ 4 / 6 P                         from the solution     │ │
│ │ (or: 3–5 / 6 P · unsure)        Gemini Flash          │ │
│ │ ✓ names SYN, SYN-ACK, ACK      2 / 2   guide          │ │
│ │ ✓ explains sequence numbers    2 / 2   guide          │ │
│ │ ✗ mentions timeout handling    0 / 2   guide          │ │
│ │   "No word on retransmission."                         │ │
│ │ Feedback: Solid on the steps, missing what happens    │ │
│ │ when a segment is lost.                    Re-grade   │ │
│ └───────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

- Rubric as a small table: hit marker (✓ full, ◐ partial, ✗ none), item, `hit / max`, source tag
  ("guide" = from the solution, "inferred"); the note under the item in muted text.
- While grading: the card shows "grading…" and the live reasoning (muted, scrolls, max ~6 lines); errors show the
  message + Retry; skipped rows show the reason.
- **Summary per task** at the top of the grading view and on the results page once LLM grades exist: one line per
  task with subtask chips `a) 4/6 · b) 2/3 …`, the task total, and "you: X P / LLM: Y P" so the two can be compared
  at a glance; clicking a chip scrolls to that row.
- Mobile: the table collapses to item + points on one line, note below.

## Backend files

`uv add anthropic google-genai openai`.
- `app/grading/models.py` — `Part`, `RubricLine`, `Solution`, `Reference`, `GradeIn` (+ `provider`, `model`,
  allow-list validator), `LlmLine`, `LlmOut`, `GradeOut`.
- `app/grading/prompt.py` — `PROMPT_VERSION`, `SYSTEM_SOLUTION`, `SYSTEM_OWN`, `system_for`, `build_content` → items.
- `app/grading/providers/anthropic.py`, `google.py`, `openrouter.py` — adapters as above.
- `app/grading/grader.py` — `finalize`, `grade_stream`, `grade`, `GradingError`.
- `app/grading/limits.py` — `RateLimiter`, `grade_limiter`.
- `app/api/routes.py` — `POST /grade` (reads body itself: size check → key → limiter → validate → stream).
- Tests: `tests/test_grading.py` (finalize, prompt items, grader with a fake adapter, key never logged),
  `tests/test_providers.py` (each adapter with its SDK faked: request shape, thinking mapping, every error code,
  close mid-stream closes upstream), `tests/test_grading_api.py` (route), `tests/test_eval.py` (metrics).

## Frontend files

- `stores/settings.ts` — `provider` (default `anthropic`), `keys: {anthropic, google, openrouter}`,
  `models: {anthropic, google, openrouter}` (defaults per table); unknown stored values fall back to defaults.
  `SettingsPanel.vue` — provider radio, key field for that provider, model select (text field for OpenRouter), hints.
- `types/attempt.ts` — `RubricLine`, `LlmGrade` (+ `provider`, `model`), `Grade.llm`, `StoredExam.rubrics`.
- `lib/strokes.ts` (`paintStroke` moved from `DrawCanvas.vue`), `lib/grading.ts` (`skipReason`, `similarSubtasks`,
  `planGrading`, `streamGrade(body, key, …)` sending `X-LLM-Key`, `sseEvents`, `GradeError`, `gradeErrorMessage` incl.
  `no_credits` "Your OpenRouter account has no credits left.", `evalCasesJsonl`).
- `stores/attempt.ts` — `llm` state, `gradeWithLlm`, `regrade`, `stopLlm`, rubric saving, attempt-switch guard.
- `components/results/LlmCard.vue` (new, the card above), `LlmSummary.vue` (new, per-task summary),
  `GradingRow.vue`, `GradingList.vue`, `views/GradingView.vue` (progress, Stop, summary, dev export),
  `views/ResultsView.vue` (button enabled when the chosen provider has a key; label names provider; summary).
- UI work uses `frontend-design:frontend-design` guidance within the existing look.

## Eval

`backend/evals/grading/run_eval.py --provider google --model <id> cases.jsonl`, key from `ANTHROPIC_API_KEY` /
`GOOGLE_API_KEY` / `OPENROUTER_API_KEY`. Same metrics per basis; the report names provider + model, so runs on
different providers can be compared side by side. Cases export unchanged (dev-only link).

## Verification

- `uv run pytest` and `npx vitest run` green; all provider calls faked in tests, no key needed.
- Manual, free: a Google AI Studio key, grade one attempt with and one without a solution; Stop mid-pass; a wrong
  key shows "rejected" per row. Optional: OpenRouter free model, Anthropic Haiku.
- `GOOGLE_API_KEY=... uv run python -m evals.grading.run_eval --provider google evals/grading/cases.jsonl` writes the report.

Not included: applying the LLM grade to the self-grade in one click, Markdown/LaTeX rendering of feedback (plain
text by prompt), OpenRouter live reasoning, per-course "lecturer style" summaries (Phase 4).
