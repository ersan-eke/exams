# Phase 2, LLM grading: status and what's left

Written 2026-10-29, after the LLM grading phase. Spec: `docs/superpowers/specs/2026-10-29-llm-grading-design.md`; plan: `docs/superpowers/plans/2026-10-29-llm-grading.md`.
Earlier context: `docs/2026-10-28-backend-foundation-handoff.md` (run commands, backend decisions).
Tests at the end: backend 135 passed, frontend 254 passed (36 files), `npm run type-check` clean.

## Done

- **Grading core** (`backend/app/grading/`): models, one prompt file, and a grader that streams a result and clamps it.
  Grades solution-first, with a certainty/range; without a solution it falls back to references.
- **Three providers**, picked in settings: Anthropic, Google AI Studio, OpenRouter. Adapters live in `grading/providers/`.
- **`POST /api/grade`**: the key comes in `X-LLM-Key`, is never stored or logged. Body size cap and a per-IP rate limit.
  Answers as an SSE stream (reasoning, result, errors such as rejected key or no credits).
- **Client**: provider/key settings, SSE reader (`lib/grading.ts`), attempt-store actions to run, stop, re-grade and save.
  A regrade joins a pass that is already running.
- **Results UI**: LLM card per row, summary, progress, Stop, Retry/Re-grade, results button, eval case export.
- **Eval runner** (`backend/evals/grading/`): grades exported cases, with and without the solution.

## Not done

- **Manual checks with a real key: none done.** All tests mock the providers.
- **Visual check of the LLM card and summary** at desktop and 375px: not done (no browser). The header may overflow at 375px.
- **Eval not yet run on real cases.** Export cases, then run `run_eval`.
- **Gemini free-tier status unconfirmed.** `gemini-flash-latest` / `gemini-pro-latest` are the docs-confirmed aliases; needs a live key.
- **OpenRouter live reasoning is not streamed.**
- **Lecturer-style summaries and vector references** wait for Phase 4.
- Skip reasons are lost on reload (`prepareLlm` doesn't set `llm.skipped`).
- A 25 MB body (413) shows "too many images".
- Anthropic low credit may come back as a 400, so `no_credits` may never fire for Anthropic.
- Google non-SAFETY block reasons (PROHIBITED_CONTENT, BLOCKLIST, RECITATION) show as "couldn't grade", not refused.
- Smaller deferred items are in `.superpowers/sdd/2026-10-29-llm-grading/progress.md` ("minor (deferred)").
- **Step for the user (free with a Google AI Studio key):** set provider and key; grade one attempt with and one without a
  solution; Stop mid-pass; check that a wrong key shows "rejected" per row; export cases and run
  `GOOGLE_API_KEY=... uv run python -m evals.grading.run_eval --provider google evals/grading/cases.jsonl` (from `backend/`).

## Decisions already made (don't revisit)

- The decisions in `docs/2026-10-28-backend-foundation-handoff.md` and the spec still stand.
- The user's own key, sent per request in `X-LLM-Key`; never stored or logged.
- Three providers; the model ids are `gemini-flash-latest` / `gemini-pro-latest` for Google and `google/gemini-2.5-flash` as the OpenRouter default.
- The Google adapter passes the Pydantic class `LlmOut` as `response_schema` (the SDK converts it), not `llm_schema()`.
- The three adapters were built and reviewed as one batch.
- `planGrading`'s context field for multiple-choice answer keys is `mcKeys` (not `keys`, which is the settings API keys).
- A regrade joins a running pass (uses that pass's key). Retry/Re-grade is hidden while a row is pending, not guarded in the store.
- `GradingList` always plans on load and registers jobs with `store.prepareLlm(jobs)`, so Re-grade works after a reload.
- References are dropped when a solution exists.

## Where things live

- `backend/app/grading/`: `models.py`, `prompt.py`, `grader.py`, `limits.py`, `providers/{anthropic,google,openrouter}.py`.
- `backend/app/api/routes.py`: `/api/grade`.
- `backend/evals/grading/`: `run_eval.py`, `README.md`. Tests: `backend/tests/test_{grading,providers,grading_api,eval}.py`.
- `frontend/src/lib/grading.ts`: planning, SSE reader, requests. `frontend/src/stores/attempt.ts`: run/stop/regrade/save. `frontend/src/stores/settings.ts`: provider and key.
- `frontend/src/components/results/`: `LlmCard.vue`, `LlmSummary.vue`, `GradingList.vue`, `GradingRow.vue`. `frontend/src/components/frame/SettingsPanel.vue`: provider UI.
- `frontend/src/views/GradingView.vue`, `ResultsView.vue`: the pass and the results button.
