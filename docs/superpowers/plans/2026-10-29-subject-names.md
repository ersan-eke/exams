# Phase 1: Subject Names Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Guess the subject correctly from real exam filenames, and put signed-in exam uploads into a `courses` row.

**Spec:** `docs/superpowers/specs/2026-10-29-subject-names-design.md`

**Commands:** frontend `cd frontend && npx vitest run <path>`; backend `cd backend && uv run pytest <path> -q` (needs `docker compose up -d db`).

## Task 1: `guessSubject` rewrite (frontend)

Files: `frontend/src/lib/stats.ts`, `frontend/src/lib/__tests__/stats.spec.ts`

- [ ] Add failing cases to the existing guess test (rename it from "first word"):
  `2024_Retake_GRNVS`→`GRNVS`, `Endterm 2023 GBS`→`GBS`, `GRNVS_2019 retake`→`GRNVS`,
  `Wiederholungsklausur_2022_Analysis`→`Analysis`, `Klausur_WS23_Lösung`→`Other`,
  `Analysis 1 Endterm`→`Analysis 1`, `SS2024 Musterlösung GBS`→`GBS`, `GBS 15.07.2023`→`GBS`, `  `→`Other`.
- [ ] Implement: split on `/[\s_\-.]+/`, drop tokens that are 2+ digits (`/^\d{2,}$/`), semester tokens
  (`/^(ws|ss|wise|sose)\d{0,4}(\/\d{2,4})?$/i`), and exam-kind words (one lowercase `Set`: endterm, midterm,
  final, retake, repeat, exam, solution, solutions, sample, mock, klausur, wiederholungsklausur, wiederholung,
  nachholklausur, lösung, lösungen, loesung, loesungen, musterlösung, musterloesung, probeklausur, probe,
  hauptklausur, semestralklausur, mit, with). Join the rest with a space; empty → `'Other'`.
- [ ] `npx vitest run src/lib/__tests__/stats.spec.ts` green.

## Task 2: The client sends the guess with the upload

Files: `frontend/src/lib/api.ts`, `frontend/src/stores/library.ts` (+ their specs if they assert the form)

- [ ] `uploadExam(file, role?, subject?)` appends `subject` to the form when given.
- [ ] `importUpload` passes `guessSubject(file.name.replace(/\.pdf$/i, ''))`; `attachSolution` passes nothing.
- [ ] Test: the form posted by `importUpload` carries the guessed subject. `npx vitest run` green.

## Task 3: `jobs.subject` + course mapping in the worker (backend)

Files: new Alembic migration in `backend/alembic/versions/`, `backend/app/db/models.py`,
`backend/app/api/routes.py`, `backend/app/db/exams.py`, `backend/app/worker/main.py`,
`backend/tests/test_api.py`, `backend/tests/test_worker.py`

- [ ] Migration adds nullable `jobs.subject` (String); `Job.subject: Mapped[str | None]`.
- [ ] `upload_exam`: `subject: str | None = Form(None)`; strip, cap at 100 chars, empty → None; stored only
  when `user` is set and `role == "exam"`.
- [ ] `course_id(db, user_id, name) -> uuid.UUID` in `app/db/exams.py`: Postgres
  `insert(Course).on_conflict_do_nothing(index_elements=["user_id", "name"])`, then select the id.
- [ ] `process`: pass `course_id=course_id(db, job.user_id, job.subject)` into `to_rows` when both are set.
- [ ] Tests: two signed-in jobs with the same subject → one course, both exams point at it; anonymous or
  no subject → `course_id is None`; upload stores the trimmed/capped subject for a signed-in user and drops
  it for anonymous users.
- [ ] `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`; `uv run pytest` green.

## Task 4: Docs

- [ ] `docs/roadmap.md`: status line + Phase 1 marked done; Phase 3 sync slice gets "exam subject edits → course".
- [ ] `docs/2026-10-29-subject-names-handoff.md`: done / not done (rename sync, case folding, PDF title
  fallback) / decisions. Point `CLAUDE.md`'s "Latest handoff" at it.
