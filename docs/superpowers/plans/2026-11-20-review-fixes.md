# Review fixes (14 findings) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 14 review findings (numbers `#1`–`#14` below are the review's numbers).

**Architecture:** Each fix goes in the layer that owns it. Backend tasks first (1–5), frontend after (6–9), then bookkeeping (10). The tasks are independent of each other; the sync paging server and client halves are both in Task 4.

**Tech Stack:** FastAPI + SQLAlchemy + pytest (`uv run pytest` in `backend/`), Vue 3 + Pinia + vitest (`npx vitest run` in `frontend/`).

**Spec:** `docs/superpowers/specs/2026-11-20-review-fixes-design.md`

## Global Constraints

- Backend: `uv` only; run `ruff check . && ruff format .` before each backend commit.
- Deliberate simplifications carry a `shortcut:` comment saying when to upgrade.
- Every commit message ends with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Delete a fixed entry from `docs/findings.md` in the commit that fixes it (none of these 14 are listed there today; check anyway).
- Don't change the `X-LLM-Key` handling, auth or the pipeline.

## Review Focus

- Upload exactly at the cap succeeds; one byte over gives 413 and leaves no file in `upload_path` and no `Job` row.
- A chunked upload without Content-Length is still capped (the helper reads in blocks, so it is).
- Sync paging with more rows than one page and **identical `updated_at`** on all of them: every row arrives exactly once.
- A first sync on an empty account still returns `more: false` and a cursor.
- A Deck whose job crashed three times keeps its row and its PDF.

---

### Task 1: Exam upload cap (#1) and Deck 413 test (#14)

**Files:**
- Modify: `backend/app/core/storage.py`, `backend/app/api/routes.py:47-75` (`upload_exam`), `backend/app/api/documents.py:~118-133` (`upload_document`)
- Test: `backend/tests/test_documents.py`, `backend/tests/test_api.py`

**Interfaces:**
- Produces: `save_capped(file: BinaryIO, path: Path, limit: int) -> str` in `core/storage.py`: copies `file` to `path` in 1 MiB blocks, returns the sha256 hexdigest; past `limit` bytes it closes and unlinks `path` and raises `HTTPException(413, detail={"code": "too_large"})`. `routes.MAX_EXAM_BYTES = 50 * 1024 * 1024`.

- [ ] **Step 1: Failing tests.** In `test_documents.py`: `test_deck_over_the_cap_is_413` — `monkeypatch.setattr("app.api.documents.MAX_BYTES", 1000)`, `upload(b, make_pdf([["x" * 5000]]))` (a PDF over 1000 bytes), assert `status_code == 413`, `json()["detail"] == {"code": "too_large"}`, no `Job` row and no file left under `upload_path`'s directory. In `test_api.py`: `test_exam_over_the_cap_is_413_and_leaves_nothing` — same with `monkeypatch.setattr("app.api.routes.MAX_EXAM_BYTES", 1000)` against `/api/exams`, anonymous; plus a case where the file is exactly the cap and is accepted (202).
- [ ] **Step 2:** `uv run pytest tests/test_documents.py tests/test_api.py -k cap -v` → exam test FAILS (202), Deck test passes already.
- [ ] **Step 3:** Move the copy loop out of `upload_document` into `save_capped`; call it from both routes (`upload_document` uses the returned digest; `upload_exam` replaces `shutil.copyfileobj`, passes `MAX_EXAM_BYTES`). Look the limit up at call time (pass the module constant as the argument) so the monkeypatch works.
- [ ] **Step 4:** `uv run pytest tests/test_documents.py tests/test_api.py -v` → PASS. `ruff check . && ruff format .`
- [ ] **Step 5:** Commit `Cap exam uploads at 50 MB and test the Deck 413 (#1, #14)`.

### Task 2: Worker survives a deleted Deck; no delete on server errors (#2, #3, #4)

**Files:**
- Modify: `backend/app/worker/main.py` (`run_once`, `main`)
- Test: `backend/tests/test_worker.py`

**Interfaces:**
- Produces: `step(db: Session) -> bool` in `worker/main.py` — the body of the `main()` loop (run_once, then index_pending/backfill_decks, then cleanup timing) returning True when `main` should loop again without sleeping. `main()` wraps `with SessionLocal() as db: step(db)` in `try/except Exception`: `log.exception`, rollback, then sleep and continue. Cleanup timestamp moves to a module-level variable or a small closure — implementer's choice, keep `cleanup` hourly.

- [ ] **Step 1: Failing tests** (add `process_document` coverage; `add_job(db, kind="document", document_id=...)` with a real `Document` row, see `tests/test_documents.py` for how one is made):
  - `test_deck_deleted_while_queued_finishes_the_job` — Document deleted before `run_once`; job ends `done`, no exception.
  - `test_deck_deleted_mid_job_does_not_kill_the_worker` — monkeypatch `app.worker.main.store_deck` to delete the Document through a second `SessionLocal()` and commit, then return. Call `step(db)` and assert it does not raise (or, if `run_once` handles it itself, that the job is not left `running`). Run it first against current code to see where it breaks, and put the guard where the error is raised.
  - `test_server_failure_keeps_the_deck_and_its_file` — job with `attempts = MAX_ATTEMPTS + 1` and a Document: after `run_once`, job `failed`/`server`, Document row and `doc_dir` file still there.
  - `test_unreadable_pdf_still_removes_the_deck` — monkeypatch `read_deck` to raise; Document gone, job `failed`/`unreadable`.
  - `test_step_error_is_survived_by_main_loop` — monkeypatch `run_once` to raise, call the wrapper used by `main` (extract a `guarded_step(db)` if needed) and assert it returns without raising.
- [ ] **Step 2:** `uv run pytest tests/test_worker.py -v` → new tests FAIL.
- [ ] **Step 3:** In `run_once` delete the Deck only when `job.error_code in ("unreadable", "scanned")`. Add `step` and the try/except in `main` as in Interfaces. Also make `index_pending`'s final commit safe the same way (covered by the try/except in `main`; no separate change).
- [ ] **Step 4:** `uv run pytest tests/test_worker.py tests/test_documents.py -v` → PASS; ruff.
- [ ] **Step 5:** Commit `Worker survives a deleted Deck and keeps Decks on server errors (#2, #3, #4)`.

### Task 3: Job stream deadline (#10), rate-limiter sweep (#12), MCP score history (#11)

**Files:**
- Modify: `backend/app/api/routes.py:103-114` (`job_events`), `backend/app/grading/limits.py`, `backend/app/mcp/tools.py:106-127` (`_scored`)
- Test: `backend/tests/test_api.py`, `backend/tests/test_grading.py` (or wherever `RateLimiter` is tested; grep), `backend/tests/test_mcp_tools.py`

**Interfaces:**
- Produces: `routes.JOB_EVENTS_DEADLINE = 15 * 60` (seconds). When it passes with the job still `queued`/`running`, `job_events` yields `job.model_copy(update={"status": "failed", "error_code": "server"})` and returns (a closed stream would make `EventSource` reconnect forever; the client stops on `failed`).
- `RateLimiter.allow` unchanged in signature; it drops every client whose newest hit is older than `window` at most once per `window` (track `self.swept`).

- [ ] **Step 1: Failing tests.** Stream: monkeypatch `JOB_EVENTS_DEADLINE` to 0.05 and `asyncio.sleep` interval as needed, leave a job `running`, read the SSE response, assert the last event has `status == "failed"` and `error_code == "server"` and the stream ends. Limiter: `allow("a", now=0)`, `allow("b", now=1000)` with `window=60` → `"a" not in limiter.hits`; and `allow` results unchanged for a normal burst. MCP: build one exam with a solution and 5 handed-in graded attempts (see existing `_scored` tests for the fixture), count SELECTs with `sqlalchemy.event.listen(engine, "before_cursor_execute", ...)` around `_scored`; assert the count is the same for 1 attempt and for 5.
- [ ] **Step 2:** run the three test files → FAIL.
- [ ] **Step 3:** Implement. In `_scored`: memoize the per-exam `fallback` and per-`solution_exam_id` `Exam` lookups in dicts local to the call, and load exams with `db.get(Exam, id, options=[selectinload(Exam.tasks).selectinload(Task.subtasks)])` (same pattern as `get_exam` in `routes.py`).
- [ ] **Step 4:** tests PASS; ruff.
- [ ] **Step 5:** Commit `Bound the job stream, sweep idle rate-limit clients, stop N+1 in MCP scores (#10, #11, #12)`.

### Task 4: Paged sync (#6)

**Files:**
- Modify: `backend/app/api/sync.py:157-181` (`get_sync`), `backend/app/db/sync.py` (`SyncOut`), `frontend/src/lib/sync.ts:159-200` (`pull`)
- Test: `backend/tests/test_sync.py`, `frontend/src/lib/__tests__/sync.spec.ts`

**Interfaces:**
- Produces: `sync.SYNC_PAGE = 50`. `GET /api/sync?since=<iso>&after=<uuid>`; `SyncOut` gains `more: bool`, `after: uuid.UUID | None` (id of the last attempt returned) and `page_since: str | None` (that attempt's `updated_at`, iso; wire name `pageSince`). Attempts are ordered by `(updated_at, id)`; with `after` present the filter is `(updated_at, id) > (since, after)` with **no** overlap subtraction and `exams` is `[]`; without `after` behaviour is as today (overlap, exams included). `cursor` is `now()` as today. `more` is true iff the page was full (`SYNC_PAGE` rows) — implementer fetches `SYNC_PAGE + 1` to know. A malformed `after` is 422 (type `uuid.UUID | None` does it). `after` without `since` is 422.
- Client: `pull()` loops: first request as today; while `body.more`, request `?since=<that page's updated_at>&after=<body.after>`. The next page's request sends `since=<pageSince>&after=<after>`. The persisted cursor is the **first** page's `cursor`, saved only when every page and exam fetch completed (existing `complete` rule).

- [ ] **Step 1: Failing tests.** Backend: `test_sync_pages_attempts_without_losing_or_repeating_any` — `monkeypatch.setattr("app.api.sync.SYNC_PAGE", 2)`, create 5 handed-in attempts, force identical `updated_at` on all with `age`/an UPDATE, follow `more` through `since=pageSince&after=after` and assert the union of ids equals the five, each exactly once, exams only on page 1, last page `more == false`. `test_sync_empty_account_is_one_final_page`. `test_sync_after_without_since_is_422`. Frontend (`sync.spec.ts`, mirror its existing fetch mocks): a mocked `/api/sync` returning two pages stores both pages' attempts and writes the first page's cursor once.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** Implement as in Interfaces; keep the existing `selectinload` options and the `keys` lookup (compute over the page's rows only). Add the new fields to the client's `body` type.
- [ ] **Step 4:** `uv run pytest tests/test_sync.py -v`; `npx vitest run src/lib/__tests__/sync.spec.ts` → PASS; ruff.
- [ ] **Step 5:** Commit `Page /api/sync by attempt so a new device doesn't pull the whole history at once (#6)`.

### Task 5: Sync input validation → 422 (#7)

**Files:**
- Modify: `backend/app/db/sync.py` (`ExamPut`, `AttemptWire`)
- Test: `backend/tests/test_sync.py`

**Interfaces:**
- Produces: `AttemptWire` int fields bounded `Field(ge=0, le=2**31 - 1)` where the column is a 32-bit `Integer` (`time_limit_ms`, `TimeWire.main/over`, `AnswerWire.ticks` items; check `db/models.py:273-310`; `started_at` etc. are BigInteger/timestamps — check each before bounding). `ExamPut` gets a `model_validator` rejecting duplicate task ids (and duplicate subtask keys inside a task) in `structure` with a `ValueError`, which FastAPI turns into 422.

- [ ] **Step 1: Failing tests** (parametrize, reuse `attempt_body`/`full` helpers): `time_limit_ms = 2**40` → 422; a duplicate task id in the structure → 422; both currently 500.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** Implement. Note `put_attempt` already turns `ValidationError` into 422 by hand (`sync.py:~150`), so the wire-model bounds are enough there; `put_exam` relies on FastAPI's own validation.
- [ ] **Step 4:** `uv run pytest tests/test_sync.py -v` → PASS (existing round-trip tests must still pass); ruff.
- [ ] **Step 5:** Commit `Reject bad exam and attempt data in sync with 422 (#7)`.

### Task 6: PdfViewer cancels the previous render (#5)

**Files:**
- Modify: `frontend/src/components/material/PdfViewer.vue` (`draw`)
- Test: `frontend/src/components/material/__tests__/PdfViewer.spec.ts` (create if absent; mock `pdfjs-dist` as other component specs mock their libraries)

**Interfaces:** module variable `let rendering: pdfjs.RenderTask | null = null`.

- [ ] **Step 1: Failing test:** with a mocked page whose `render()` returns a task whose `promise` stays pending and rejects with an error named `RenderingCancelledException` when `cancel()` is called, change `page` twice quickly; assert `cancel` was called on the first task and `error` was **not** emitted.
- [ ] **Step 2:** run `npx vitest run PdfViewer` → FAIL.
- [ ] **Step 3:** Before `p.render(...)`: `rendering?.cancel()` and await its settled promise (ignore the rejection); store the new task in `rendering`. In the `catch`, don't emit `error` when `e?.name === 'RenderingCancelledException'`. Cancel `rendering` in `onBeforeUnmount`.
- [ ] **Step 4:** `npx vitest run` → PASS.
- [ ] **Step 5:** Commit `PdfViewer: cancel the old render before drawing a new page (#5)`.

### Task 7: Ignore stale answers in ChatPane (#8) and attempt store (#9)

**Files:**
- Modify: `frontend/src/components/material/ChatPane.vue:~73-76` (`open`), `frontend/src/stores/attempt.ts:77-91` (`load`)
- Test: `frontend/src/components/material/__tests__/ChatPane.spec.ts`, `frontend/src/stores/__tests__/attempt.spec.ts` (existing specs; add cases)

- [ ] **Step 1: Failing tests.** ChatPane: `getChat` mocked with two deferred promises; open A then B, resolve B then A; assert the shown chat is B. attempt store: `getAttempt` mocked deferred; `load('a')` then `load('b')`, resolve b then a; assert `attempt.value.id === 'b'`, and that the stale `load('a')` neither throws nor changes `exam.value`.
- [ ] **Step 2:** run both → FAIL.
- [ ] **Step 3:** ChatPane: a module counter `let opening = 0`; `open` takes `const mine = ++opening`, returns without `reset` if `mine !== opening` after the await (same pattern as `latest` in the hints code above it). Also bump it in `reset()` callers that start a new chat (`fresh`, `remove`) so a late answer can't revive a closed chat. attempt store: `let loading = 0`; `load` takes a token at the start, and after each `await` that precedes writing state returns early when the token is stale (the writes at the end must not run; the `putAttempt` for an inherited solution may still run — it is that attempt's own data).
- [ ] **Step 4:** `npx vitest run` → PASS.
- [ ] **Step 5:** Commit `Drop out-of-order chat and attempt loads (#8, #9)`.

### Task 8: One `waitForJob` (#13)

**Files:**
- Modify: `frontend/src/lib/api.ts:62-78` (export `waitForJob`), `frontend/src/lib/documents.ts:93-110` (delete `waitForDocument`, import it)
- Test: existing `frontend/src/lib/__tests__/` specs for documents and api.

**Interfaces:** `export function waitForJob(jobId: string): Promise<string>` (unchanged body; `documents.ts` ignores the returned exam id). Rejection type becomes `UploadError` for Decks too; its `message` is the code, same as the `Error(code)` used before, and `serverCodes` already holds `scanned` and `unreadable`. Check that nothing in `documents.ts` callers or components compares to `instanceof Error` only or reads a code that `errorFor` would map to `'server'` (grep the Deck upload UI for `scanned`/`unreadable`/`server`).

- [ ] **Step 1:** Run `npx vitest run` first to see the baseline. Add a test in the documents spec: a failed job with `error_code: 'scanned'` rejects with `message === 'scanned'`.
- [ ] **Step 2:** Make the change; `npx vitest run` → PASS; `npx vue-tsc --noEmit` (or the project's type-check script) clean.
- [ ] **Step 3:** Commit `Share waitForJob between exam and Deck uploads (#13)`.

### Task 9: Close out

- [ ] Full runs: `uv run pytest` (backend), `npx vitest run` (frontend), `ruff check . && ruff format .`.
- [ ] `graphify update .`
- [ ] Per CLAUDE.md after the review (`/code-review high`): record any unfixed findings in `docs/findings.md`; say in the final reply which were recorded.
- [ ] Commit follow-ups if any.
