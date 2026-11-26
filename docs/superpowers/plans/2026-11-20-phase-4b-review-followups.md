# Phase 4b review follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the spec deviations, test gaps and tidy-ups left after the `phase-4-rag` review (#11 and its tickets), so the branch can merge.

**Architecture:** No new modules. Small edits in `rag/hints.py`, `worker/main.py`, `api/documents.py`, `api/sync.py`, `api/auth.py`, `db/session.py`-area docstring, plus tests and docs. Each task is independent and ends with a commit.

**Tech Stack:** FastAPI, SQLAlchemy sync `Session`, Postgres, pytest (`uv run pytest` in `backend/`), Vue 3 + vitest (comment-only change).

**Spec:** none written. Scope was agreed in conversation on 2026-11-20 from the review list below; the parent ticket is GitHub issue #11 (decisions there are settled, CLAUDE.md rule). Items marked "verified" were checked against the code while planning.

## Scope (from the review list)

| Review item | Task |
|---|---|
| A1 hints tie-break | 1 |
| A2 worker exam title, B4 weak NUL test | 2 |
| C subject matching (`_duplicate` vs `course_id`) | 3 |
| B6 race-path test for a Subject made by `course_id()` | 3 |
| B3 route-level grading test | 4 |
| E sync rollback duplication, D `start_session` shortcut comment, C detached-user docstring, E `ChatPane`/`hints.WORD` pointer | 5 |
| D findings format, stale issues #11/#13, handoff doc, unrecorded findings | 6 |
| B5 `auth.callback` | verified fine: `auth.py:136` calls `start_session` in `run_in_threadpool`. Only a handoff note (Task 6). |
| C hyphen indexing | verified fine: `tokens()` emits joined form plus parts, same as `_spellings`. No change. |
| E renames (`clean`, `*args`, `exclude_exams` type, `Vocab`), F | not done; recorded in `docs/findings.md` (Task 6) |

## Global Constraints

- Backend: `uv` only, run from `backend/`. Lint `ruff check . && ruff format .` before each backend commit.
- Deliberate simplifications carry a `shortcut:` comment saying when to upgrade.
- Delete a `docs/findings.md` entry in the same commit that fixes it.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Do not change behaviour beyond what a task names. No renames (E naming items are out of scope).
- `clean(name, length=100)` in `app/core/text.py` returns `None` when nothing is left.

## Review Focus

- Exam filename that cleans to nothing (`"\x00.pdf"` via worker): exam title falls back, no crash. (Task 2)
- Exam filename over 200 chars: title is capped at 200, not 255. (Task 2)
- Same PDF re-uploaded under a new Subject that loses the insert race: 409 naming the winner's Subject, no new Subject row, no stray upload file. (Task 3)
- `/api/grade` with `exclude_exams` containing a non-UUID or 11 entries: 422, grading never starts. (Task 4)
- Hint spelling tie ("TCP" and "tcp" once each): first seen wins, regardless of alphabet. (Task 1)

---

### Task 1: Hints tie-break is "first seen"

**Files:**
- Modify: `backend/app/rag/hints.py` (`Vocab.written`)
- Test: `backend/tests/test_rag_slides.py` (next to `test_hints_handle_umlauts_and_return_the_slide_spelling`, line ~195)

**Interfaces:**
- Consumes: `Vocab.spelling: dict[str, Counter]`, `hints(vocab, text) -> dict`.
- Produces: unchanged signatures.

- [ ] **Step 1: Write the failing test** `test_hint_spelling_tie_goes_to_the_first_seen`. Build a `Vocab` by hand (reuse the file's `_vocab` helper if it fits, else set `vocab[t]` and `vocab.spelling[t] = Counter(...)` directly) where the token `"tcp"` was seen as `"tcp"` first, then `"TCP"`, one time each. Assert `vocab.written("tcp") == "tcp"` and `hints(vocab, "tc")["completions"] == ["tcp"]`. Add a second case where `"TCP"` comes first and assert `"TCP"`. A third case: `"tcp"` seen twice, `"TCP"` once, first-seen `"TCP"` still loses (count wins, tie-break only on equal counts).
- [ ] **Step 2: Run** `uv run pytest tests/test_rag_slides.py -k tie -v`. Expected: FAIL (alphabetical picks `"TCP"`).
- [ ] **Step 3: Change `Vocab.written(self, token: str) -> str`** to return `max(seen, key=seen.__getitem__)`. `Counter` keeps insertion order and `max` returns the first maximum, so ties go to first seen. Update the docstring to say so.
- [ ] **Step 4: Run** `uv run pytest tests/test_rag_slides.py -v`. Expected: all PASS (the umlaut test must still pass).
- [ ] **Step 5: Commit** `fix: hint spelling ties go to the first seen, as #11 decided`.

---

### Task 2: Exam title from the worker is cleaned and capped; NUL test checks the title

**Files:**
- Modify: `backend/app/worker/main.py:94` (`title=Path(job.filename).stem`)
- Modify: `backend/app/api/documents.py:142` (suffix strip), `backend/app/api/sync.py:64` (inline NUL strip)
- Test: `backend/tests/test_worker.py` (uses `fake_pipeline`, `exam_of`, `add_job`; read them first), `backend/tests/test_documents.py` (`test_exam_upload_cleans_nul_from_filename`, line 144)
- Modify: `docs/findings.md` (delete fixed entries, see Step 6)

**Interfaces:**
- Consumes: `clean(name: str | None, length: int = 100) -> str | None`.
- Produces: exam `title` is `clean(Path(job.filename).stem, 200) or "upload"`, matching Deck titles (`documents.py:142` uses the same `or "upload"` fallback).

- [ ] **Step 1: Write failing tests** in `test_worker.py`, using `fake_pipeline(monkeypatch)` and `add_job` (add a `filename` argument only if it has none):
  - `test_exam_title_is_cleaned_and_capped`: job filename `"a" * 300 + ".pdf"` gives `exam_of(db, job_id).title == "a" * 200`.
  - `test_exam_title_falls_back_when_the_filename_cleans_to_nothing`: filename `"\x00 .pdf"` gives title `"upload"`. (Stem of `"\x00 .pdf"` is `"\x00 "`, which cleans to `None`.)
  - Leave `test_exam_upload_cleans_nul_from_filename` as is: the route only stores `Job.filename`; the exam title is built by the worker, so the two tests above are what pin it (this closes review item B4).
- [ ] **Step 2: Run** `uv run pytest tests/test_worker.py -k exam_title -v`. Expected: FAIL (title is 255 chars / NUL kept).
- [ ] **Step 3: In `worker/main.py`**, import `clean` from `..core.text` and set `title=clean(Path(job.filename).stem, 200) or "upload"`.
- [ ] **Step 4: Suffix strip in `documents.py:142`.** Replace `filename.removesuffix(".pdf").removesuffix(".PDF")` with `re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)` (add `import re`). Do not use `Path.stem`: `".pdf"` has stem `".pdf"` and the existing test `test_upload_title_falls_back_to_filename_then_upload` expects `"upload"`. Add a case to that test: filename `"Notes.Pdf"` gives title `"Notes"`.
- [ ] **Step 5: `sync.py:64`.** Replace `body.subject.replace("\x00", "")[:100].strip()` with `clean(body.subject)` (this is exactly what `clean` does for length 100; keep the `None` handling: `clean(None)` is `None`, so the `None if body.subject is None else` wrapper can go). Leave `subjects.py` and `chats.py` alone (different empty-string and length rules; stays in findings).
- [ ] **Step 6: Findings.** In `docs/findings.md` delete these entries: "Exam title from the upload filename is not capped…", "Exam-upload NUL test lives in `test_documents.py`" (the title is now asserted in the worker tests), "Title fallback strips only `.pdf` / `.PDF`". Edit "Inline NUL-strip copies remain" to list only `api/subjects.py` and `api/chats.py`, with *Left because:* different empty and length rules.
- [ ] **Step 7: Run** `uv run ruff check . && uv run ruff format . && uv run pytest tests/test_worker.py tests/test_documents.py tests/test_sync.py -v`. Expected: PASS.
- [ ] **Step 8: Commit** `fix: exam titles from the worker are cleaned and capped at 200`.

---

### Task 3: Duplicate check compares Subjects in SQL; race-path test

**Files:**
- Modify: `backend/app/api/documents.py` (`_duplicate`, line ~81)
- Test: `backend/tests/test_documents.py` (beside `test_same_file_in_another_subject_is_a_conflict_naming_that_subject`, line ~164; reuse `signed_in`, `upload`, `stored_uploads`, `CH1`)

**Interfaces:**
- Consumes: `_by_sha(db, user, sha) -> Document | None` (module-level in `documents.py`; used at the dedup check and in the `IntegrityError` handler), `course_id`.
- Produces: `_duplicate(db, existing, subject, response) -> dict`, unchanged signature and responses (200 `{job_id: None, document_id}` for the same Subject, 409 `{code: "already_uploaded", document_id, subject}` otherwise).

- [ ] **Step 1: Write the failing/pinning test** `test_losing_the_insert_race_leaves_no_new_subject_and_no_file`: user uploads `CH1` under `"Numerik"` (winner). Monkeypatch `app.api.documents._by_sha` with a wrapper that returns `None` on its first call and delegates afterwards, so the second upload passes the dedup check, creates Subject `"Algebra"` via `course_id`, and hits the unique constraint on commit. Upload `CH1` again under `"Algebra"`. Assert: status 409, `detail.subject == "Numerik"`, `detail.document_id` is the winner's, the user's Subject list has no `"Algebra"` (query `Course` for that user and name), and `stored_uploads()` is unchanged from before the second upload. If `"Algebra"` does persist, stop and report: that contradicts the "rolled back with the insert" assumption and is a real finding.
- [ ] **Step 2: Run** it. Expected: PASS already (it pins current behaviour). If it fails, fix the cause in `documents.py` before going on.
- [ ] **Step 3: Refactor `_duplicate`** so "same Subject" is decided by one SQL query using `func.lower` on both sides, the same normalisation as `course_id` (`db/exams.py:17-18`): select the name of `Course` where `Course.id == existing.course_id`, then compare with `select(...).where(func.lower(Course.name) == func.lower(subject))` instead of Python `.lower()`. Keep the unfiled case (`existing.course_id is None`) as a conflict with `subject: None`.
- [ ] **Step 4: Run** `uv run ruff check . && uv run ruff format . && uv run pytest tests/test_documents.py -v`. Expected: PASS (existing "same Subject, other spelling" test must still pass).
- [ ] **Step 5: Commit** `refactor: duplicate upload compares Subjects like course_id; pin the race path`.

---

### Task 4: Route-level `/api/grade` tests for `exclude_exams`

**Files:**
- Test: `backend/tests/test_grading_api.py` (module has `client`, `BODY`, `KEY`, `fake`, `events`)
- Read first: `backend/app/api/routes.py:165-180` (the `req.subject` branch that calls `material_for`), `backend/app/grading/models.py:83`.

**Interfaces:**
- Consumes: `material_for(session_cookie, subject, text, exclude_exams) -> str` as imported in `app.api.routes`.
- Produces: none.

- [ ] **Step 1: Write tests**:
  - `test_exclude_exams_must_be_uuids` (parametrized): `{"exclude_exams": ["not-a-uuid"]}` and a list of 11 valid UUIDs, each posted as `BODY | {"subject": "Numerik"} | extra` with `KEY` headers, assert status 422.
  - `test_exclude_exams_reach_the_material_lookup`: monkeypatch `app.api.routes.material_for` with a recorder returning `""`; post `BODY | {"subject": "Numerik", "exclude_exams": [a, b]}` (two `uuid.uuid4()` values, as strings); drain the stream via `events(r)`; assert the recorder got `subject == "Numerik"` and `exclude_exams == [uuid.UUID(a), uuid.UUID(b)]` (compare as lists of `UUID`).
  - `test_no_subject_means_no_material_lookup`: same recorder, no `subject`, assert it was not called.
- [ ] **Step 2: Run** `uv run pytest tests/test_grading_api.py -k "exclude or material" -v`. Expected: PASS (these pin existing behaviour). A failure is a real bug: fix it in `routes.py`/`models.py` and say so.
- [ ] **Step 3: Commit** `test: /api/grade validates exclude_exams and passes it to the material lookup`.

---

### Task 5: Comments and one small extraction

**Files:**
- Modify: `backend/app/api/sync.py` (lines ~106-108 and ~144-146), `backend/app/api/auth.py` (`start_session`, line ~98), `backend/app/db/` (find `read_then_release` with `grep -rn "def read_then_release" backend/app`), `frontend/src/components/material/ChatPane.vue:47-48`

**Interfaces:**
- Produces in `sync.py`: `async def _end_auth_transaction(db: Session) -> None`, which awaits `run_in_threadpool(db.rollback)` and carries the existing two-line comment once.

- [ ] **Step 1: `sync.py`.** Add `_end_auth_transaction` (place it next to `_once_more_on_conflict`), replace the duplicated `await run_in_threadpool(db.rollback)` plus comment in `put_exam` and `put_attempt` with `await _end_auth_transaction(db)`.
- [ ] **Step 2: `auth.py::start_session`.** Add to the `except IntegrityError` branch comment: `# shortcut: one retry like sync._once_more_on_conflict; a third simultaneous first login can still fail, loop if that is ever seen`. Check that the claim is true by reading the code (the handler re-reads once and raises if still empty). Reword to match what it really does.
- [ ] **Step 3: `read_then_release` docstring.** Add one line: it expunges everything, so the `User` it returns is detached on purpose: callers (`ask_turn`, `outline_ai`) read only plain columns (the id) from it afterwards and must not touch relationships or refresh it.
- [ ] **Step 4: `ChatPane.vue`.** Above `const W`, extend the comment with `mirrors hints.WORD in backend/app/rag/hints.py: change both together`. Add the opposite pointer above `WORD` in `hints.py`.
- [ ] **Step 5: Run** `uv run ruff check . && uv run ruff format . && uv run pytest tests/test_sync.py tests/test_auth.py tests/test_chats.py -v`, then in `frontend/`: `npx vitest run`. Expected: all PASS.
- [ ] **Step 6: Commit** `refactor: one place for the sync transaction release; document shortcuts and the detached user`.

---

### Task 6: Findings, issues, handoff

**Files:**
- Modify: `docs/findings.md`, `CLAUDE.md` ("Where we are" latest handoff line)
- Create: `docs/2026-11-20-phase-4b-review-handoff.md`
- GitHub: issues #11 and #13 (via `gh issue edit`)

- [ ] **Step 1: Findings format.** Add the missing *Left because:* to "Solution-exam test fixture is a copy of the question", "Test asserts fixture labels" and "Unexplained single failure in a full `npx vitest run`" (and a *Fix when:* wherever one is missing; check every entry under "Open" has both). Use the entry's existing wording to decide the reason; do not invent history.
- [ ] **Step 2: Record what stays unfixed.** Append under a new heading `### Phase 4b review follow-ups (#11)`, each in the entry format with *Left because:* and *Fix when:*:
  - `clean` in `core/text.py` is a generic name.
  - `_once_more_on_conflict(put, db, *args)` and `read_then_release(db, read, *args)` hide their purpose behind `*args`.
  - `exclude_exams` is always graded exam plus solution exam but is an open list capped at 10.
  - `Vocab(Counter)` carries spelling inside a Counter subclass and `hints()` reaches into it.
  - `subjects.py` and `chats.py` inline NUL strips (updated in Task 2, do not duplicate).
  - Accepted, no action (one line each, *Left because:* accepted in review): `_once_more_on_conflict` retries once; no test that new warnings from our own code still show past `filterwarnings`.
- [ ] **Step 3: Issue text.** `gh issue view 11 --json body` and `gh issue view 13 --json body`, replace the `exam_id` wording with `exclude_exams: list[UUID]` (max 10, graded exam plus its solution exam, from #20) and `exclude_exam` with `exclude_exams`. Apply with `gh issue edit <n> --body-file <file>`. These edit shared GitHub text: show the diff to the user and wait for their go-ahead before running `gh issue edit`.
- [ ] **Step 4: Handoff doc** `docs/2026-11-20-phase-4b-review-handoff.md`, same shape as `docs/2026-11-05-rag-handoff.md`: Done / Not done / **Decisions already made**. Decisions to record: (a) the async/session rule (sync `Session`; endpoint without `await` is plain `def`; `async def` touches the session only inside `run_in_threadpool`; no ORM attribute read after rollback/commit on the event loop), with the audit result: `auth.callback` follows it (`start_session` in `run_in_threadpool`), sync `put_exam`/`put_attempt` release the transaction first; (b) the upload duplicate contract: same user + sha256 + same Subject (case-insensitive, in SQL) gives 200 with the existing `document_id` and `job_id: null`, other Subject or unfiled gives 409 `already_uploaded` with `document_id` and `subject`, the DB `UNIQUE(user_id, sha256)` is the arbiter, every non-insert outcome removes the uploaded file; (c) hint spelling ties go to first seen; (d) `exclude_exams` replaced `exam_id`.
- [ ] **Step 5: `CLAUDE.md`** point "Latest handoff" at the new doc, keeping the Ask redesign decisions line.
- [ ] **Step 6: Commit** `docs: phase 4b review handoff, findings format, stale issue text`.

---

### Task 7: Verify

- [ ] **Step 1:** In `backend/`: `uv run ruff check . && uv run ruff format --check . && uv run pytest`. Expected: ruff clean, all pass (398 plus the new tests).
- [ ] **Step 2:** In `frontend/`: `npx vitest run`. Expected: 360 pass.
- [ ] **Step 3:** `graphify update .` from the repo root.
- [ ] **Step 4:** `/code-review high` on the branch diff for this plan's commits; fix real findings, record the rest in `docs/findings.md` per CLAUDE.md, and say in the final reply which findings were recorded.
