# Phase 1 — Subject names

## Context

Grading (Phase 2), MCP (3) and RAG (4) all group by subject. Right now the subject comes from
`guessSubject` (`frontend/src/lib/stats.ts:8`), which takes the first word of the filename. So
`2024_Retake_GRNVS` becomes "2024" and `Endterm 2023 GBS` becomes "Endterm". The `courses` table
(`backend/app/db/models.py:74`, `UNIQUE(user_id, name)`) and `exams.course_id` exist, but nothing
writes to them.

Goal: a guess that is right for the real filename patterns, and signed-in uploads land in a
`courses` row.

## Gaps in the Phase 1 roadmap entry, and whether a later phase covers them

| Gap | Covered later? | Plan |
|---|---|---|
| The server never learns the subject. The client guesses it and the worker only has `job.filename`. | No | The client sends its guess with the upload (one form field, stored in a new `jobs.subject` column). The guess logic stays in TypeScript only, not copied into Python. |
| Renaming a subject in the browser (`ExamRow`, `ExamSettingsView`) never reaches the server, so `course_id` goes stale. | Partly. Phase 3 brings sync, but its list (`GET /api/exams`, `PUT /api/attempts`) doesn't cover exam edits. | Out of scope now. Add a line to the Phase 3 roadmap: the sync slice must carry the exam's subject and map it to a course. |
| Anonymous uploads have no user, and `courses.user_id` is NOT NULL. | Not needed: anonymous exams are deleted after 24h. | No course for anonymous uploads. |
| Solution uploads (`role=solution`) | Phase 2 gets the solution through `attempt.solution_exam_id` and doesn't need a course on the solution. | Only `role=exam` gets a course. |
| Course title from the PDF's first page ("skip unless cheap") | No | Skip. It needs pipeline work, and the filename guess covers the real samples. |
| `GRNVS` and `grnvs` become two separate courses | Phase 3 sync and renames | Leave it. Use the name exactly as given, the same as the client does. |

Nothing consumes `course_id` before Phase 3. The upload-time mapping is still worth doing now,
because Phase 4's slide upload needs the same find-or-create helper.

## Steps

**1. `guessSubject` rewrite** (`frontend/src/lib/stats.ts`, test first in `lib/__tests__/stats.spec.ts`)
- Split on `/[\s_\-.]+/` and drop:
  - Pure-digit tokens of 2 or more digits (years, dates like `15.07.2023`, `20230715`). Keep single digits, so `Analysis 1` stays.
  - Semester tokens: `/^(ws|ss|wise|sose)\d{0,4}(\/\d{2,4})?$/i` (`WS23`, `SS2024`, `WiSe23/24`).
  - Exam-kind words, compared case-insensitively against one `Set`: endterm, midterm, final, retake, repeat, exam, solution(s), sample, mock, klausur, wiederholungsklausur, wiederholung, nachholklausur, lösung(en), loesung(en), musterlösung, musterloesung, probeklausur, probe, hauptklausur, semestralklausur, mit, with.
- Join what's left with a space. Empty → `'Other'`.
- New cases: `2024_Retake_GRNVS`→GRNVS, `Endterm 2023 GBS`→GBS, `GRNVS_2019 retake`→GRNVS,
  `Wiederholungsklausur_2022_Analysis`→Analysis, `Klausur_WS23_Lösung`→Other, `Analysis 1 Endterm`→Analysis 1.
- The existing test name changes ("first word"). `bySubject` keeps working because `X 1` → `X`.

**2. The client sends the guess** (`frontend/src/lib/api.ts:87`, `stores/library.ts:37`)
- `uploadExam(file, role?, subject?)` appends `subject` when given.
- `importUpload` passes `guessSubject(file.name.replace(/\.pdf$/i, ''))`. `attachSolution` passes nothing.

**3. Store it on the job** (backend)
- Alembic migration: `jobs.subject` is a nullable String. Add `subject: Mapped[str | None]` to `Job`.
- `upload_exam` (`backend/app/api/routes.py:42`) gets `subject: str | None = Form(None)`: strip it, cap it
  at 100 chars, empty → None. Store it only when `user` is set and `role == "exam"`.

**4. Map it to a course in the worker**
- `course_id(db, user_id, name) -> UUID` in `backend/app/db/exams.py`: `INSERT … ON CONFLICT (user_id, name) DO NOTHING`,
  then select. Two workers inserting the same course at once can't collide.
- `process` (`backend/app/worker/main.py:79`) passes `course_id=…` into the existing `to_rows(..., **exam_cols)`
  when `job.user_id and job.subject`.
- Tests in `backend/tests/test_worker.py`, in the style of `_job(**cols)`: two signed-in jobs with the same subject share one course,
  and an anonymous or subject-less job gives `course_id=None`. In `test_api.py`: the posted subject is stored on the job
  (trimmed, capped), and it is dropped for anonymous users.

**5. Docs**
- `docs/roadmap.md`: mark Phase 1 done. In Phase 3's sync slice, add "exam subject edits → course".
- New handoff `docs/2026-10-29-subject-names-handoff.md` covering done, not done (rename sync, case folding, PDF title fallback) and decisions.
- Process: this phase is small, so this plan doubles as the spec. Save it as `docs/superpowers/specs/2026-10-29-subject-names-design.md`,
  and save the task list as `docs/superpowers/plans/2026-10-29-subject-names.md`. Then use subagent-driven-development with
  4 tasks (steps 1, 2, 3+4, 5) and a review after each. Finish with `/code-review high`. No `/security-review`, because no keys, auth or webhooks change.
- Work on branch `phase-1-subject-names`.

## Verification

- `npx vitest run` in `frontend/` and `uv run pytest` in `backend/` (DB up). Both green.
- `uv run alembic upgrade head`, then `downgrade -1`, then `upgrade head` again, to show the migration is clean.
- Manual check: run `guessSubject` over every filename in `samples/` (a short node or vitest one-off, not committed) and look over the list.
- The pipeline isn't touched, so no smoke run is needed.
