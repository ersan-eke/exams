# exam-sim

Exam simulator: a FastAPI pipeline turns old exam PDFs into tasks/subtasks with page crops
(`backend/app/pipeline`), a Vue 3 app runs them as a timed exam and grades them.

## Where we are

- Roadmap and phase status: `docs/roadmap.md`. Work one phase per session.
- Latest handoff (done / not done / decisions): `docs/2026-11-26-phase-6a-stage1-handoff.md` (hosting stage 1, `docs/hosting.md`; VM go-live check open);
  earlier: `docs/2026-11-25-phase-5b2-handoff.md` (Notion export, `docs/notion.md`; live manual check open);
  earlier: `docs/2026-11-23-phase-5b1-handoff.md` (Anki export, `docs/anki.md`);
  earlier: `docs/2026-11-24-slack-crops-handoff.md` (`/quiz` shows page crops, weakest-first picking, response_url ack);
  earlier: `docs/2026-11-20-phase-5a-handoff.md` (Slack: signature rules, webhook prefix rule, no LLM in Slack; setup in `docs/slack.md`;
  earlier: `docs/2026-11-20-phase-4b-review-handoff.md` (async/session rule, upload duplicate contract);
  Ask redesign decisions: `docs/2026-11-13-ask-redesign-grill-handoff.md`, no code yet; phase 4 as built: `docs/2026-11-05-rag-handoff.md`).
  Write a new handoff doc at the end of each phase.

## Run

- DB: `docker compose up -d db` (root `compose.yaml`, image `pgvector/pgvector:pg18`; an older `postgres:18` volume needs
  `ALTER DATABASE <db> REFRESH COLLATION VERSION` on `template1`, `postgres` and `examsim`, then `REINDEX DATABASE examsim`).
- Backend (from `backend/`, uv only, no pip): `uv sync`, `uv run alembic upgrade head`,
  `uv run uvicorn main:app`, `uv run python -m app.worker.main`. Add deps with `uv add`.
  `DEV=1` turns on the dev-only request preview endpoint of the Ask AI turn (404 otherwise).
- Frontend (from `frontend/`): `npm run dev` (proxies `/api` and `/mcp`, keep `changeOrigin: false`).
- MCP server for Claude Code / Desktop: `/mcp` with a personal access token, see `docs/mcp.md`.
- Production (home VM, Cloudflare tunnel): `docs/hosting.md`, compose file `deploy/compose.prod.yaml`.
- Tests: `uv run pytest` in `backend/` (needs the DB; uses `examsim_test`), `npx vitest run` in `frontend/`.
- Lint (from `backend/`): `ruff check . && ruff format .` before committing backend changes (config in `pyproject.toml`).

## Testing levels

- Features that don't touch the pipeline (grading, MCP, RAG, Slack): no PDFs; use a stored
  `ExamStructure` + mocked Claude/Slack.
- Pipeline changes: `uv run python -m app.pipeline.smoke` (15 PDFs chosen to cover every feature,
  ~13s, compared against `backend/tests/pipeline_smoke.json`). Runs automatically via a hook after
  edits under `backend/app/pipeline/`. Intended change → `--update`. New sample PDFs → `--select`.
- Before merging pipeline changes: all of `samples/` with `uv run python -m app.pipeline.cli ../samples`.

## Workflow

Per phase: spec (`superpowers:brainstorming` → `docs/superpowers/specs/`) → plan
(`superpowers:writing-plans` → `docs/superpowers/plans/`) → `superpowers:subagent-driven-development`
with a review after every task → `/code-review high` (+ `/security-review` when keys, auth or webhooks
are touched) → verify → commit.

After each ticket's review (also when running `/implement` or any other flow that ends in review and commit), automatically, without being
asked: append every finding you did not fix to `docs/findings.md` (format and rules there) before the final commit, or in a follow-up
commit right after; delete an entry in the commit that fixes it. Say in the final reply which findings were recorded.

## Rules

- Decisions in every handoff doc's "Decisions already made" are settled; don't revisit them.
- Columns for what is joined/filtered/summed, JSONB for what is read and written whole.
- Never commit exam PDFs or crops (copyright): `samples/`, `results/`, `*.pdf` are ignored.
- The user's LLM key (Anthropic, Google AI Studio, OpenRouter) is sent per request in `X-LLM-Key` and never stored or logged on the server.
- Migrations only add (tables, nullable columns, indexes); a drop or rename is a later release once no deployed image reads the old shape (rollback runs an older image on the newer schema).
- Deliberate simplifications carry a `shortcut:` comment saying when to upgrade.
- Always use the Context7 CLI skill (`find-docs`) when I need library/API documentation, code generation, setup or configuration steps, without me having to explicitly ask.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for `ersan-eke/exam-sim` (via the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. When the answer is under a Markdown heading, `graphify section "<heading>"` prints that section's text, so the .md need not be opened. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
