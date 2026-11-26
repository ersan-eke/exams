# Phase 3a — Auth + two-way sync across devices

Status: design, awaiting approval. Source: the Phase 3 brainstorm in `docs/roadmap.md` (2026-11-02).

## Intent

Today every exam, attempt and grade lives in one browser's IndexedDB. Sign-in exists (GitHub/Google,
server sessions) but does nothing for the user's data. 3a makes the account real: finish an attempt on
one browser, sign in on another, and see it there with its answers, grades and crops. It also puts the
user's data on the server, which 3b (MCP) and Phase 4 (RAG) read.

**Success:** hand in + grade an attempt in browser A, open browser B, sign in, and within a few seconds
the exam (with crops) and the attempt (answers, times, grades, LLM suggestions, pen marks) are there.
Edit a grade in B; A shows it after its next sync.

## Goals

- Two-way sync of exams (incl. solution exams) and handed-in attempts between all devices of one account.
- Works offline-first: the browser stays the working copy; sync is a background push + pull.
- Signed-out use keeps working exactly as today.

## Non-goals / out of scope

- Syncing running attempts (they stay on the device that runs them until handed in).
- Real-time push (WebSocket/SSE), field-level merge, conflict UI. The latest *edit* wins per record (user decision).
- Deletes / tombstones (the app has no delete for exams or attempts).
- Merging the same PDF uploaded on two devices before they sync: it becomes two exams (user decision;
  `shortcut:` comment in the PUT exam route — merge by `fingerprint` and remap attempts when it bites).
- Separate local data per account on a shared browser (`shortcut:` comment where the first-sign-in rule lives).
- `GET /api/exams` list endpoint (replaced by `/api/sync`).

## Anti-goals (failure even if it "works")

- Losing work: a pull must never replace a newer local edit, and a push must never replace a newer server edit.
- One user reading or overwriting another user's exam or attempt.
- Storing or logging the LLM key (unchanged rule).

## Constraints

- Settled decisions in earlier handoff docs stand (columns for joined/filtered/summed, JSONB for whole values,
  `exams.id` and `attempts.id` are client-made).
- New routes use a `current_user` dependency that raises 401 (add next to `optional_user` in `app/api/auth.py`).
- Writes stay covered by the existing same-origin check in `main.py`.

## Design

### Ids

- `importUpload`/`attachSolution` store a new upload under the server's `exam_id` (the job's result) instead of
  `crypto.randomUUID()`. `uploadExam` returns that id with its result.
- Older local exams keep their random ids; the first push creates them on the server under that id.

### Migration (one Alembic revision)

- `exams`: `point_overrides` JSONB null, `rubrics` JSONB null, `solution_for` UUID null (no FK: it names a
  client attempt that may not be on the server yet), `fingerprint` text null.
- `attempts`: `overtime` bool not null default false.
- `exams` and `attempts`: `edited_at` timestamptz not null default now() — the client's edit time, used for
  latest-edit-wins (`updated_at` stays the server's sync cursor).
- `grades`: `llm` JSONB null.
- `courses`: replace the `(user_id, name)` unique constraint with a unique index on `(user_id, lower(name))`.

### Subject → course

`course_id()` in `app/db/exams.py` matches case-insensitively (find by `lower(name)`, insert on conflict do
nothing). Remove its `shortcut:` comment. The first spelling wins as the course name. Empty subject → `course_id`
NULL (the client's `'Other'` stays a display bucket, never a course).

### Field mapping (client ↔ server)

Exam (`StoredExam`): `title`, `hasInk`→`has_ink`, `hidden`, `subject`→course name, `pointOverrides`,
`rubrics`, `solutionFor`, `fingerprint`, `createdAt`→`created_at` (epoch ms ↔ timestamptz). `structure` and
crops only on create. `editedAt` → `edited_at` (epoch ms).

Attempt: scalar fields map 1:1 (`attendanceAt`→`attendance_at_ms`, epoch ms ↔ timestamptz for `startedAt`,
`handedInAt`, `gradedAt`, `editedAt`→`edited_at`). Per-subtask maps are keyed by the subtask key (`"A2b"`) on the client and by
`subtasks.id` on the server; the server resolves keys within the attempt's exam.
- **Answers:** `overtime = snapshot !== null`. If overtime: `main` rows = `snapshot`, `over` rows = `answers`.
  Else `main` rows = `answers`, no `over` rows. Pull reverses it exactly, so answer versions round-trip.
- **Times:** `time[key] = {main, over}` ↔ `subtask_times`.
- **Grades:** `main`, `over`, `comment`, `marks` columns as today, `llm` → new JSONB column.
- **Not synced:** `view` (UI state). A pulled attempt gets the default view state; a pulled attempt that already
  exists locally keeps its local `view`.

### API

All three routes: `current_user` (401), JSON bodies.

**`PUT /api/exams/{id}`** — upsert one exam.
- **Stale edit:** if the stored `edited_at` is newer than the body's, change nothing and return 204 (the
  client's next pull brings the newer version). Same rule for attempts.
- Row exists, owner is the user → update metadata only (structure/crops in the body are ignored).
- Row exists, `user_id` NULL (an anonymous upload) → claim it (set `user_id`), then update metadata.
- Row exists, other owner → 404.
- Row missing → body must have `structure` (`ExamStructure`) and `images` (+ `solution_images` when
  `has_ink`), base64 PNGs; else `409 {code: "need_content"}`. Writes rows via `to_rows` and crops into
  `exam_dir(id)/blank|ink/crops/`.
- Crop names must match `^[A-Za-z0-9_.-]+\.png$` and not start with `.`; bytes must start with the PNG signature;
  else 422. Body capped at 50 MB, streamed like `/api/grade` (413).
- Returns 204.

**`PUT /api/attempts/{id}`** — full replace of one handed-in attempt.
- `status == "running"` → 422. Exam not on the server or not the user's → `409 {code: "need_exam"}`.
  `solution_exam_id` set but not the user's → `409 {code: "need_exam"}` too. Attempt id owned by another
  user → 404. Unknown subtask keys → 422.
- One transaction: upsert the attempt row, delete + re-insert its answers, subtask_times and grades rows.
  Bumps `updated_at` even if nothing changed. Returns 204.
- New module `app/db/attempts.py` (counterpart of `app/db/exams.py`): client shape ↔ rows.

**`GET /api/sync?since=<iso ts>`** — what changed.
- Returns `{cursor, exams: [metadata…], attempts: [full attempt…]}` for the user's records with
  `updated_at > since - 10 s` (overlap covers commits that land out of order). No `since` → everything.
- `cursor` = the DB's `now()` at query time. The client stores it and sends it next time.
- Exam metadata has no structure/crops; the client fetches unknown exams with the existing `GET /api/exams/{id}`.

### Client

- **Edit time + outbox:** `putExam`/`putAttempt` in `lib/db.ts` compare the new record with the stored one,
  ignoring `view` and `editedAt`. If anything synced changed, they set `editedAt = Date.now()` and add the id
  to a dirty set in localStorage (`sync-dirty-exams`, `sync-dirty-attempts`). View-only saves (folding,
  expanding, the attempt store's periodic flush) therefore neither mark dirty nor bump `editedAt`. Writes coming
  from a pull use a variant that does neither. Records from older versions without `editedAt` count as 0.
- **`lib/sync.ts`** — `sync()`:
  1. Push dirty exams (metadata; on `409 need_content`, retry once with structure + crops from IndexedDB).
  2. Push dirty attempts; running ones stay dirty and are skipped; `409 need_exam` → push that exam, retry once.
  3. Pull `/api/sync?since=cursor`; write each remote exam/attempt whose `editedAt` is newer than the local
     one (or that is missing locally), and drop it from the dirty set; keep the local one otherwise. Fetch
     structure + crops for exams not stored locally. Save the cursor.
  A record is removed from the dirty set after its 2xx (a stale-edit 204 included). A 413 or 422 also removes it
  (`console.warn`, the record stays local-only; retrying can't fix it) — e.g. an old exam whose structure no
  longer validates. Errors leave it dirty for next time; network
  failure ends the run quietly. Only one `sync()` runs at a time (a call during a run schedules one more).
- **Triggers** (only when signed in): after `account.load()` finds a user, on `visibilitychange` to visible, and
  2 s after the last `putExam`/`putAttempt` (debounced).
- **First sign-in on a device:** localStorage `sync-user` ≠ current user id → mark every local exam and attempt
  dirty, clear the cursor, set `sync-user`. (`shortcut:` a second account on the same browser gets the first
  one's local data pushed into it; keep local data per account when shared browsers matter.)
- Stores (`library`, `attempt`) refresh after a pull that changed something: lists reload, and if the attempt
  store holds an attempt the pull replaced, it reloads it from IndexedDB keeping its local `view`, so its next
  flush can't write the old version back.
- No UI beyond that in 3a; optional "last synced" text is the builder's call.

## Testing

- Backend (pytest, `examsim_test`, no PDFs — stored `ExamStructure` fixture): PUT exam create / metadata update /
  claim anonymous / other user 404 / `need_content` / bad crop name / non-PNG / 413; PUT attempt round-trip of
  answers (overtime and not), times, grades incl. `llm` and `marks`; stale `edited_at` is a no-op 204; running 422; `need_exam`; unknown key 422;
  other user 404; `/api/sync` since filter + overlap; course case-folding; 401 without session.
- Frontend (vitest, mocked fetch + fake IndexedDB as existing tests do): dirty marking + `editedAt` bump,
  view-only save marks nothing, pulled newer record replaces local and clears dirty, older one is kept, 422 drops dirty, pull doesn't mark dirty,
  push order + both 409 retries, running attempt stays dirty, first-sign-in marks all.
- Manual: the success scenario above with two browsers (or a normal + private window).

## Claude's calls (check these)

- View-only saves don't mark dirty; the open attempt reloads after a pull replaces it.
- 413/422 on push drop the record from the outbox instead of retrying forever.
- Edit times come from device clocks; a badly wrong clock can win or lose wrongly (accepted).

## Left to the builder

- Request/response Pydantic models and exact JSON field casing (camelCase in the client mapping layer is fine).
- How `sync.ts` hooks into stores/app (plugin, `App.vue`, or the account store).
- Whether `GET /api/exams/{id}` gets reused as-is for pulled exams' content (preferred) or a lighter variant.
