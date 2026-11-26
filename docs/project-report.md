# exam-sim: project report

*Written as if the project were complete. A note at the end lists which sections describe unbuilt work.*

## 1. Summary

exam-sim is a self-hosted exam simulator and study assistant. You upload old exam PDFs. A pipeline turns each PDF into a structured exam (tasks, subtasks, point values, multiple-choice options, page crops). You take the exam in a timed browser UI and grade it yourself or with an LLM. Everything then feeds a subject-level study loop:

- statistics and weak-spot tracking
- search and chat over your lecture material
- an MCP tutor
- Slack quizzes
- Anki and Notion flashcards
- a daily study coach

It runs in production at exams.ersaneke.com and has a demo mode for visitors.

The stack:

- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2, Alembic, Postgres 18 with pgvector.
- **Frontend:** Vue 3, Pinia and Vue Router, with IndexedDB as the local store.
- **Code size:** about 8,600 lines of backend Python and about 9,600 lines of frontend TypeScript and Vue, plus a large test suite (about 650 backend and about 400 frontend tests).

## 2. Architecture

```
Browser (Vue 3, IndexedDB working copy)
   │  /api  /mcp                         Slack / Notion / Claude clients
   ▼                                          │
nginx (web) ── FastAPI (api) ◄────────────────┘
                 │   │
                 │   └─ Postgres 18 + pgvector  (users, exams, chunks, jobs, ...)
                 │
              worker (same image)  ── job queue = Postgres (SKIP LOCKED)
              PDF pipeline · slide indexing · Notion export · repair agent · study coach
```

- **One backend image, several commands.** The API runs `uvicorn main:app`. The worker runs `python -m app.worker.main`.
- **Postgres is the job queue.** There is no Redis or Celery. Jobs are claimed with `SELECT … FOR UPDATE SKIP LOCKED`.
  - Stale running jobs are re-claimed after 15 minutes. A job gets 3 attempts.
  - Progress reaches the browser over SSE (`/api/jobs/{id}/events`).
- **Local-first frontend.** Exams, crops and attempts live in IndexedDB. A sync layer mirrors them to the server so the same account works on several devices.
- **Database.** There are 21 tables:
  - Accounts: `users`, `oauth_accounts`, `sessions`, `access_tokens`.
  - Study content: `courses`, `exams`, `tasks`, `subtasks`, `attempts`, `answers`, `subtask_times`, `grades`.
  - Material and chat: `documents`, `deck_pages`, `chunks`, `chats`.
  - Integrations: `jobs`, `integrations`, `notion_databases`, `notion_cards`, `webhook_events`.
  - Every migration only adds. Drops and renames wait a release, because rollback runs an older image on the newer schema.

## 3. The exam pipeline (`backend/app/pipeline`)

The pipeline is deterministic PDF analysis with no LLM, so uploads are free and reproducible.

| Module | Job |
|---|---|
| `extract.py` (535 lines) | pdfplumber extraction of words and lines. Detects checkbox glyphs and ink colours (handwritten answers). Folds sub/superscripts into `_{}`/`^{}` markup. Drops repeated page furniture and margin graphics. |
| `structure.py` (852 lines) | Finds task headers (Aufgabe/Problem/Exercise/Task/Question/Frage) and subtask labels (a, b, c or N.1, N.2). Confirms them by layout evidence: one dominant header style and a consistent indent. Parses point values from many notations (`(2 Punkte)`, `2P+2P=4P`, `je 1P`, `[ /3.5]`, `/21`). Cross-checks subtask sums, task headers and the cover-page total. |
| `mc.py`, `meta.py` | Multiple-choice option detection and answer-key detection from ticked boxes in solution PDFs. Parses the exam duration and per-tick scoring rules. |
| `enrich.py` | Optional docling pass that turns formulas into validated LaTeX (Apple Silicon). |
| `render.py` | Renders clean page crops. Produces a *blank* and an *ink* variant per region. |
| `models.py` | `ExamStructure` with `Task`, `Subtask`, `Region`, `McRule`, `Issue` and similar. |

- **Solutions.** A filename and content heuristic recognises solution sheets. They link to their exam, and a solution's MC key and text are matched to subtasks.
- **Text-first rule.** Regions are marked visual only when the text can't carry them. This cut the visual share of regions from 59.5 % to 37.2 % and the average grading request from 1,018 to 829 tokens.
- **Repair agent.** When the pipeline emits `Issue`s (points that don't add up, a missing label), the worker enqueues a repair job. Claude receives the page images and the structure and has four tools: `get_page_image`, `move_region`, `set_points` and `validate`. Its result replaces the original only if it passes `ExamStructure` validation and the points check.
- **Guards.** A 15-PDF smoke test (`pipeline.smoke`, about 13 s) compares output against `pipeline_smoke.json` and runs from a hook after every pipeline edit. The full corpus run (`pipeline.cli ../samples`) gates merges. PDFs and crops are never committed.

## 4. Backend services

**Upload and jobs (`api/routes.py`, `worker/main.py`).**
- `POST /api/exams` streams the file to disk with a 100 MB cap and a duplicate contract, then returns 202 with a job id.
- Anonymous uploads are kept for 24 hours. Signing in claims them.
- `GET /api/exams/{id}` returns the structure plus base64 crops.

**Authentication (`api/auth.py`).**
- GitHub and Google OAuth through Authlib, using PKCE and a short-lived signed state cookie.
- Server-side sessions with a hashed token in an HTTP-only cookie.
- Only the verified primary GitHub address is used, and Google requires `email_verified`.
- `ALLOWED_EMAILS` makes the instance invite-only. An unlisted identity is rejected before any user or session exists, and an allowlist that parses empty makes the app refuse to start.
- A same-origin middleware backs up SameSite=Lax by refusing cross-site writes.
- Another middleware refuses signed-out uploads before the multipart body is read.
- Personal access tokens (stored hashed, revocable) authenticate `/mcp`.

**Sync (`api/sync.py`, `db/sync.py`, `frontend/lib/sync.ts`).**
- `PUT /api/exams/{id}` and `PUT /api/attempts/{id}` are idempotent full replaces in one transaction, with last write wins.
- A content check rejects bad PNGs, unsafe filenames and oversized bodies.
- `GET /api/sync?since=` returns changes with a 10-second overlap window for out-of-order commits.
- The client keeps a localStorage outbox of dirty ids. It pushes exams before attempts, then pulls. It runs on sign-in, when the tab becomes visible and 2 s after the last edit.
- Subjects map to `courses` rows through a case-insensitive find-or-create.

**LLM grading (`grading/`).**
- `POST /api/grade` streams over SSE. It works with three providers: Anthropic, Google AI Studio and OpenRouter.
- The user's key arrives per request in `X-LLM-Key` and is never stored or logged.
- A versioned prompt (`PROMPT_VERSION`) has two modes:
  - **Solution present:** the solution sheet is the rubric.
  - **No solution:** the model solves the task itself, builds a rubric, and sees up to N same-subject reference tasks plus course-material excerpts. The result is marked `basis: "own_solution"`.
- The structured result has `points`, `points_min`, `points_max`, a certainty flag, rubric lines (`item`, `max`, `hit`, `note`, `source`) and feedback. The server clamps all three scores to `0..max` and enforces `min ≤ points ≤ max`.
- Requests are capped at 20 images and 20k characters of text, every image must be a PNG, and a rate limiter applies.
- The prompt has a cache break so repeated attempts reuse the cacheable prefix.
- `evals/grading/run_eval.py` reports agreement, how often your grade falls in the model's range, mean absolute error and calibration, split by basis.

**Material and Ask (`rag/`, `api/documents.py`, `api/chats.py`, `api/ask.py`).**
- Subjects hold *decks* (slides, scripts, exercises). Upload is deduplicated by SHA-256 per user.
- The worker reads each deck page by page (title, headings, footer section, body). It builds an automatic two-level *outline* from PDF bookmarks, repeated footer sections, title-size headings, or fixed blocks of pages as the last fallback. The user can replace it with an AI-built one and reset it.
- Pieces are embedded locally with fastembed (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensions, no API key). Each piece also gets a Postgres `tsvector`.
- **Search needs no LLM.**
  - Exam-subtask search is hybrid: pgvector cosine plus full-text, merged by Reciprocal Rank Fusion.
  - Slide search uses BM25-style weights with the subject's own IDF. Title terms count 4, headings 2.5, the footer section 1.5 and the body 1. Agenda pages are down-weighted and a local embedding blend breaks ties.
  - Every query is scoped to one user and one subject.
- **Chats** are saved per subject and hold search turns and AI turns. You pin pages (at most 20). The AI turn sends only the pinned pages plus the last 6 messages. Only cited ids that were actually pinned survive. A dev-only preview endpoint shows the exact request (`DEV=1`).
- "Similar tasks" for grading comes from the same vector search, so references never leave the subject.

**MCP server (`mcp/`).**
- Streamable HTTP at `/mcp`, with bearer tokens.
- Tools: `list_subjects`, `progress`, `find_tasks` (filters `unattempted`, `scored_below`, `has_solution`), `get_task` (text, crops as inline images, MC key or solution on request), `my_history`, `record_practice` and `set_points`.
- The host model (Claude Code or Desktop) does the tutoring and grading. Practice shows up in the web app on every device.

**Integrations.**
- **Slack:**
  - OAuth with Fernet-encrypted stored tokens, and key rotation through comma-separated keys.
  - HMAC-SHA256 signature check with a 5-minute replay window and `event_id` de-duplication.
  - `/quiz <subject>` picks randomly among the 10 weakest subtasks and shows page crops through signed, expiring crop URLs. Interaction buttons reveal the verdict and the solution. There is no LLM in Slack, and the 3-second ack is handled with `response_url` and background tasks.
- **Anki:** `GET /api/subjects/{id}/anki` builds an `.apkg` of up to 200 weak subtasks (below 60 %). Question and crops are on the front and the solution on the back. A fixed model id keeps re-imports stable.
- **Notion:** OAuth, then a worker job creates a database and writes crop cards, uploading images and refreshing tokens. A Postgres advisory lock prevents concurrent exports for one integration, and `notion_cards` makes re-export idempotent.
- **Study coach:**
  - Courses carry an exam date.
  - A scheduled worker job finds weak topics from grades (reusing the MCP scoring code).
  - It sends a Slack DM and creates a Notion practice set. It uses no LLM and no key.

## 5. Frontend

| View | Purpose |
|---|---|
| New exam | PDF drop zone, upload progress over SSE, subject guess |
| My exams | Subject groups, per-exam settings (point overrides, rubrics, hide, attach solution) |
| Exam | Timed attempt with side outline, per-subtask answer area (typed text or a pen canvas), MC overlay, overtime handling with answer snapshots |
| Results and grading | Self-grading and LLM grading, rubric display, request preview, time bars, overtime changes |
| Statistics | Per-subject trends, activity grid, weak topics |
| Ask, Material, Study | Subject chat, a PDF viewer with outline, and study pages with export buttons |
| Settings | Provider, key and model per provider (kept on the device), personal access tokens, Slack and Notion connections |

- **Subject names.** `guessSubject` strips years, semesters and exam-kind words in English and German. The user can override it.
- **Scoring, sheet and solution logic** (`lib/scoring.ts`, `sheet.ts`, `solution.ts`) is pure and unit-tested.
- **Content-security policy.** The built app ships with a strict CSP.
- **Demo mode** is described in section 6.

## 6. Deployment and security

- **Hosting.** A home VM runs `deploy/compose.prod.yaml` with six services: `db`, `migrate`, `api`, `worker`, `web` (nginx) and `cloudflared`.
  - No service publishes a port. Cloudflare Tunnel is the only way in.
  - Networks are split: `backend` is internal, `edge` gives internet access to api, worker and web, and `tunnel` connects only cloudflared and web.
  - Every container has `cap_drop: ALL` and `no-new-privileges`, and the backend runs as uid 10001.
  - nginx takes the client IP only from `CF-Connecting-IP`, sets security headers and keeps no access log. uvicorn runs with `--no-access-log` because query strings carry OAuth codes and crop tokens.
- **Live domain.** The app is served at exams.ersaneke.com with Google and GitHub login in production. The instance is invite-only.
- **Demo mode.** Visitors can try the app without being invited. A demo account is read-only for exams and uses a server-paid LLM key under a tight quota, so the "key per request, never stored" rule holds for real users.
- **Edge protection.** Cloudflare rate limits protect the API and login paths. A CSP is set.
- **Operations:**
  - Automatic security updates on the VM.
  - Nightly encrypted backups of the database and `/srv/exam-sim/storage`, with a tested restore.
  - Images are built in CI and published to GHCR, and the VM deploys them automatically (the checkout and deploy-key flow was retired).
  - A ZAP baseline attack scan runs against a staging instance.
  - The Proxmox firewall is applied to the VM's network segment.
- **CI and tests.** GitHub Actions run the frontend build and tests (and backend tests, lint and the pipeline smoke test). Backend lint is ruff, line length 150. Deliberate simplifications carry `shortcut:` comments that say when to upgrade, so they can be listed as a debt ledger.
- **Known limit that remains.** Cloudflare terminates TLS, so it sees plaintext traffic, including the `X-LLM-Key` header. This is documented in `docs/hosting.md`.

## 7. Engineering process

- **One phase per session**, in the order spec → plan → subagent implementation with a review after each task → `/code-review high` (plus `/security-review` for keys, auth and webhooks) → verify → commit. A handoff doc (done / not done / decisions) is written at the end of each phase. "Decisions already made" in those docs are settled.
- **Findings.** Review findings that were not fixed go to `docs/findings.md` and are deleted in the commit that fixes them.
- **Project docs.** `CLAUDE.md`, `GLOSSARY.md` (Subject, Material, Deck, Outline, Search, Chat, Pinned page, AI turn), per-feature docs (`mcp.md`, `slack.md`, `anki.md`, `notion.md`, `hosting.md`), specs and plans under `docs/superpowers/`, and the graphify knowledge graph.
- **Tests** are organised by level:
  - Features outside the pipeline use a stored `ExamStructure` plus mocked Claude and Slack, with no PDFs.
  - Pipeline changes use the smoke set.
  - Merges use the full corpus.

## 8. Result

A signed-in user can:

1. Upload an exam and get a faithfully cropped, point-annotated, timed exam.
2. Answer it on any device.
3. Get strict rubric-based grading from their own LLM key, with an honest uncertainty range.
4. Ask questions of their own slides with page-level citations.
5. Be quizzed by Claude over MCP, or in Slack.
6. Export weak spots to Anki or Notion.
7. Be nudged by a coach before the exam date.

All of it runs on a hardened, backed-up, continuously deployed home server. A recruiter can try it through demo mode.

---

**Note on what's real.** The source supports sections 3 (except the repair agent), 4, 5 and the hosting basics: compose hardening, the allowlist and the nginx config. The following are written as done, though the repo does not have them yet:

- the repair agent and study coach (5c and 5d)
- demo mode, the CSP and the Cloudflare rate limit
- automatic updates and nightly backups
- CI deploys, the ZAP scan and the Proxmox firewall

The Notion live check and the VM go-live check are also still open. Google login is already coded in `api/auth.py` and `deploy/compose.prod.yaml`, but only works once its credentials are set. The report is based on the docs, key modules and the test structure, not every file. No tests were run, so the test counts come from the last handoff.
