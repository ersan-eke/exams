# Phase 5b-1: Anki export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One button per Subject downloads an Anki `.apkg` deck of the student's weak subtasks (question + crops on the front, solution + crops on the back), re-importable without duplicates.

**Architecture:** The selection and the card content already exist in `app/mcp/tools.py` (`_scored`, the "latest share" loop inside `find_tasks`, `get_task(include_solution=True)`, the safe `_crops`). Task 1 lifts the selection into shared helpers, Task 2 builds the deck with `genanki` in a new `app/anki.py`, Task 3 exposes it on the subjects router, Task 4 adds the button and `docs/anki.md`. No LLM, no new table, no migration.

**Tech Stack:** FastAPI, SQLAlchemy 2, `genanki` (new, `uv add`), Vue 3 + vitest.

**Spec:** `docs/superpowers/specs/2026-11-23-phase-5b-anki-notion-design.md` (Part 5b-1; its *(my call)* items are proposals the user has not individually confirmed). Notion (5b-2) is out of scope here.

## Global Constraints

- Branch `phase-5b-anki` off `main` (5b-1 uses nothing from 5a); one commit per task; `ruff check . && ruff format .` in `backend/` before each backend commit.
- Sync `Session`; the endpoint is a plain `def`. `shortcut:` comments for simplifications. Deps via `uv add genanki` only.
- Weak = latest graded share of the subtask is **strictly below** `below`; default `0.6`; `below` is a query parameter in `0..1`. Unattempted subtasks (share `None`) are never exported.
- At most `200` notes per deck (constant `LIMIT`), in order exam title, task position, subtask position.
- Deck name `exam-sim::<Subject name>`. Model id is a fixed constant; deck id is derived from the Subject id (`zlib.crc32(str(course.id).encode())`); note guid = `genanki.guid_for(str(exam.id), subtask key)`. Tags: Subject name and exam title with whitespace replaced by `_`.
- Only the signed-in user's data: a foreign or unknown Subject id is `404` (like `rename_subject`); hidden exams and solution exams are excluded (reuse `tools._practice_exams`).
- Crops come only from `tools.get_task`'s paths (they already stay inside the exam directory). No LLM call, no key.
- Tests: `uv run pytest` in `backend/` (needs `docker compose up -d db`), `npx vitest run` in `frontend/`. No PDFs: reuse the `seed` fixture and `crop`/`attempt` helpers of `tests/test_mcp_tools.py`.

## Review Focus

- Question or solution text containing `<`, `&` or `<script>` (PDF text can) must be HTML-escaped in the note fields (Task 2 test).
- A weak subtask with no solution and no crops still yields a valid note whose back says there is no stored solution (Task 2 test).
- A share exactly equal to `below` is not weak (Task 1 test).
- The same crop used by two notes ends up once in the package's media (Task 2 test).
- Exporting twice, with the attempt re-graded in between, keeps the same note guids (Task 2 test).

---

### Task 1: Shared weak-subtask selection

**Files:**
- Modify: `backend/app/mcp/tools.py` (`find_tasks`, around lines 200-215)
- Test: `backend/tests/test_mcp_tools.py` (append)

**Interfaces:**
- Produces: `latest_shares(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> dict[tuple[uuid.UUID, str], float | None]`, key `(exam id, subtask key)` to the share in the newest graded attempt that had it (the loop now inline in `find_tasks`, moved unchanged).
- Produces: `weak_refs(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, below: float, limit: int) -> list[str]`, wire ids `"<exam uuid>/<subtask key>"` of subtasks whose share is `< below` (never `None`), ordered by exam title, exam id, task position, subtask position, at most `limit`. Only practice exams (`_practice_exams`).

- [ ] **Step 1: Write the failing tests** in `test_mcp_tools.py`, using `seed` (E1 shares: `A1a` 0, `A1b` 0.5, `A2a` 1, `A2b` 1):
  - `test_weak_refs_below_threshold`: `weak_refs(db, a, cid, 0.6, 10) == [f"{e1}/A1a", f"{e1}/A1b"]`.
  - `test_weak_refs_threshold_is_strict`: `weak_refs(db, a, cid, 0.5, 10) == [f"{e1}/A1a"]`.
  - `test_weak_refs_skip_unattempted_and_cap`: nothing from `e2` (never attempted) appears at `below=1.0`; `limit=1` gives one ref.
  - `cid` is `course_id(db, seed["a"], "GRNVS")`.
- [ ] **Step 2: Run** `uv run pytest tests/test_mcp_tools.py -k weak_refs -v`. Expected: FAIL (`weak_refs` not defined).
- [ ] **Step 3: Implement** both helpers in `tools.py`; make `find_tasks` call `latest_shares` instead of its inline loop (behavior unchanged, keep its 20 cap). `weak_refs` should reuse the same ordered `Exam/Task/Subtask` query shape `find_tasks` uses rather than a second hand-written ordering; extract the shared query part if that is the clean way.
- [ ] **Step 4: Run** `uv run pytest tests/test_mcp_tools.py -v`. Expected: all PASS (existing `find_tasks` tests prove the refactor).
- [ ] **Step 5: Commit** `refactor: share the latest-score selection between find_tasks and weak_refs`.

### Task 2: The deck builder

**Files:**
- Create: `backend/app/anki.py`
- Modify: `backend/pyproject.toml`, `backend/uv.lock` (via `uv add genanki`)
- Test: `backend/tests/test_anki.py`

**Interfaces:**
- Consumes: `tools.weak_refs`, `tools.get_task(db, user_id, ref, include_solution: bool) -> (dict, list[Path])` (question crops first, then solution crops when `include_solution`), `tools.resolve`.
- Produces: `build_deck(db: Session, user_id: uuid.UUID, course: Course, below: float = 0.6, limit: int = 200) -> bytes | None` — the `.apkg` bytes, or `None` when nothing is weak. Constants `LIMIT = 200`, `BELOW = 0.6`, `MODEL_ID`.

- [ ] **Step 1: Run `uv add genanki`.** Then confirm the API against Context7 (`/kerrickstaley/genanki`): `Model`, `Deck`, `Package(deck).media_files = [paths]`, `write_to_file`, and the custom-guid pattern (`Note` subclass with a `guid` property, as in genanki's README).
- [ ] **Step 2: Write the failing tests** in `tests/test_anki.py` (`from test_mcp_tools import seed, crop, attempt`; read the package with `zipfile` + `sqlite3` on the extracted `collection.anki2`, table `notes`, columns `guid`, `flds`, `tags`):
  - `test_deck_has_one_note_per_weak_subtask`: for `seed`, two notes; `flds` of the first contains the subtask's question text and the source line with the exam title `Endterm 2024` and a score.
  - `test_nothing_weak_returns_none`: `build_deck(..., below=0.0)` is `None`.
  - `test_text_is_html_escaped`: set a weak subtask's `text` to `'a < b & <script>x</script>'` in the DB; the note field contains `a &lt; b &amp; &lt;script&gt;` and no raw `<script>`.
  - `test_subtask_without_solution_still_exports`: `flds` back part contains `No solution stored`.
  - `test_images_are_embedded_once`: the question crop appears as `<img src="…">` whose name is in the zip's `media` JSON; two notes that use the same crop file give one media entry.
  - `test_guids_stable_across_exports`: build twice with a re-graded attempt in between (`attempt(db, a, e1, {...})` newer, same weak subtasks); the sets of `guid` are equal, and equal to `genanki.guid_for(str(e1), "A1a")` for `A1a`.
  - `test_limit`: `limit=1` gives one note.
- [ ] **Step 3: Run** `uv run pytest tests/test_anki.py -v`. Expected: FAIL (module missing).
- [ ] **Step 4: Implement `build_deck`** in `app/anki.py`. Calls: `weak_refs` for refs; per ref `get_task(..., False)` for question text, MC options and question crops, and `get_task(..., True)` for the solution, whose crops are `paths[len(question_paths):]` (`shortcut:` two calls per card, fine for 200; fold into one call if it shows up in profiles). Model fields `Question`, `Answer`, `Source`; front template `{{Question}}`; back `{{FrontSide}}<hr id="answer">{{Answer}}<div class="source">{{Source}}</div>`; a short CSS block. Question field: task context text (if any), question text, MC options as a lettered list (`A.`, `B.`, …), then the crops as `<img>`. Answer field: solution text, MC key as letters (`mc_key` holds option indexes), then the solution crops; `No solution stored` when all are empty. Source: `<exam> · <task> · <label> · <share as percent>` (the share is `latest_shares` for that ref; call it once, or have `weak_refs` callers re-read it, whichever stays simplest). Escape every DB-sourced string with `html.escape` before it goes into a field. Media: copy each crop into a `tempfile.TemporaryDirectory` as `<sha1(content)[:16]>.png` and use that name in `<img src>`, so equal files are one media entry and names never collide across exams. Write with `Package.write_to_file` into the same temp dir and return the bytes.
- [ ] **Step 5: Run** `uv run pytest tests/test_anki.py -v`. Expected: PASS.
- [ ] **Step 6: Commit** `feat: build an Anki deck from the weak subtasks of a subject`.

### Task 3: The download endpoint

**Files:**
- Modify: `backend/app/api/subjects.py`
- Test: `backend/tests/test_anki.py` (append)

**Interfaces:**
- Consumes: `anki.build_deck`, `anki.BELOW`.
- Produces: `GET /api/subjects/{subject_id}/anki?below=<0..1>` → `200`, `application/octet-stream`, `Content-Disposition: attachment; filename="exam-sim.apkg"`, body the deck. `404` for an unknown or foreign Subject (no body detail), `409 {"detail": {"code": "nothing_weak"}}` when the selection is empty, `422` for `below` outside `0..1`.

- [ ] **Step 1: Write the failing tests** (HTTP, `signed_in(monkeypatch, sub)` from `test_auth`; the endpoint test must commit the seeded rows the way other HTTP tests in `test_mcp_tools.py`/`test_documents.py` do, e.g. the `committed` fixture there): `test_download_is_a_zip_with_the_deck` (200, body starts with `PK`, header present), `test_download_nothing_weak_is_409` (`below=0`, code `nothing_weak`), `test_foreign_subject_is_404` (user b asks for a's course id), `test_below_out_of_range_is_422` (`below=1.5`), `test_download_needs_login` (anonymous → 401, as the other routes answer).
- [ ] **Step 2: Run** `uv run pytest tests/test_anki.py -k download -v`. Expected: FAIL (404 route missing).
- [ ] **Step 3: Implement the route** on the existing router in `subjects.py`: load the `Course`, 404 unless `course.user_id == user.id`, `below: float = Query(BELOW, ge=0, le=1)`, call `build_deck`, `None` → `HTTPException(409, detail={"code": "nothing_weak"})`.
- [ ] **Step 4: Run** `uv run pytest -q` and `ruff check . && ruff format .`. Expected: all PASS, lint clean.
- [ ] **Step 5: Commit** `feat: GET /api/subjects/{id}/anki downloads the weak subtasks as an Anki deck`.

### Task 4: Button and docs

**Files:**
- Modify: `frontend/src/lib/subjects.ts`, `frontend/src/views/StatisticsView.vue` (subject layer, next to the exams section)
- Create: `docs/anki.md`
- Test: `frontend/src/views/__tests__/StatisticsView.spec.ts` (append), `frontend/src/lib/__tests__/subjects.spec.ts` if one exists, else cover `downloadAnki` there as a new file

**Interfaces:**
- Produces: `downloadAnki(id: string, name: string): Promise<void>` in `lib/subjects.ts`: `fetch('/api/subjects/<id>/anki')`; on non-OK rejects with the response's `detail.code` (like `ok()` there); on success saves the blob as `<name>.apkg` through a temporary `<a download>` and revokes the object URL.

- [ ] **Step 1: Write the failing tests.** `lib`: `downloadAnki` rejects with `nothing_weak` on a 409 body `{detail:{code:'nothing_weak'}}`; on 200 it clicks an anchor with `download === 'GRNVS.apkg'` (stub `URL.createObjectURL`/`revokeObjectURL`). View (mock `@/lib/subjects`): on `/statistics/GRNVS` there is a button "Export weak questions to Anki"; clicking looks the Subject up by name ignoring case via `listSubjects`, calls `downloadAnki(id, 'GRNVS')`; a rejection `nothing_weak` shows an `role="alert"` text "No questions scored below 60% in this subject yet."; the button is absent on the all-subjects layer `/statistics`.
- [ ] **Step 2: Run** `npx vitest run src/views/__tests__/StatisticsView.spec.ts`. Expected: FAIL.
- [ ] **Step 3: Implement** `downloadAnki` and the button (disabled while a request runs; other errors show the generic message the app uses elsewhere for failed requests).
- [ ] **Step 4: Write `docs/anki.md`**: what the deck contains, the 60% rule and 200-card cap, how to import (File > Import in Anki, same file again updates cards, review history is kept because guids are stable), what is not exported (unattempted subtasks, review progress back), no key needed. Link it from the spec and `docs/roadmap.md`.
- [ ] **Step 5: Run** `npx vitest run` and `npx vue-tsc --noEmit` (or the project's type-check script). Expected: PASS.
- [ ] **Step 6: Commit** `feat: Export weak questions to Anki from a subject's statistics`.

---

## After the tasks (project workflow, `CLAUDE.md`)

`/code-review high`; append every unfixed finding to `docs/findings.md` and say which in the final reply; run `graphify update .`; write `docs/2026-11-23-phase-5b1-handoff.md` (done / not done / decisions, including a manual check: import the downloaded deck in real Anki, see images and the back side, import it again and see no duplicates); update the "Where we are" pointer in `CLAUDE.md` and the Status line in `docs/roadmap.md`. Then brainstorm 5b-2 (Notion).
