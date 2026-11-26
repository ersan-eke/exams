# Phase 3a, auth + two-way sync: status and what's left

Written 2026-11-03, after Phase 3a. Spec: `docs/superpowers/specs/2026-11-02-sync-design.md`; plan: `docs/superpowers/plans/2026-11-02-sync.md`.
Earlier context: `docs/2026-11-01-text-first-handoff.md`, `docs/2026-10-29-llm-grading-handoff.md`.
Tests at the end: backend 277 passed, frontend 305 passed (38 files), `npm run type-check` clean.
Reviews: per-task reviews, `/code-review high` (10 findings, all fixed), `/security-review` (no findings).

## Done

- **Migration** `2c1ca18c29ed_sync`: `exams` + `point_overrides`, `rubrics` (JSONB), `solution_for` (UUID, no FK),
  `fingerprint`, `edited_at` (default epoch 0); `attempts` + `overtime`, `edited_at`; `grades.llm` (JSONB).
  Courses: case-duplicates per user are merged (oldest row kept), then a unique index on `(user_id, lower(name))`.
- **`course_id()`** finds courses case-insensitively (`func.lower` on both sides, Unicode-safe).
- **Routes** (`backend/app/api/sync.py`, all behind `current_user` → 401):
  - `PUT /api/exams/{id}`: create with structure + base64 PNG crops, metadata update, claim an anonymous row, other user → 404,
    `409 need_content`, stale `editedAt` → 204 no-op, crop name + PNG signature checks, 50 MB cap (413).
  - `PUT /api/attempts/{id}`: full replace of a handed-in attempt (answers, times, grades incl. `llm`); running → 422,
    `409 need_exam`, unknown subtask key → 422, stale → 204.
  - `GET /api/sync?since=`: own exams (metadata) + full attempts changed since `since - 10 s`, plus the DB-time cursor.
- **Wire format** (`backend/app/db/sync.py`, `app/db/attempts.py`): camelCase, times as epoch ms, per-subtask maps keyed by subtask key.
- **Client**: `lib/db.ts` stamps `editedAt` and marks the localStorage outbox only on real changes (view-only saves and running
  attempts don't); `lib/sync.ts` single-flight push exams → push attempts → pull, with `need_content` / `need_exam` retries;
  triggers on sign-in, tab visible and 2 s after an edit; first sign-in on a device pushes everything local.
  Uploads are stored under the server's `examId`. Views reload after a pull that changed something; the open attempt reloads
  unless a save is pending.

## Not done

- **Manual two-browser check (for the user):** sign in in a normal window and a private window, upload + hand in + grade in one,
  see it in the other within a few seconds (crops, answers, grades, LLM cards, pen marks), edit a grade there and see it come back.
  Needs a real GitHub/Google sign-in, so it was not run.
- **Migration:** the dev DB is still at `e7a1c2d3b4f5`; run `uv run alembic upgrade head` from `backend/`.
- Known gaps, deferred:
  - `flush()` clears the save timer before `putAttempt` resolves; a pull landing during that write can show the remote version.
  - A reload can drop an unsaved in-memory edit within the 500 ms save delay; `account.load` can trigger a sync before
    first-sign-in marking finishes.
  - Concurrent first PUTs of the same exam/attempt id → IntegrityError 500 (the retry next sync succeeds).
  - Grades are `Numeric(6,2)`: 0.333 → 0.33, ≥ 10000 → 500.
  - A permanently broken server exam keeps the cursor from advancing (refetch + warn every pull).
  - A pulled known exam that turns `hasInk` true doesn't fetch ink crops.
  - A localStorage failure drops an edit from the outbox (`shortcut:` comment); `putStamped` get+put isn't one IDB transaction.
  - `since` near `datetime.min` → 500; missing `createdAt` stored as 1970; empty `rubrics {}` stored as null.
  - Same PDF uploaded on two devices before syncing → two exams (`shortcut:` in the PUT exam route).
  - A second account on the same browser gets the first one's local data pushed into it (`shortcut:` in `stores/account.ts`).
  - Claiming an anonymous exam needs only its UUID; if anonymous exam ids are ever shared as links, require proof (e.g. the job id).
- No "last synced" UI.

## Decisions already made (don't revisit)

- Decisions in the earlier handoff docs and the spec still stand.
- Latest *edit* wins per record, by the client's `editedAt` (device clock; a badly wrong clock can win or lose wrongly, accepted).
  `updated_at` is only the sync cursor. A stale push is a 204 no-op.
- Exams written by the worker have `edited_at` = epoch 0, so any client push beats them (else old local edits would lose to the worker row).
- View-only saves don't mark dirty; `view` is never synced and a pulled attempt keeps its local `view`.
- 413/422 on push drop the record from the outbox (stays local-only); 401/5xx/network end the run; other 4xx keep it dirty and the run continues.
  Attempts of an exam that can't be pushed are dropped from the outbox.
- Running attempts are not synced.
- `subject` null/absent on PUT keeps the course; `""` clears it. `'Other'` is display-only, never a course.
- Both PUT routes end the auth dependency's transaction after reading the body (`db.rollback()`), so `now()` is write time.
- Duplicate PDFs across devices stay two exams for now (user decision).

## Where things live

- `backend/app/api/sync.py` (routes), `app/db/sync.py` (wire models, `ms`/`dt`), `app/db/attempts.py` (rows ↔ client shape),
  `app/api/auth.py` (`current_user`), `app/api/routes.py` (`check_declared`, `read_capped`). Tests: `backend/tests/test_sync.py`.
- `frontend/src/lib/sync.ts` (`sync`, `startSync`, `pulled`), `lib/db.ts` (outbox, `putStamped`, `storeRemote*`),
  `stores/account.ts` (first sign-in), `stores/attempt.ts` (`reloadIfReplaced`). Tests: `lib/__tests__/sync.spec.ts`, `db.spec.ts`.
