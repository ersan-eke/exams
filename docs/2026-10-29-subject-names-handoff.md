# Phase 1, subject names: status and what's left

Written 2026-10-29, after the subject-name phase. Spec: `docs/superpowers/specs/2026-10-29-subject-names-design.md`.
Earlier context: `docs/2026-10-28-backend-foundation-handoff.md` (still the reference for run commands and the backend decisions).

## Done

- **Better guess:** `guessSubject` (`frontend/src/lib/stats.ts`) now ignores years, semesters, exam-kind words
  (EN/DE plus abbreviations like sol, lsg, wdh, quiz1, ET/MT/RT, TSK), handles NFD (macOS) umlauts, and a single digit right
  after a noise word. The rest, joined, is the subject; nothing left means `Other`.
- **Upload sends it:** every exam upload sends a non-`Other` guess as `subject`; the server keeps it only for signed-in `role=exam` uploads. It is stored on `jobs.subject` (migration
  `4b78faf1d92c`), and the worker finds or creates a `courses` row via `course_id()` in `app/db/exams.py`.
  Anonymous uploads and solution uploads get no course.

## Not done

- **Top open item: PDF first-page course-title fallback.** Measured over the 306 real filenames in
  `samples/`, 189 still guess `Other`. Nearly all carry no subject at all (e.g. `2024 Endterm`,
  `endterm_2011-solution`, `quiz3`): `samples/` keeps the subject in the folder name, which a browser upload
  never sees. Reading the title from the PDF's first page is the fix; it needs pipeline work.
  Since then the 251 sample files without their course in the name were renamed to `<folder>_<name>`
  (tests and `pipeline_smoke.json` follow), so every sample now guesses its course; leftovers like
  `ana Main`, `gbs IN0009`, `it sec` come from extra words in the filename. Real uploads still hit the gap.
- **Renames don't reach the server:** editing an exam's subject in the UI changes only IndexedDB. Phase 3 sync
  must carry exam subject → course.
- **Case folding:** `GRNVS` and `grnvs` are different subjects (and courses).

## Decisions already made (don't revisit)

- The decisions in `docs/2026-10-28-backend-foundation-handoff.md` still stand.
- The guess logic lives in TypeScript only; the server doesn't repeat it.
- The server trusts the client's guess (stripped, capped at 100 chars).
- The course name is used exactly as given.

## Where things live

- `frontend/src/lib/stats.ts`: `guessSubject`; `frontend/src/lib/__tests__/stats.spec.ts`: real filename patterns.
- `frontend/src/lib/api.ts`, `frontend/src/stores/library.ts`: send `subject` with the upload.
- `backend/app/api/routes.py`: reads the `subject` form field into the job.
- `backend/app/worker/main.py`, `backend/app/db/exams.py`: `course_id()` and saving the exam under it.
