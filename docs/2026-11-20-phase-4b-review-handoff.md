# Phase 4b review follow-ups: status and what's left

Written 2026-11-20. Plan: `docs/superpowers/plans/2026-11-20-phase-4b-review-followups.md`. Parent ticket: #11. Earlier context:
`docs/2026-11-05-rag-handoff.md`, `docs/2026-11-13-ask-redesign-grill-handoff.md`.

## Done

- Hint spelling ties go to the first seen (`rag/hints.py` `Vocab.written`).
- Exam titles from the worker go through `clean(..., 200)` with an `"upload"` fallback; Deck title fallback strips `.pdf` case-insensitively.
- `_duplicate` decides "same Subject" in SQL with `lower()` on both sides, as `course_id` does. The lost-insert-race test also checks that no new Subject is left behind.
- `/api/grade` route tests: `exclude_exams` must be at most 10 UUIDs (422 otherwise) and reaches `material_for`; no `subject` means no lookup.
- `sync.py` releases the auth transaction in one helper; `start_session` carries its `shortcut:` comment; the word regexes in `ChatPane.vue` and `hints.py` point at each other.
- Checked and fine, no change: `auth.callback` runs `start_session` in `run_in_threadpool`; hyphen indexing in `hints._spellings` matches `tokens()`.

## Not done

- The `sync.py` subject strip stays inline: `""` clears a course and `None` keeps it, which `clean` cannot express. `subjects.py` and `chats.py` copies stay too.
- Renames and the `Vocab` shape are recorded in `docs/findings.md` ("Phase 4b review follow-ups").
- Manual checks from the RAG handoff are still open.

## Decisions already made (don't revisit)

- **Async/session rule:** the app uses a sync `Session`. An endpoint without `await` is a plain `def`. An `async def` endpoint touches the session and ORM objects only inside `run_in_threadpool`, and reads no ORM attribute after a rollback or commit on the event loop. Audit result: `auth.callback`, `put_exam`, `put_attempt`, the AI turn and the outline endpoint follow it.
- **Upload duplicate contract:** same user, same sha256, same Subject (case-insensitive, compared in SQL) gives 200 with the existing `document_id` and `job_id: null`. Another Subject or unfiled gives 409 `{code: "already_uploaded", document_id, subject}`; the Deck is not moved. `UNIQUE(user_id, sha256)` is the arbiter in a race, and every non-insert outcome removes the uploaded file.
- **Hint spelling:** most frequent spelling; a tie goes to the first seen.
- **Grading exclusion:** the request field is `exclude_exams: list[UUID]` (max 10, the graded exam plus its solution exam), not `exam_id`.
