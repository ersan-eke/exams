# Phase 5b-1 handoff: Anki export

## Done
- `GET /api/subjects/{id}/anki?below=0..1` returns an `.apkg` of the Subject's weak subtasks (latest share strictly below `below`, default 0.6, at most 200). `409 nothing_weak` when none; foreign Subject is `404`. Setup and import: `docs/anki.md`.
- `tools.latest_shares` / `tools.weak_refs` (shared with `find_tasks`), `app/anki.py` (`build_deck`, genanki), button on `/statistics/<Subject>`.
- Manual check in real Anki done (images, back side, re-import updates without duplicates).
- Tests: backend 536 passed, frontend 385 passed. Unfixed review findings are in `docs/findings.md` ("Anki export").

## Not done
- Notion (5b-2): own brainstorm and plan next.

## Decisions already made
- Weak = latest graded share strictly below `below`; unattempted subtasks are never exported.
- Deck id from the Subject id; note guid = `guid_for(exam id, subtask key)`, so re-imports update instead of duplicating.
- A card shows the crop only; the extracted text and MC letters are the fallback when a subtask has no crop (the text is PDF noise and its letters need not match the layout).
- Crops come only from `tools.get_task` paths; no LLM, no key.
- The branch `phase-5b-anki` was cut from the 5a branch, not main (main lacks 5a); merge 5a first.
