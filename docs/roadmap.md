# Exam-sim upgrade plan

Status: Phases 0–2, 2b, 3a, 3b and 4 done (see `docs/2026-10-29-llm-grading-handoff.md`, `docs/2026-11-01-text-first-handoff.md`, `docs/2026-11-03-sync-handoff.md`, `docs/2026-11-04-mcp-handoff.md`, `docs/2026-11-05-rag-handoff.md`) and 5a (Slack, `docs/2026-11-20-phase-5a-handoff.md`, `docs/2026-11-24-slack-crops-handoff.md`) and 5b-1 (Anki, `docs/2026-11-23-phase-5b1-handoff.md`) and 5b-2 (Notion, `docs/2026-11-25-phase-5b2-handoff.md`; live Notion check open). Phase 6a stage 1 (live, invite-only at exams.ersaneke.com; runbook `docs/hosting.md`) is built; the live check is open. Agreed order (2026-11-26): (1) 6a stage 1; (2) 6b demo mode, together with the parts of 6a stage 2 that demo exposure needs (Cloudflare rate limit, content security policy, automatic security updates on the VM, nightly backups); (3) publish (the link goes on the CV); (4) later: 5c, 5d and the rest of 6a stage 2 (CI with automatic deploys, the ZAP attack scan, the Proxmox firewall once at home). Split from Phase 5 below:
5b flashcard export (5b-1 Anki `.apkg`, then 5b-2 Notion; design `docs/superpowers/specs/2026-11-23-phase-5b-anki-notion-design.md`), 5c pipeline repair agent, 5d study coach (scheduled job, Slack DM + Notion practice set).

## Context

The app today: a Vue 3 exam simulator (IndexedDB) on top of a FastAPI pipeline that turns exam PDFs
into `ExamStructure` (tasks → subtasks → regions + PNG crops). The goal is to add nine portfolio skills
(LLM grading, RAG, SQL, auth, webhooks, integrations, MCP, agents, Claude Code) as real features.

Step 1 (Postgres + auth + async jobs) is **built and committed** — see
`docs/2026-10-28-backend-foundation-handoff.md`. Done: 12 tables + 3 Alembic migrations, Postgres job
queue (`SKIP LOCKED`) + worker + SSE, GitHub/Google login with server sessions. Open: sync, `documents`/
`chunks`, Slack webhook, Notion/Slack OAuth.

Your decisions: switch pip → uv; commit first, then LLM grading; grading uses **your own API key**;
grading is solution-first with a certainty/range; slide upload per subject; better subject names;
"similar tasks" scoped to one subject.

## Phase 0 — uv, commit, CLAUDE.md (½–1 day)

**uv** (the venv is already uv-made, Python 3.13.5):
- `backend/pyproject.toml` with `[project] dependencies` = today's `requirements.txt` (keep the
  `pypdfium2==4.30.0` pin + its comment) and `[dependency-groups] dev = ["pytest", "httpx"]`;
  `requires-python = ">=3.13"`. Generate `uv.lock`, commit it.
- Delete `requirements.txt` / `requirements-dev.txt`.
- Commands become `uv run alembic upgrade head`, `uv run uvicorn main:app`,
  `uv run python -m app.worker.main`, `uv run pytest`. Update the handoff doc + CLAUDE.md.
- Real `backend/Dockerfile` (it's a placeholder): `ghcr.io/astral-sh/uv` base,
  `uv sync --frozen --no-dev`. Check current uv Docker docs via Context7.

**Commit**:
- Fix the odd staged renames first (`.env -> backend/app/api/routes.py`,
  `frontend/package.json -> layout_analyzer.py`): reset the index, re-add real paths, ensure `.env` /
  `backend/.env` are ignored. Drop `.idea/`, `.DS_Store`.
- `uv run pytest` + `npx vitest run` green, then 2–3 commits (pipeline, backend, frontend).

**CLAUDE.md**: how to run (uv), the "decisions don't revisit" list, the spec → plan → implement
workflow in `docs/superpowers/`.

## Phase 1 — Subject names (½ day, small, unblocks grading + RAG) — DONE

The subject is already editable (`ExamRow.vue` input, `ExamSettingsView.vue`); only the guess is weak:
`guessSubject` in `frontend/src/lib/stats.ts` takes the first word.
- Rewrite `guessSubject`: split on `[\s_\-.]+`, drop tokens that are years (`19xx/20xx`, `WS23`,
  `SS2024`, `WiSe/SoSe…`), dates, and exam-kind words in EN + DE (endterm, midterm, final, retake,
  repeat, exam, solution, sample, mock, Klausur, Wiederholung(sklausur), Nachholklausur, Endterm,
  Lösung(en), Musterlösung, Probeklausur, Probe, Hauptklausur, Semestralklausur…). The rest, joined,
  is the subject; empty → `'Other'`.
- Fallback: if the pipeline's first page has a course title, prefer that — skip unless cheap.
- Extend `stats.spec.ts` with the real patterns: `2024_Retake_GRNVS`, `Endterm 2023 GBS`,
  `GRNVS_2019 retake`, `Wiederholungsklausur_2022_Analysis`.
- Server side: the `courses` table gets used — on sync/upload the subject maps to a `course` row
  (user_id, name). Grading and RAG both key off `course_id`.

## Phase 2b — Text-first grading inputs — DONE

Fewer images per grading request: more point values read from the exam, sub/superscripts folded into text, a stricter
"visual" rule, optional docling formulas as LaTeX (Apple Silicon), editable max points. Visual subtask regions
59.5 % -> 37.2 %, missing points 2552 -> 2020, tokens per request 1018 -> 829. See `docs/2026-11-01-text-first-handoff.md`.

## Phase 2 — LLM grading + eval (3 days) — DONE

Scope grew to three providers (Anthropic, Google AI Studio, OpenRouter); see `docs/2026-10-29-llm-grading-handoff.md`.

**Grading modes** (one prompt file, `backend/app/grading/prompt.py`, so the eval pins it):
1. **Solution present** (attempt has `solutionExamId`): the solution sheet *is* the grading template.
   Prompt tells Claude to extract the rubric/point split from the solution crop(s) +
   `solution_text`/`mc_key` first, then grade strictly against it — no own opinions on what's correct.
2. **No solution**: Claude solves the subtask itself, builds its own rubric, then grades. As
   reference, include up to N similar subtasks *with solutions* from other exams of the **same
   subject** (same `course`; v1: same subtask/topic text match, later Phase 4's vector search).
   Result marked `basis: "own_solution"`.

**Output** (structured output, Pydantic):
`{points, points_min, points_max, certain: bool, basis: "solution"|"own_solution",
rubric: [{item, max, hit, note}], feedback}`.
`certain=true` ⇔ `points_min == points_max == points`; otherwise the range where the score could land
(e.g. unreadable drawing, ambiguous answer). Server clamps all three to `0..max` and enforces
`min ≤ points ≤ max` — never trust model numbers at the boundary.

**Backend** — `backend/app/grading/`, route in `app/api/routes.py`:
- `POST /api/grade`: subtask crop(s), solution crop(s) or none, reference examples (crops + solution)
  chosen by the client from same-subject exams in IndexedDB, answer (typed text and/or canvas PNG),
  points.
- Key in header `X-Anthropic-Key`, used for that call, **never stored or logged**. Missing → 400.
- Latest Sonnet via `anthropic` SDK (check `claude-api` skill for model id + structured output
  syntax). Prompt caching on the solution crops.

**Frontend**:
- `stores/settings.ts`: `anthropicKey`, stored on this device only; field in gear settings.
- `ResultsView.vue`: enable "Ask an LLM to grade" (disabled + hint if no key). Works with or without a
  solution; the label says which basis will be used.
- `types/attempt.ts` `Grade`: add `llm?: {points, min, max, certain, basis, rubric, feedback}`, shown
  next to the self-grade in `GradingRow.vue` as "4 P" or "3–5 P (unsure)".
- `ResultsView.spec.ts`: the "coming soon" test flips.

**Eval** (`backend/evals/grading/`):
- `cases.jsonl` (~30–50 of your self-graded subtasks, exported from IndexedDB), each run in both modes.
- `run_eval.py` (key from env): exact agreement %, your grade inside `[min, max]` %, mean abs error,
  how often `certain=true` was actually right (calibration), split by basis. Report to
  `results/<date>.md` + README.
- pytest with a mocked client: schema, clamping/range rules, missing key, key not logged.

## Phase 3 — Sync + MCP server (3–4 days, split into 3a and 3b)

**3a done 2026-11-03** (handoff `docs/2026-11-03-sync-handoff.md`). Agreed with the user 2026-11-02. **"Start phase 3" = start 3a**: write the
spec from this section (`docs/superpowers/specs/<date>-sync-design.md`), have the user approve it, then plan →
subagents. 3b follows in the next session with its own spec. Each part gets its own spec, plan, review and handoff.

### 3a — Auth + two-way sync across devices

User decisions: real two-way sync of exams and attempts between every device signed into the same account
(not push-only); `current_user` dependency (401) on the new routes.

Proposed design (Claude's calls, confirm in the spec):
- **Ids**: the client stores uploads under the server's `exam_id` instead of `crypto.randomUUID()`. Older local
  exams keep their random ids and are created on the server under that id on the first push (`exams.id` is
  client-made by design).
- **Migration**: `exams` + `point_overrides`, `rubrics` (JSONB), `solution_for` (UUID, no FK), `fingerprint`;
  `attempts.overtime` (bool = client `snapshot !== null`, so answer versions round-trip); `grades.llm` (JSONB).
  Answers: `main` = snapshot (or final answers when handed in on time), `over` = final answers when overtime.
- **Subject → course**: case-insensitive find-or-create (fixes the `course_id()` shortcut in `db/exams.py`).
- **`PUT /api/exams/{id}`**: metadata update; claims an anonymous row (user_id NULL); other user's id → 404;
  missing row needs `structure` + base64 crops, else `409 need_content`. Crop names `^[A-Za-z0-9_.-]+\.png$`,
  PNG signature check, 50 MB streaming body cap (like `/api/grade`).
- **`PUT /api/attempts/{id}`**: full replace of attempt + answers/times/grades rows in one transaction; running
  attempts are not synced (422); exam must be on the server (`409 need_exam`); unknown subtask ids 422.
  New `app/db/attempts.py` as counterpart of `app/db/exams.py`. `view` (UI state) is not synced.
- **`GET /api/sync?since=`**: the user's exams (metadata) + attempts with `updated_at > since - 10 s` (overlap for
  out-of-order commits), plus a new cursor. Unknown exams are fetched via existing `GET /api/exams/{id}`.
  Replaces the planned `GET /api/exams`.
- **Client**: `putExam`/`putAttempt` mark ids dirty in a localStorage outbox (not when writing a pull);
  `lib/sync.ts` push (exams before attempts, `need_content` retry, running attempts stay dirty) then pull (skip
  dirty records). Runs on sign-in/app load, tab visible, and 2 s after the last edit. First sign-in on a device
  (localStorage `sync-user` differs) marks everything local dirty. Last write wins per record; no deletes exist,
  so no tombstones.
- Out of scope: syncing running attempts, real-time push, field-level merge, separate local data per account
  on shared browsers (`shortcut:`).

### 3b — MCP server

**3b done 2026-11-04** (handoff `docs/2026-11-04-mcp-handoff.md`, usage `docs/mcp.md`).

User decisions: the value is the user's own data (exams, solutions, past answers, grades, weak spots), so the
host model (Claude Code / Desktop on the user's subscription) does the tutoring and grading itself.
`grade_answer` with a server-side key is dropped.

Proposed design (Claude's calls, confirm in the 3b spec; check FastMCP / MCP SDK docs via Context7 first):
- **Transport + auth**: streamable HTTP mounted in FastAPI at `/mcp`, personal access tokens created in the
  web app's settings (stored hashed, revocable, `Authorization: Bearer`). `shortcut:` full MCP OAuth 2.1 (needed
  for one-click claude.ai connectors) later.
- **Tools**: `list_subjects()`, `progress(subject?)` (weak topics by score share, trend, unattempted exams),
  `find_tasks(subject, query?, filter?)` (`unattempted`, `scored_below`, `has_solution`; text match now, vector
  search in Phase 4), `get_task(subtask_id)` (text, crops inline as images, points, solution / MC key),
  `my_history(subtask_id)`, `record_practice(subtask_id, answer, points, feedback)` (shows in the app, feeds
  `progress`), optional `set_points(subtask_id, points)`.
- Crops as resources `exam://{exam_id}/crop/{name}`, owner-checked. README: `claude mcp add --transport http`
  and Claude Desktop config. Tests: stored `ExamStructure` + seeded attempts, tools called in-process.
- Example session: "Quiz me on GRNVS, focus on what I'm bad at" → `progress` → `find_tasks` → `get_task`
  (solution kept hidden) → user answers in chat → Claude grades against the solution, `my_history` for repeated
  mistakes → `record_practice` → result visible in the app on every device.

## Phase 4 — RAG "Ask" + slides per subject (3–4 days)

**Data**: migration with `CREATE EXTENSION vector`; compose image → `pgvector/pgvector:pg18`.
- `documents` (user_id, course_id, kind `exam|slides|script`, filename, UNIQUE(user_id, sha256)
  server-side hash).
- `chunks` (document_id, course_id, page, bbox, text, `tsvector`, `embedding vector(n)`).
- Keep extracted text instead of deleting it (the conflict noted in `worker/main.py`).
- `jobs.kind` column (`exam | document | slack_event`); slide processing reuses the queue + SSE.

**Upload slides UI** — "Add slides" drop zone (reuse `PdfDropZone`) with a subject picker (existing
subjects + "new"):
- In **My exams** (`MyExamsView.vue`): per subject group header, so the subject is preset.
- In the **Ask** page (`/ask`, replaces ComingSoon): picker on top, shows the subject's documents.
- Requires sign-in (slides live on the server); signed-out → quiet "sign in to add slides" hint.

**Retrieval**:
- Chunking: slides by page, scripts by heading with a size cap, exams by task/subtask (already
  structured).
- Embeddings: Voyage (Anthropic-recommended) or a local model — decide in the Phase 4 spec.
- Hybrid search: Postgres full-text + vector cosine merged with Reciprocal Rank Fusion, **always
  filtered by `course_id`** when a subject is selected.
- Answer with Claude; citations = chunk ids → page crops (`pipeline/render.py`).
- **Similar tasks**: vector search over subtask chunks, scope = the exam's subject, never across
  subjects. Replaces the text match in Phase 2's no-solution grading and in MCP `search_tasks`.

## Phase 5 — Agent + Slack/Notion + webhooks (4–5 days)

5a (Slack: OAuth, webhooks, `/quiz`) is done; 5b–5d (Notion export, repair agent, study coach) follow after 6a stage 1 and 6b (order in the status line at the top).

- `integrations` table (user_id, provider, workspace id, Fernet-encrypted tokens, scopes, expiry);
  OAuth code flow reusing `app/api/auth.py` helpers, tokens kept.
- `POST /api/webhooks/slack`: url_verification, HMAC-SHA256 over `v0:ts:body` with `compare_digest`,
  5-min replay window, `event_id` UNIQUE + `ON CONFLICT DO NOTHING`, enqueue, 200 in <3s. `/quiz`
  slash command → random subtask of a subject + grade reply.
- (5b) Flashcards: export low-scored subtasks as an Anki deck (5b-1, `docs/anki.md`), then to a Notion database (5b-2, `docs/notion.md`).
- (5c) **Pipeline repair agent**: when the pipeline emits `Issue`s, the worker enqueues a repair job;
  Claude gets page images + structure, tools `get_page_image`, `move_region`, `set_points`,
  `validate`; the result must pass `ExamStructure` validation + points check, else keep the original.
- Study coach: scheduled job (exam date on `courses`) → weak topics per subject from grades → Slack DM
  + Notion practice set.

## Ongoing — Claude Code visibility

`CLAUDE.md` (Phase 0); project skill `.claude/skills/pipeline-regression` running
`app/pipeline/cli.py` on test PDFs and diffing `exam.json` against golden files (hook/pre-commit);
README "How I built this" pointing at `docs/superpowers/`.

## Verification

- Every phase: `uv run pytest` + `npx vitest run` green; new routes tested with mocked Claude/Slack.
- Phase 0: fresh clone → `uv sync` → tests pass; `docker build backend/` works.
- Phase 1: real filenames in `stats.spec.ts` produce the right subject.
- Phase 2: grade one subtask in the UI with and without a solution; `run_eval.py` writes the report.
- Phase 3a: finish an attempt on one browser, sign in on another, see it (with grades and crops).
- Phase 3b: `claude mcp add` the server, ask Claude Code to quiz you.
- Phase 4: add slides from My exams and from Ask; a question answered by a slide cites the right
  page; similar tasks never leave the subject.
- Phase 5: Slack "Send test event" passes the signature check; a retried event is processed once.

## How Claude Code works through this

**One phase = one session = one branch.** Don't run the whole roadmap in one conversation; context
fills up and quality drops. Between phases: `/clear`.

**Context that carries over** (so each fresh session starts informed, no re-explaining):
- `CLAUDE.md` (Phase 0): run commands, conventions, "decisions don't revisit", pointer to this
  roadmap and the current phase.
- `docs/roadmap.md`: this plan, with a status line per phase.
- End of each phase: update the handoff doc (`docs/<date>-<phase>-handoff.md`, like the existing one)
  with done / not done / decisions. That's the "memory" for the next session.

**Per phase, 5 steps:**
1. **Spec** — `superpowers:brainstorming` with you → `docs/superpowers/specs/<date>-<phase>.md`.
   You approve it. (This is where design questions like the grading prompt get settled.)
2. **Plan** — `superpowers:writing-plans` → `docs/superpowers/plans/...` with small, testable tasks.
3. **Implement** — `superpowers:subagent-driven-development`: one fresh subagent per plan task
   (TDD), and **a review subagent checks each task before the next starts**. Keeps the main context
   clean and catches mistakes early. Parallel agents only where tasks are truly independent
   (e.g. Phase 2: eval script ‖ frontend button) — not by default; each agent costs a cold start.
4. **Review the whole phase** before merging:
   - `/code-review high` on the branch diff (correctness).
   - `/security-review` for the phases touching keys, auth, webhooks (2, 3, 4, 5).
   - You read the diff of anything security- or data-related yourself.
5. **Verify + finish** — `superpowers:verification-before-completion` (tests + the manual check from
   Verification below), then `superpowers:finishing-a-development-branch` → commit/PR to `main`.

**Guards that run automatically** (Phase 0, via `update-config` hooks):
- After edits to `backend/app/pipeline/`: the pipeline regression check.
- Before commit: `uv run pytest` + `npx vitest run`.

Next step after approval: Phase 0 (uv, clean commit, CLAUDE.md, roadmap doc, hooks).
