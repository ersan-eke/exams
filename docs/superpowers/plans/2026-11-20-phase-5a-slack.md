# Phase 5a: integrations + Slack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A signed-in user connects Slack ("Add to Slack"), and `/quiz <subject>` in Slack serves them a question from their own exams, answered with buttons.

**Architecture:** An `integrations` table stores per-user, per-workspace Slack bot tokens Fernet-encrypted. A new `app/slack/` package holds the pure parts (signature check, Block Kit messages, quiz logic over the existing `app/mcp/tools.py`); `app/api/integrations.py` is the OAuth connect/disconnect surface (Authlib, same state/PKCE machinery as login); `app/api/slack.py` is the signed webhook receiver. Handlers do only DB reads, so the 3 s ack holds; replies to `response_url` run as background tasks.

**Tech Stack:** FastAPI, SQLAlchemy 2 + Alembic, Authlib, `cryptography` (Fernet/MultiFernet), httpx, Vue 3 + vitest.

**Spec:** `docs/superpowers/specs/2026-11-20-phase-5a-slack-design.md` (approved 2026-11-21, including its *(my call)* items)

## Global Constraints

- Branch `phase-5a-slack` off `main`; one commit per task; `ruff check . && ruff format .` in `backend/` before each backend commit.
- Sync `Session`. Endpoints without `await` are plain `def`; an `async def` touches the session only inside `run_in_threadpool` and reads no ORM attribute after commit/rollback on the event loop.
- Signature: HMAC-SHA256 hex of `v0:{timestamp}:{raw body bytes}`, header `X-Slack-Signature: v0=<hex>`, `hmac.compare_digest`, reject timestamps more than 300 s from now, either direction.
- Slack config env vars: `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_SIGNING_SECRET`; `INTEGRATIONS_KEY` = comma-separated Fernet keys, the first encrypts, all decrypt. Unset ⇒ Slack features answer 404 and `/api/integrations` reports `slack.enabled=false`.
- Bot scopes: `commands`, `chat:write`. Slash command `/quiz`. OAuth endpoints `https://slack.com/oauth/v2/authorize` and `https://slack.com/api/oauth.v2.access`.
- No token (bot, client secret, signing secret, Fernet key) in logs, exceptions or responses. Webhook endpoints never return 500 for bad input: 401 bad/missing signature, 400 malformed body.
- New deps via `uv add`; deliberate simplifications carry `shortcut:` comments.
- Tests: `uv run pytest` in `backend/` (needs `docker compose up -d db`), `npx vitest run` in `frontend/`. Slack HTTP calls are mocked; never hit slack.com.

## Review Focus

Each line gets a test in the named task.

1. Body with non-ASCII text (a subject like "Algorithmen für Ärzte") signs and verifies over the raw bytes, not a re-encoded form (Task 2).
2. Missing, empty, non-numeric or future timestamp / missing signature header gives 401, never 500 (Task 2).
3. A Slack user with no linked account who runs `/quiz` gets an ephemeral "connect" message and no question; another user's subject name never leaks (Task 5).
4. The same Slack identity connected by a second exam-sim user: callback redirects with a failure flag, the first link is untouched, no 500 (Task 3).
5. Consent cancelled on Slack (`?error=access_denied`) and a callback with no signed-in user redirect with a flag, no 500 (Task 3).
6. `/quiz` with an unknown subject, no subject, or a subject with no usable text lists the user's subjects / says so; a tampered button `value` pointing at someone else's subtask answers "not found" (Task 5).
7. Block Kit limits: a subtask text over 3000 chars is truncated; a subtask with more than 5 MC options still produces valid blocks (Task 5).
8. A retried Events API delivery (same `event_id`) deletes/handles once and still answers 200 (Task 4).

---

### Task 1: Encrypted integrations storage

**Files:**
- Modify: `backend/app/core/config.py`, `backend/app/db/models.py`, `backend/pyproject.toml` (via `uv add cryptography`), `backend/.env.example`
- Create: `backend/app/core/crypto.py`, `backend/alembic/versions/f4a5b6c7d8e9_integrations.py` (down_revision `d3e4f5a6b7c8`)
- Test: `backend/tests/test_crypto.py`, extend `backend/tests/test_db.py` only if it enumerates tables

**Interfaces:**
- Produces: `config.SLACK: tuple[str|None, str|None, str|None]` (client id, client secret, signing secret), `config.INTEGRATIONS_KEY: str|None`, `config.SLACK_ENABLED: bool` (all four set).
- Produces: `crypto.encrypt(plain: str) -> str`, `crypto.decrypt(token: str) -> str` (MultiFernet over `INTEGRATIONS_KEY.split(",")`; raise `RuntimeError("INTEGRATIONS_KEY not set")` when unset; `decrypt` raises `cryptography.fernet.InvalidToken` on a wrong key).
- Produces models: `Integration(id uuid pk, user_id fk users cascade indexed, provider choice("integration_provider","slack","notion"), workspace_id str, workspace_name str, external_user_id str, access_token str /*ciphertext*/, scopes str, expires_at datetime|None, created_at)` with `UniqueConstraint(provider, workspace_id, external_user_id)`; `WebhookEvent(provider str, event_id str, received_at)` with composite primary key `(provider, event_id)`.

- [ ] **Step 1: Write failing tests** in `test_crypto.py`: `test_round_trip` (`decrypt(encrypt("xoxb-1")) == "xoxb-1"` and ciphertext != plaintext); `test_rotation` (token made under key A decrypts when `INTEGRATIONS_KEY="B,A"`, new tokens made under B); `test_unset_key_raises` (RuntimeError); `test_integration_unique_per_slack_identity` (db fixture: two `Integration` rows with same provider/workspace/external_user_id for two users ⇒ `IntegrityError`); `test_webhook_event_conflict_is_ignored` (insert same `(provider, event_id)` twice with `postgresql.insert(...).on_conflict_do_nothing()` ⇒ `rowcount` 1 then 0). Monkeypatch `crypto` to read the key at call time, so tests can change it.
- [ ] **Step 2:** `uv run pytest tests/test_crypto.py -v` ⇒ FAIL (modules missing).
- [ ] **Step 3:** `uv add cryptography`; add config values (follow the `OAUTH` pattern, `SLACK_ENABLED` computed); write `crypto.py`; add both models in `db/models.py` (use `choice(...)`, `created()`); write the Alembic migration by hand in the style of `d3e4f5a6b7c8_outline.py` (`upgrade` creates both tables, `downgrade` drops them); append the four env vars with setup comments (Slack app page, redirect URL `http://localhost:5173/api/integrations/slack/callback` via the tunnel, how to generate a Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) to `.env.example`.
- [ ] **Step 4:** `uv run pytest tests/test_crypto.py tests/test_db.py -v` ⇒ PASS (the session fixture replays all migrations, so the migration is tested).
- [ ] **Step 5:** `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` on the dev DB, then ruff and commit `feat: encrypted integrations table`.

### Task 2: Slack signature verification

**Files:**
- Create: `backend/app/slack/__init__.py` (empty), `backend/app/slack/signature.py`
- Test: `backend/tests/test_slack_signature.py`

**Interfaces:**
- Produces: `signature.verify(secret: str, timestamp: str | None, signature: str | None, body: bytes, now: float | None = None) -> bool` (never raises; `now` defaults to `time.time()`).
- Produces: `signature.sign(secret: str, timestamp: str, body: bytes) -> str` returning `"v0=<hex>"` (used by `verify` and by tests of later tasks).
- Produces: `async def verified_body(request: Request) -> bytes`, a FastAPI dependency: 404 when `not SLACK_ENABLED`, 401 when `verify` fails, else the raw body.

- [ ] **Step 1: Write failing tests:** `test_valid_signature_passes`; `test_wrong_secret_fails`; `test_body_tampered_fails`; `test_stale_timestamp_fails` (301 s old) and `test_future_timestamp_fails` (301 s ahead); `test_boundary_299s_passes`; `test_missing_or_garbage_inputs_fail` parametrised over `timestamp in (None, "", "abc", "1e9")` and `signature in (None, "", "v0=", "v1=…", "v0=zz")` ⇒ `False`, no exception (Review Focus 2); `test_non_ascii_body` signs `"text=Algorithmen+für+Ärzte".encode()` and verifies (Review Focus 1).
- [ ] **Step 2:** run ⇒ FAIL.
- [ ] **Step 3:** implement. Parse the timestamp with `int()` inside try/except; compare with `hmac.compare_digest` on equal-type strings (encode both, so a non-ASCII header cannot raise).
- [ ] **Step 4:** run ⇒ PASS. Add one route-level test later in Task 4 for the dependency.
- [ ] **Step 5:** ruff, commit `feat: Slack request signature check`.

### Task 3: Connect, list and disconnect Slack (OAuth)

**Files:**
- Create: `backend/app/api/integrations.py`, `backend/app/slack/client.py`
- Modify: `backend/main.py` (include router with prefix `/api`)
- Test: `backend/tests/test_integrations.py`

**Interfaces:**
- Consumes: `auth.current_user`, `auth.optional_user`, `crypto.encrypt`, `config.SLACK*`, `Integration`.
- Produces `client.revoke(token: str) -> None` (async httpx POST `https://slack.com/api/auth.revoke`, swallows and logs only the status on failure).
- Produces routes: `GET /api/integrations` ⇒ `{"slack": {"enabled": bool, "connections": [{"id": str, "workspace": str, "connectedAt": int_ms}]}}` (current user only, never the token); `GET /api/integrations/slack/connect` ⇒ redirect to Slack (401 without session, 404 when disabled); `GET /api/integrations/slack/callback` (route name `slack_callback`) ⇒ 303 to `/?integration=slack` on success or `/?integration=failed`; `DELETE /api/integrations/{id}` ⇒ 204, 404 for another user's row, calls `client.revoke` on the decrypted token then deletes the row.
- Produces `integrations.exchange(request: Request) -> dict` (module-level, so tests monkeypatch it like `auth.identity`): returns `{"access_token", "scope", "team_id", "team_name", "authed_user_id"}` from Slack's `oauth.v2.access` response after Authlib checked state/PKCE.

- [ ] **Step 1: Write failing tests** (use `signed_in` from `test_auth`; monkeypatch `integrations.exchange` and `client.revoke`): connect redirects to `slack.com/oauth/v2/authorize` with `scope=commands,chat:write`, state and PKCE challenge, and 401s signed out; callback stores a row whose `access_token` column is not the plaintext and decrypts to it; `GET /api/integrations` shows the workspace and contains no `token`/`access_token` key; connecting the same workspace again by the same user is idempotent (one row, token updated); Review Focus 4 (second user, same `authed_user_id` ⇒ `/?integration=failed`, first row unchanged); Review Focus 5 (`?error=access_denied`, and a callback with no session cookie ⇒ `/?integration=failed`); a callback with a missing or mismatched `state` ⇒ `/?integration=failed` and no row (do not monkeypatch `exchange` past Authlib's state check for this test, or patch only the token fetch); delete removes the row and calls revoke once; another user's delete ⇒ 404; with `SLACK_ENABLED` false, `/connect` ⇒ 404 and the list says `enabled: false`.
- [ ] **Step 2:** run ⇒ FAIL.
- [ ] **Step 3:** implement. Register a separate `OAuth()` client `slack` (authorize/access URLs above, `client_kwargs={"scope": "commands,chat:write", "code_challenge_method": "S256"}`) mirroring `auth.py`'s registration, only when enabled. Callback: `OAuthError` ⇒ failed redirect; upsert by `(provider, workspace_id, external_user_id)` and, on a row owned by a different user, fail without touching it; DB work in `run_in_threadpool`; log only an error code.
- [ ] **Step 4:** run ⇒ PASS.
- [ ] **Step 5:** ruff, commit `feat: connect and disconnect Slack`.

### Task 4: Slack webhook receiver: events, dedup, uninstall

**Files:**
- Create: `backend/app/api/slack.py`
- Modify: `backend/main.py` (include router, prefix `/api`), `backend/app/worker/main.py` (`cleanup` deletes `WebhookEvent` rows older than 7 days)
- Test: `backend/tests/test_slack_events.py`, extend `backend/tests/test_worker.py` for the cleanup

**Interfaces:**
- Consumes: `signature.verified_body`, `signature.sign`, `WebhookEvent`, `Integration`.
- Produces: `POST /api/webhooks/slack/events` (JSON). `url_verification` ⇒ `{"challenge": …}`. `event_callback`: insert `(provider="slack", event_id)` with `ON CONFLICT DO NOTHING`; if it was new and `event.type in ("app_uninstalled", "tokens_revoked")`, delete the `Integration` rows with `provider="slack"` and `workspace_id == team_id`; always 200 `{}`. Unparseable JSON or a missing `type` ⇒ 400.
- Produces test helper `slack_post(client, path, body: bytes, secret=…, ts=None, content_type=…)` in `backend/tests/conftest.py` or a `tests/slack_util.py` (signs with `signature.sign`); later tasks import it. Set `SLACK_*` and `INTEGRATIONS_KEY` env vars in conftest the way `GITHUB_*` are.

- [ ] **Step 1: Write failing tests:** unsigned / bad-signature / stale ⇒ 401 for all three paths (parametrise path; the other two return 404 until Task 5, so assert 401 only on `events` here and extend in Task 5); `url_verification` echoes the challenge; `app_uninstalled` deletes the workspace's rows only (another workspace's row stays); the same `event_id` delivered twice processes once (delete a row, re-add a row, redeliver ⇒ the re-added row survives, still 200) (Review Focus 8); `event_callback` of an unknown type ⇒ 200 and no change; malformed JSON ⇒ 400; a request carrying a foreign `Origin` header still reaches the signature check (documents that the middleware does not interfere: Slack sends none) ; worker cleanup removes only events older than 7 days.
- [ ] **Step 2:** run ⇒ FAIL.
- [ ] **Step 3:** implement; `async def` handlers parse the body from `verified_body`, DB work via `run_in_threadpool`. Add `# shortcut: handled inline; move to the job queue when a handler does slow work (5d)`.
- [ ] **Step 4:** run ⇒ PASS.
- [ ] **Step 5:** ruff, commit `feat: Slack events webhook with dedup`.

### Task 5: `/quiz` command and answer buttons

**Files:**
- Create: `backend/app/slack/blocks.py`, `backend/app/slack/quiz.py`
- Modify: `backend/app/api/slack.py` (two routes), `backend/app/slack/client.py` (`respond`)
- Test: `backend/tests/test_slack_quiz.py`

**Interfaces:**
- Consumes: `tools.find_tasks(db, user_id, subject, None, None)`, `tools.get_task(db, user_id, ref, include_solution)`, `tools.list_subjects`, `tools.NotFound`, `tools.BadInput` (all in `app/mcp/tools.py`; `get_task` also returns crop paths, ignore them).
- Produces `quiz.linked_user(db, team_id: str, slack_user_id: str) -> uuid.UUID | None` (via `Integration`).
- Produces `quiz.question(db, user_id, subject: str) -> dict` and `quiz.answer(db, user_id, ref: str, choice: int | None) -> dict`, both returning a Slack message payload (`response_type: "ephemeral"`, `blocks`, fallback `text`). `question` picks `random.choice` among `find_tasks` rows whose subtask text is non-empty; empty/unknown subject ⇒ a message listing the user's subjects (from `list_subjects`) or "no exams yet". `answer` with `choice` compares `{choice}` to `mc_key` and says right/wrong, then always shows the solution text and, for MC, the correct option(s); `choice=None` is "Show solution". A ref the user does not own ⇒ a "Question not found" message (catch `NotFound`/`BadInput`).
- Produces `blocks.question_blocks(task: dict) -> list[dict]` (section text truncated to 2900 chars; heading with exam, task, label, points; MC options as `actions` blocks of at most 5 buttons each, `action_id="answer"`, `value=f"{ref}|{index}"`, button label truncated to 75 chars; non-MC a single "Show solution" button `action_id="reveal"`, `value=ref`), `blocks.answer_blocks(task: dict, choice: int | None) -> list[dict]`, `blocks.connect_message(url: str) -> dict`.
- Produces `client.respond(response_url: str, message: dict) -> None` (async httpx POST, `replace_original: true`, log status only on failure).
- Produces routes: `POST /api/webhooks/slack/commands` (form `team_id`, `user_id`, `text`, `command`): unlinked ⇒ `connect_message(f"{base}/")` where base comes from `request.base_url`; else `quiz.question(...)` as the JSON response. `POST /api/webhooks/slack/interactions` (form `payload` = JSON `block_actions`): resolve the user from `team.id`/`user.id`, parse `value` (`rsplit("|", 1)` for answer), compute `quiz.answer`, post it with `client.respond` in a `BackgroundTasks`, return 200 immediately.

- [ ] **Step 1: Write failing tests** with a seeded user, an exam with one MC subtask (3 options, `mc_key=[1]`) and one text subtask, an `Integration` linking `T1/U1`, using `slack_post`: `/quiz Algo` ⇒ ephemeral, blocks contain 3 answer buttons with `value` `"<exam>/<key>|0"`; unlinked `U9` ⇒ connect message, no question text (Review Focus 3); unknown and empty subject ⇒ lists the user's subjects only (Review Focus 6); clicking option 1 ⇒ `respond` receives text containing the right-answer wording and the solution; option 0 ⇒ wrong wording; reveal ⇒ solution only; tampered ref of another user's exam ⇒ "not found" (Review Focus 6); text of 5000 chars ⇒ section ≤ 3000; 7 options ⇒ two actions blocks, each ≤ 5 elements (Review Focus 7); all three routes 401 with a bad signature; a bad `payload` JSON ⇒ 400. Monkeypatch `client.respond` to capture calls.
- [ ] **Step 2:** run ⇒ FAIL.
- [ ] **Step 3:** implement. Pick-random is `random.choice` over the (≤20) rows `find_tasks` returns, `# shortcut: samples the first 20 matches, so a huge subject is not uniformly random; query the whole subject when that matters`. Compose messages in `blocks.py` only; `quiz.py` stays free of Slack JSON shapes beyond calling `blocks`.
- [ ] **Step 4:** run the whole backend suite `uv run pytest -q` ⇒ PASS.
- [ ] **Step 5:** ruff, commit `feat: /quiz slash command and answer buttons`.

### Task 6: Settings card in the frontend

**Files:**
- Create: `frontend/src/lib/integrations.ts`, `frontend/src/components/frame/SlackIntegration.vue`, `frontend/src/components/frame/__tests__/SlackIntegration.spec.ts`
- Modify: `frontend/src/components/frame/SettingsPanel.vue` (render it under `McpTokens`, `v-if="account.user"`)

**Interfaces:**
- Consumes: `GET /api/integrations`, `DELETE /api/integrations/{id}` (Task 3 shapes); follow `lib/tokens.ts` for the fetch helpers and error style.
- Produces: `listIntegrations(): Promise<{ slack: { enabled: boolean; connections: { id: string; workspace: string; connectedAt: number }[] } }>`, `disconnectIntegration(id: string): Promise<void>`.

- [ ] **Step 1: Write failing component tests** modelled on `McpTokens.spec.ts`: renders nothing when `enabled` is false; with no connections shows an "Add to Slack" link whose `href` is `/api/integrations/slack/connect`; with a connection shows the workspace name and a Disconnect button that calls `disconnectIntegration` and removes the row; a failed list or disconnect shows an error with `role="alert"`; the card shows the hint "Use /quiz &lt;subject&gt; in Slack" when connected.
- [ ] **Step 2:** `npx vitest run src/components/frame` ⇒ FAIL.
- [ ] **Step 3:** implement, copying `McpTokens.vue` conventions (script setup, `run()` error wrapper, `.label` heading, scoped styles). Also read `?integration=failed|slack` on load in the place the app mounts the settings panel (builder's call where), show a one-line notice, and strip the query with `history.replaceState`.
- [ ] **Step 4:** `npx vitest run` ⇒ PASS.
- [ ] **Step 5:** commit `feat: Slack card in settings`.

### Task 7: Docs, manifest and manual check

**Files:**
- Create: `docs/slack.md`, `docs/slack-app-manifest.yml`, `docs/2026-11-20-phase-5a-handoff.md`
- Modify: `docs/roadmap.md` (status line, mark 5a done and 5b–5d next), `CLAUDE.md` ("Latest handoff" pointer)

- [ ] **Step 1:** write `docs/slack-app-manifest.yml` (bot user, scopes `commands`, `chat:write`, slash command `/quiz` ⇒ `<tunnel>/api/webhooks/slack/commands`, interactivity ⇒ `…/interactions`, event subscriptions ⇒ `…/events` with bot events `app_uninstalled`, `tokens_revoked`, redirect URL `<tunnel>/api/integrations/slack/callback`). Write `docs/slack.md`: create the app from the manifest, tunnel (`cloudflared tunnel --url http://localhost:5173`), env vars, connect from Settings, what `/quiz` does and does not do (no LLM grading, no crops, why).
- [ ] **Step 2: Manual check** (the roadmap's verification): in the Slack app page press "Send test event" / complete the URL verification ⇒ passes; connect from Settings ⇒ the card shows the workspace; `/quiz <subject>` ⇒ a question; click an option ⇒ right/wrong plus solution; disconnect ⇒ the row is gone and `/quiz` answers with the connect link. Replay a captured events request twice with `curl` (same signature) ⇒ the second is a no-op, and with a timestamp older than 5 minutes ⇒ 401.
- [ ] **Step 3:** write the handoff (done / not done / "Decisions already made": signature rules, one-row-per-Slack-identity, no LLM in Slack and why, ephemeral messages, text only) and update the roadmap and CLAUDE.md pointers.
- [ ] **Step 4:** run `/code-review high` and `/security-review` (tokens, auth, webhooks are touched); append unfixed findings to `docs/findings.md`; `uv run pytest -q` and `npx vitest run` green; `graphify update .`.
- [ ] **Step 5:** commit `docs: phase 5a Slack handoff`.
