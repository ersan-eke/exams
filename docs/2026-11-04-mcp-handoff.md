# Phase 3b, MCP server: status and what's left

Written 2026-11-04, after Phase 3b. Spec: `docs/superpowers/specs/2026-11-03-mcp-design.md`; plan: `docs/superpowers/plans/2026-11-03-mcp.md`.
Usage: `docs/mcp.md`. Earlier context: `docs/2026-11-03-sync-handoff.md`.
Tests at the end: backend 315 passed, frontend 315 passed (40 files), `npm run type-check` clean.
Reviews: a review after every task (Task 3 had a path-traversal finding, fixed), `/code-review high` (10 findings: 7 fixed,
3 kept as decisions below), a security review (no findings). A smoke test against real uvicorn: 401 without a token, 7 tools, no token in the log.

## Done

- **Tokens:** `access_tokens` table (migration `7cea61f142c4`) stores only the sha256. A token is `es_` + 32 random bytes, shown once.
  `GET/POST/DELETE /api/tokens` (cookie session). The Settings panel has an "MCP access" section with create, copy, a `claude mcp add` line and revoke.
- **Endpoint:** `/mcp` uses MCP SDK v2 (`mcp` 2.3.0), stateless streamable HTTP with JSON responses, through `app.add_route` (a mount 307s on
  `POST /mcp`). The FastAPI lifespan runs the session manager. `BearerAuth` (`app/mcp/auth.py`) checks the hash on every request and passes the
  user on in a ContextVar. It writes `last_used_at` at most hourly. `/mcp` is exempt from `same_origin_writes` because it uses no cookie. DNS-rebinding
  protection is off because a rebinding page can't attach the token. The Vite dev server proxies `/mcp`.
- **Tools** (`app/mcp/tools.py` holds the logic as `(db, user_id, …)` functions; `server.py` holds thin wrappers):
  `list_subjects`, `progress`, `find_tasks`, `get_task` (crops as images, solution only on request), `my_history`, `record_practice`, `set_points`.
  Only `NotFound` / `BadInput` text reaches the host; other errors stay opaque. Crop names must match `CROP_NAME` (now in
  `core/storage.py`, shared with sync) and resolve inside the exam dir.
- **Practice = attempt:** `record_practice` writes a handed-in, graded attempt for one task through `write_attempt`, so 3a sync, Results and
  Statistics show it without any frontend change.

## Not done

- **Manual check, for you:** create a token in Settings, run `claude mcp add …`, ask "quiz me on <subject>", and check that the practice attempt
  shows up in Results/Statistics after a sync. This needs a real sign-in. A Claude Desktop setup via `mcp-remote` is documented but untested.
- MCP OAuth 2.1 (one-click claude.ai connector): `shortcut:` in `app/mcp/auth.py`.
- No expiry on tokens; revoke is the only end.
- Deferred minors: `GET /api/tokens` has no id tiebreak for equal `created_at`; no test for the 100-char token name bound; courses with
  only hidden or solution exams show `exams: 0`; a non-numeric `point_overrides` value makes the score queries fail; the Copy button gives no feedback.
- ruff is not installed in the backend venv, so the new backend code wasn't linted.

## Decisions already made (don't revisit)

- Earlier handoff docs and the 3b spec still stand.
- The host model does the tutoring and grading; the server holds no LLM key and has no `grade_answer` tool.
- Personal access tokens (Bearer), stored hashed and revocable; no scopes.
- A subtask is addressed as `"<exam id>/<subtask key>"`. Unknown and foreign ids give the same "not found".
- Practice results are ordinary handed-in attempts that cover one whole task. Siblings that weren't practiced count as 0 in Statistics (accepted).
  Duplicate subtask ids in one call are rejected, points are clamped to `0..max` (at most 1000 when the max is unknown) and rounded to 2 decimals.
- Server-side max points = `point_overrides[key]` else `subtask.points`. MC subtasks that the client auto-scores (no Grade row) or whose max comes from
  the client's MC split are not counted in MCP progress (`shortcut:` on `max_points`; mirror `scoring.ts` `mcPoints` if it matters).
- `set_points` bumps the exam's `edited_at`. A later client push of `point_overrides` can still overwrite it (per-record last-edit-wins from 3a).
- `point_overrides` stays JSONB even though the MCP aggregates read it in SQL (a column move would be a migration; not worth it now).
- "unattempted" means per task in `find_tasks` and per exam in `progress`. `list_subjects` counts handed-in attempts.
- `get_task` accepts the user's own hidden and solution exams; listings exclude them.

## Where things live

- `backend/app/mcp/{auth,server,tools}.py`, token routes in `app/api/auth.py`, `AccessToken` in `app/db/models.py`, `/mcp` route + lifespan in `main.py`.
  Tests: `tests/test_tokens.py`, `tests/test_mcp_http.py` (one module-scoped lifespan client, since the session manager is single-use), `tests/test_mcp_tools.py`.
- `frontend/src/lib/tokens.ts`, `components/frame/McpTokens.vue` (in `SettingsPanel.vue`).
