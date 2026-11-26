# Phase 5b-2 handoff: Notion export

## Done
- Settings has a Notion card (public OAuth, `provider = "notion"` in `integrations`, refresh token stored encrypted). Setup: `docs/notion.md`.
- `POST /api/subjects/{id}/notion` queues a `notion` job (one active per Subject, partial unique index `uq_jobs_active_notion`). The worker runs
  `notion/export.py` `export_subject`: it creates the "Flashcards: exam-sim" database once (Table, Board by Status, Gallery), then one page per weak
  subtask that is not in `notion_cards` yet (question crops, solution crops in an `Answer` toggle, text only where crops are missing).
- `app/notion/`: `client.py` (pacing 0.34 s, retries on 429/5xx, file upload, refresh), `cards.py` (pure card builder), `export.py`.
- Job heartbeat: the exporter bumps `locked_at` per card, and the SSE stream gives up only when neither the job nor `locked_at` has changed for 15 minutes.
- Tests: backend 591 passed (one failure, `test_enrich::test_numprog_integration`, needs `samples/`), frontend 392 passed, vue-tsc clean.
  Unfixed review findings are in `docs/findings.md` ("Notion export").

## Not done
- The manual check with a real Notion integration (`docs/notion.md` "Manual check"). Connect, export, check the six properties and the three views
  (crops as gallery covers), open a card's `Answer` toggle, export again without duplicates, trash the database and export again, disconnect.
- Three facts come from the docs only. The manual check should record them here:
  - ~~Database create with no `parent`~~ answered live: rejected (400 `body.parent should be defined`); `parent: {type: workspace, workspace: true}` works.
  - Which error does Notion give for a trashed database or parent? The code treats 404 `object_not_found` and 400 `validation_error` mentioning archived/trash as gone.
  - Does `expires_in` come back for public integrations, and does a refresh response carry `workspace_id`/`owner`? The code tolerates both being missing.

## Decisions already made
- One-way export. Existing cards are never updated, and nothing is read back from Notion.
- One Notion workspace per user. Reconnecting the same workspace keeps the database and its cards; connecting another workspace deletes the old row (cascade).
- A `Task` select and the views By subject, By exam (tables) and Exam × Task (compact board, sub-grouped) were added after the
  first live run (2026-11-26); a database made before that lacks them, since views are only created with the database.
- The Board view groups by the `Status` select using the docs' select shape `{type: "select", property_id, sort: {type: "manual"}}`.
- Views are best effort. A failed view is logged, and the database still counts as created, so a retry never makes a second database.
- A failed refresh (any 400/401) and a second 401 end the job as `notion_auth`, with no retry. The rotated refresh token is stored before the retried call.
- A second "gone" after recreating the database ends the job as `server`, with no worker retry.
- Select names are cut to 100 characters.
- Exports of one connection are serialized by `pg_advisory_lock` on a dedicated connection (the Session releases its connection on commit).
- Disconnecting deletes the row only. Revoking at Notion is a `shortcut:`.
