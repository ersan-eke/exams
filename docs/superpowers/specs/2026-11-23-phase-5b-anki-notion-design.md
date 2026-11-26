# Phase 5b: flashcard export, Anki first, then Notion (design)

Status: written by the assistant after a conversation with the user on 2026-11-23. **Not yet approved.** Calls marked *(my call)* are proposals.
Roadmap: `docs/roadmap.md` Phase 5. Builds on 5a (`integrations` table, `core/crypto.py`, the OAuth flow in `api/integrations.py`).
Facts about Anki and Notion below come from their docs via Context7 (2026-11-23); the builder re-checks the exact API of `genanki` before using it.

The work is two parts with different size, built in this order:

- **5b-1 Anki export** (this design is complete for it): small change, one session. As built: `docs/anki.md`.
- **5b-2 Notion export**: decisions so far are recorded at the end; it gets its own brainstorm and plan after 5b-1 ships (token refresh, a worker job and a
  card table are enough new ground to settle properly then).

## Intent

A student who scored badly on subtasks wants to drill exactly those, away from the app, with real spaced repetition. They press one button per Subject and get
a deck file that opens in Anki. The same weak-subtask selection later feeds Notion.

## Goals (5b-1)

- `GET /api/subjects/{subject}/anki` returns an `.apkg` deck of the user's weak subtasks in that Subject, as a file download.
- Weak = the share in the user's latest graded attempt of that subtask is below a threshold. *(my call)* Default 0.6, query parameter `below` (0..1, validated
  the same way as `find_tasks`' `scored_below:`). Unattempted subtasks are not exported.
- One note per subtask. Front: task context text, question text, MC options (if any), and the question crops as images. Back: solution text, MC answer letters,
  and the solution crops as images. A source line: exam, task, label, last score share. *(my call)* Tags: Subject and exam title, spaces replaced by `_`.
- Crops are embedded as media (the server owns them on disk; this is the advantage over Slack and Notion, which cannot fetch them).
- Re-exporting and re-importing updates cards in place instead of duplicating: the note guid is derived from `(exam id, subtask key)`; the model id and deck
  id are fixed (deck id derived from the Subject id). The deck is named `exam-sim::<Subject>`.
- A button on the frontend for a Subject, disabled or hidden when nothing is weak.
- `docs/anki.md` (what you get, how to import, what updates on re-import).

## Non-goals

- Reading review progress back from Anki (no AnkiConnect: it needs Anki running on the student's machine, which the server cannot reach).
- A plain `.txt` import file (no images) and AnkiWeb sync.
- Exporting unattempted subtasks, or whole exams. *(my call)* Later, with a `filter` parameter, if wanted.
- Any LLM call. The export reads stored grades and solutions only.

## Anti-goals

- Another user's questions reachable by guessing a Subject or exam id (the lookup stays scoped to the signed-in user, like the MCP tools).
- Duplicate cards after a second export, or cards that lose their Anki review history on re-import (guid and model id must stay stable).
- A crop path that escapes the exam directory (reuse `tools._crops`, which already enforces this).

## Constraints

- Backend rules from `CLAUDE.md`: sync `Session`, a plain `def` endpoint, `shortcut:` comments, `uv add` for deps (`genanki`), `ruff` before commit.
- Reuse, do not copy: `mcp/tools.py` already has the selection (`_scored`, the "latest share" loop in `find_tasks`, which also caps at 20), the card content
  (`get_task(include_solution=True)` returns text, MC options, solution and crop paths) and the safe crop paths. Pull the "latest share per subtask" loop
  out of `find_tasks` into a helper both use (`find_tasks` keeps its 20 cap; the export has its own limit).
- The same-origin middleware only blocks writes with a foreign `Origin`; a GET download is fine.

## Approaches

1. **`.apkg` built on the server with `genanki`** *(chosen)*. One download, images included, stable guids. New dependency.
2. Tab-separated `.txt` with Anki's `#deck:`/`#guid column:` headers: no dependency, but no images, and most weak subtasks have figures in their crops.
3. AnkiConnect: out, see non-goals.

## Decisions left to the builder

Where the button sits (the Subject view in statistics or study is the natural place); file name; card CSS; the exact `genanki` calls; an export limit
*(my call: 200 cards, with a `shortcut:` comment, since `get_task` costs a few queries per subtask)*; how to write the file (`genanki` saves to a path, so a
temp file read back into the response is fine).

## Tests (5b-1)

Seeded exam + graded attempt (no PDFs, per the testing levels in `CLAUDE.md`): only subtasks below the threshold are in the deck; the deck contains the media
files; two exports give identical note guids; another user's Subject answers 404; an empty selection answers a clear error the button can use.

## 5b-2 Notion (brainstormed 2026-11-25)

Facts from Notion's docs via Context7 (2026-11-25, API version `2026-03-11`).

**Intent.** Anki is the drill; Notion is the overview. The student sees every weak question of a Subject as a card with its crop, can sort and group
them, write notes under a crop, link them into lecture notes or share the board with a study group. A plain second card flipper would not be worth it.

**Goals**
- Connect Notion from Settings (public OAuth integration, `provider = "notion"` in `integrations`), one button per Subject sends its weak subtasks
  (5b-1 rule: latest share below 0.6, at most 200) as rows of one "Flashcards: exam-sim" database at workspace level (no parent page).
- Crops only, as in Anki (5b-1 decision): question crops above, solution crops inside an `Answer` toggle, uploaded with Notion's File Upload API
  (single part, 5 MiB limit on free workspaces). Extracted text only when a subtask has no crop at all. Title is `<exam> · <task> <label>`, never PDF text.
- Properties: Question (title), Subject (select), Exam (select), Type (select: Multiple choice / Open), Score % (number, percent), Status (select:
  New / Learning / Known, new rows `New`).
- Views created through `POST /v1/views` with the database: the default Table, a Board grouped by Status, a Gallery with the page's first image as cover.
- Runs as a worker job (about 3 requests per second per connection); a re-export only adds cards that are not in Notion yet.

**Non-goals.** Reading Status or edits back (one-way; card page ids are stored so sync can come later). Updating existing cards (score, crops). A node
graph (Notion has none). Topics per subtask. A chart view *(my call: add later if wanted)*. Revoking at Notion on disconnect.

**Anti-goals.** Another user's questions reachable; tokens logged or returned; duplicate rows from a double click, a retry or two exports at once;
a second "Flashcards" database because of a race or a reconnect; a job that loops on a deleted database or a dead token.

**Approaches.** (1) Public OAuth plus a worker job *(chosen: students only click; reuses 5a)*. (2) The student pastes an internal-integration token:
less code, but a setup most students will not finish, and internal integrations cannot create workspace-level content. (3) A Notion template duplicated
at connect: layout outside the repo, not reproducible; the Views API removes the reason for it.

**Decided in the conversation:** one-way; crops only; Board/Gallery/Table views; approach 1.
**Left to the builder:** the plan `docs/superpowers/plans/2026-11-25-phase-5b2-notion.md` fixes names and tests; the exact JSON shapes are checked against
Context7 while building.

As built: `docs/notion.md`.
