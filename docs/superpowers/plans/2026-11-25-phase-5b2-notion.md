# Phase 5b-2: Notion flashcard export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A signed-in student connects Notion in Settings, presses one button on a Subject's statistics page, and a worker job writes that Subject's weak subtasks as crop cards into a "Flashcards: exam-sim" database with Table, Board (by Status) and Gallery views.

**Architecture:** Notion is the second provider of the 5a `integrations` flow. Its OAuth uses our own `state` and a JSON token request, because Notion wants a JSON body. A new `app/notion/` package holds a sync HTTP client (pacing, retries, file upload), a pure card builder and the exporter. The export is a `jobs` row of kind `notion` with a `course_id`. Two tables remember the created database and every exported card, so a retry or re-export only adds what is missing. The weak-subtask selection and the crop paths come from 5b-1 (`tools.weak_refs`, `tools.latest_shares`, `tools.get_task`).

**Tech Stack:** FastAPI, SQLAlchemy 2 + Alembic, `httpx`, `cryptography` (all installed), Vue 3 + vitest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-23-phase-5b-anki-notion-design.md`, section "5b-2 Notion (brainstormed 2026-11-25)". Rules from `CLAUDE.md` and the 5a/5b-1 handoffs apply (sync `Session`, plain `def` where no `await`, `shortcut:` comments, tokens never logged).

## Global Constraints

- Branch `phase-5b-notion` off `main`; one commit per task; `ruff check . && ruff format .` in `backend/` before each backend commit.
- Notion is offered only when `NOTION_CLIENT_ID`, `NOTION_CLIENT_SECRET` and `INTEGRATIONS_KEY` are set (`config.NOTION_ENABLED`, read at call time like `SLACK_ENABLED`). Otherwise its routes answer `404` and `/api/integrations` reports `notion.enabled=false`.
- Notion API: base `https://api.notion.com/v1`, header `Notion-Version: 2026-03-11`. Authorize `https://api.notion.com/v1/oauth/authorize?client_id=…&response_type=code&owner=user&redirect_uri=…&state=…`. Token `POST /v1/oauth/token` with HTTP Basic `client_id:client_secret` and a **JSON** body: `{"grant_type": "authorization_code", "code", "redirect_uri"}`, or `{"grant_type": "refresh_token", "refresh_token"}`. A refresh returns a new access token **and a new refresh token**; store both.
- Limits: about 3 requests per second per connection; 100 blocks per request; 2000 characters per rich-text item; 5 MiB per file on free workspaces. File uploads must be attached within 1 hour; we attach right away.
- Database: title `Flashcards: exam-sim`, created at workspace level (no `parent`), `is_inline: false`. Properties on `initial_data_source` exactly: `Question` (title), `Subject` (select), `Exam` (select), `Type` (select: `Multiple choice`, `Open`), `Score %` (number, format `percent`, stored as a 0..1 fraction), `Status` (select: `New`, `Learning`, `Known`; new rows get `New`).
- Views, created right after the database: the default Table stays; `Board` (type `board`, grouped by `Status`, `sort: manual`); `Gallery` (type `gallery`, `cover: {"type": "page_content"}`, `cover_size: "large"`, `cover_aspect: "contain"`).
- Card = page in the data source. Title `<exam> · <task> <label>` (parts that are empty are left out). Body: the question crops as `image` blocks (`type: file_upload`), then a `toggle` titled `Answer` holding the solution crops. The 5b-1 rule: text only where crops are missing. The question text, context and lettered MC options appear only when the subtask has no question crop. The solution text and `Correct: <letters>` appear only when there is no solution crop. `No solution stored.` appears when both are empty.
- Weak = 5b-1: `tools.weak_refs(db, user_id, course_id, anki.BELOW, anki.LIMIT)` (latest share strictly below 0.6, at most 200).
- One Notion workspace per user *(my call, `shortcut:`)*. Reconnecting the same workspace updates the row in place, so its database and cards survive. Connecting a different workspace deletes the user's other Notion row, which cascades to its database and card rows.
- Tokens are Fernet ciphertext (`core/crypto.py`), never logged or returned. Notion errors log the status code and Notion's `code` field only.
- Existing cards are never updated, and nothing is read back from Notion.
- Tests never hit notion.com. The client tests use `httpx.MockTransport`; the exporter tests use an in-memory fake of the client functions; the OAuth tests monkeypatch `exchange_notion`. Run `uv run pytest` in `backend/` (needs `docker compose up -d db`) and `npx vitest run` in `frontend/`.

## Review Focus

- **Double click, a second tab, or two workers.** At most one active Notion job per Subject (partial unique index, Task 1). Exports of two Subjects of one user never create two databases or race a token refresh, because the exporter holds a per-integration advisory lock (Task 5 test).
- **The database or a card's parent is deleted or trashed in Notion.** The next export drops the stored database and its card rows, creates the database once, re-sends all weak cards, and does not loop if the new one fails too (Task 5 test).
- **Token expired, revoked, or the app removed from the workspace.** A 401 triggers one refresh; the rotated refresh token is stored before the retry. A failed or missing refresh ends the job as `notion_auth` without retrying, and the UI says to reconnect (Task 5 and 7 tests).
- **A crop over 5 MiB, or a missing crop file.** It is left out, and the card falls back to text the same way as a subtask without crops. The job does not fail (Task 4 and 5 tests).
- **A worker crash halfway.** Cards are committed one by one, so the retry skips the ones already sent. A crash between Notion's answer and the commit can leave at most one duplicate page (`shortcut:` comment, Task 5 test for the resume).

---

### Task 1: Tables, config, migration

**Files:**
- Modify: `backend/app/db/models.py`, `backend/app/core/config.py`, `backend/.env.example`
- Create: `backend/alembic/versions/<rev>_notion.py` (down_revision `f4a5b6c7d8e9`, the current head; confirm with `uv run alembic heads`)
- Test: `backend/tests/test_notion_models.py`

**Interfaces:**
- Config: `NOTION: tuple[str | None, str | None]` (client id, secret from `NOTION_CLIENT_ID`, `NOTION_CLIENT_SECRET`), `NOTION_ENABLED = all(NOTION) and bool(INTEGRATIONS_KEY)`.
- `Integration.refresh_token: Mapped[str | None]` (ciphertext). `expires_at` (already there) is set from the token's `expires_in` when Notion sends one.
- `NotionDatabase` (`notion_databases`): `integration_id` PK FK `integrations` CASCADE, `database_id: str`, `data_source_id: str`, `url: str`.
- `NotionCard` (`notion_cards`): `integration_id` FK `integrations` CASCADE, `exam_id` FK `exams` CASCADE, `subtask_key: str`, `page_id: str`. Primary key `(integration_id, exam_id, subtask_key)`.
- `Job.kind` gains `"notion"` (`VARCHAR(8)` fits). New `Job.course_id: Mapped[uuid.UUID | None]` FK `courses` CASCADE, set only for Notion jobs. New partial unique index `uq_jobs_active_notion` on `jobs(course_id)` `WHERE kind = 'notion' AND status IN ('queued','running')`. New `error_code` values: `nothing_weak`, `notion_not_connected`, `notion_auth` (extend the column comment).

- [ ] **Step 1: Write the failing tests.**
  - `test_cards_cascade_with_integration_and_exam`: deleting the integration removes its `NotionDatabase` and `NotionCard` rows; deleting an exam removes only that exam's cards.
  - `test_card_key_is_unique`: the same `(integration, exam, key)` inserted twice raises `IntegrityError`.
  - `test_one_active_notion_job_per_course`: a second `queued` Notion job for the same course raises `IntegrityError`. A `done` one plus a `queued` one is fine.
  - `test_job_kind_notion_is_accepted`.
- [ ] **Step 2: Run** `uv run pytest tests/test_notion_models.py -v`. Expected: FAIL (names missing).
- [ ] **Step 3: Implement** the models, config and migration. The `job_kind` CHECK constraint comes from `a9f3c1d2e4b6_rag.py` (`sa.Enum(..., native_enum=False, create_constraint=True)`). Look up its real name with `\d jobs` before you write `op.drop_constraint`, then recreate it with three values. The downgrade reverses everything. Add `NOTION_CLIENT_ID` and `NOTION_CLIENT_SECRET` to `.env.example`.
- [ ] **Step 4: Run** `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`, then `uv run pytest tests/test_notion_models.py -v`. Expected: no errors, PASS.
- [ ] **Step 5: Commit** `feat: tables and config for the Notion export`.

### Task 2: Connect Notion

**Files:**
- Modify: `backend/app/api/integrations.py`
- Test: `backend/tests/test_integrations.py` (append; reuse `connect`, `rows` and the signed-in browser setup it already has)

**Interfaces:**
- Consumes: Task 1 config and models, `encrypt`/`decrypt`.
- `GET /api/integrations/notion/connect`: puts `secrets.token_urlsafe(32)` in `request.session["notion_state"]` (the `oauth_state` SessionMiddleware in `main.py`) and redirects to the authorize URL with `redirect_uri = url_for("notion_callback")`. Answers `404` when disabled and `401` without a session.
- `GET /api/integrations/notion/callback` (name `notion_callback`): pops the session state and compares it with `secrets.compare_digest`. A mismatch, an `error` parameter or a missing `code` sends the browser to `/?integration=notion_failed`. Success sends it to `/?integration=notion`.
- `async def exchange_notion(code: str, redirect_uri: str) -> dict` returns `{"access_token", "refresh_token" (str | None), "expires_in" (int | None), "workspace_id", "workspace_name", "external_user_id"}`. It is one `httpx.AsyncClient` POST using the Global Constraints shape, and `external_user_id` is `owner.user.id`. Tests monkeypatch it the way `fake_exchange` patches `exchange`.
- `_save(db, user_id, provider, t) -> bool` is shared by both providers. The Slack callback maps its dict onto the same keys (`workspace_id`, `workspace_name`, `external_user_id`, `access_token`, `scope`, plus optional `refresh_token`, `expires_in`). For Notion, it also deletes the user's Notion rows in other workspaces.
- `GET /api/integrations` adds `notion: {enabled, connections: [{id, workspace, connectedAt}], databaseUrl: str | None}`, and each provider lists only its own rows.
- `DELETE /api/integrations/{id}` calls `slack.client.revoke` only for `provider == "slack"`. A Notion row is just deleted (`shortcut:` the student also removes the connection in Notion's settings; wire Notion's revoke endpoint when that is worth it).

- [ ] **Step 1: Write the failing tests:**
  - `test_notion_connect_sets_state_and_redirects`: `owner=user` and the state are in the redirect URL.
  - `test_notion_callback_saves_encrypted_tokens`: the row has `provider="notion"`, `decrypt` of both tokens gives the fake values, and `expires_at` is about now plus `expires_in`.
  - `test_notion_state_mismatch_fails`, and `test_notion_denied_fails` for `?error=access_denied`.
  - `test_notion_reconnect_same_workspace_keeps_row_id`.
  - `test_notion_other_workspace_replaces_row`.
  - `test_notion_identity_of_another_user_is_refused`.
  - `test_notion_disabled_is_404`.
  - `test_list_separates_slack_and_notion` (includes `databaseUrl`).
  - `test_disconnect_notion_does_not_call_slack_revoke`.
- [ ] **Step 2: Run** `uv run pytest tests/test_integrations.py -k notion -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Keep the Slack callback's error handling as it is: `OAuthError`, `KeyError`/`TypeError`/`httpx.HTTPError` and `run_in_threadpool(_save, …)`. The Notion callback catches `KeyError`, `TypeError` and `httpx.HTTPError` around `exchange_notion`, with `raise_for_status` inside it.
- [ ] **Step 4: Run** `uv run pytest tests/test_integrations.py -v`. Expected: all PASS (the Slack tests prove the shared `_save`).
- [ ] **Step 5: Commit** `feat: connect a Notion workspace`.

### Task 3: Notion HTTP client

**Files:**
- Create: `backend/app/notion/__init__.py`, `backend/app/notion/client.py`
- Test: `backend/tests/test_notion_client.py`

**Interfaces:**
- `NOTION_VERSION = "2026-03-11"`. Exceptions: `NotionAuth` (401), `NotionGone` (404 `object_not_found`, or 400 `validation_error` whose message mentions archived/trash), and `NotionError(status: int, code: str)` for the rest.
- All functions are sync (`httpx.Client`, 30 s timeout) and take `transport: httpx.BaseTransport | None = None` for tests:
  - `create_database(token) -> tuple[str, str, str]` returns `(database_id, data_source_id, url)`. It creates the database, then the `Board` and `Gallery` views. The board's `group_by` needs the `Status` property id. If the create response doesn't carry property ids, read them with `GET /v1/data_sources/{id}`; check which is true in Context7 (`/websites/developers_notion`, "working with views").
  - `upload_image(token, path: Path) -> str | None` returns the file upload id. It runs `POST /v1/file_uploads` (`mode: single_part`, `filename`, `content_type: image/png`) and then `POST /v1/file_uploads/{id}/send` (multipart field `file`). It returns `None` without any request when the file is missing or over `MAX_FILE = 5 * 1024 * 1024`.
  - `create_page(token, data_source_id, properties: dict, children: list[dict]) -> str` returns the page id and uses `parent: {"type": "data_source_id", "data_source_id": …}`.
  - `refresh(refresh_token) -> dict` returns the same keys as `exchange_notion` (Basic auth, JSON body).
- Pacing: at least `MIN_GAP = 0.34` s between requests (module-level monotonic timestamp, `time.sleep`). Retry 429/500/502/503/504 up to 5 attempts, sleeping `Retry-After` (default 1, max 30). After the last one, raise `NotionError`. `shortcut:` the gap is per process, not per connection; it is enough while one worker runs exports.

- [ ] **Step 1: Write the failing tests** with `MockTransport`, and `monkeypatch.setattr(client.time, "sleep", …)` recording the sleeps:
  - `test_create_database_schema_and_views`: no `parent`; the title and the six properties exactly as in Global Constraints; then two view requests with `type` `board` and `gallery`; returns the three ids.
  - `test_upload_image_two_requests_and_id`.
  - `test_upload_skips_missing_or_large_file`: `None`, zero requests.
  - `test_create_page_uses_data_source_parent`.
  - `test_requests_are_spaced`: sleeps are at least `MIN_GAP` apart under a fake clock.
  - `test_429_waits_retry_after_then_succeeds`, and `test_five_failures_raise_notion_error`.
  - `test_401_is_notion_auth`, `test_404_is_notion_gone`, `test_archived_parent_is_notion_gone`.
  - `test_refresh_sends_basic_auth_json`.
  - `test_errors_never_contain_the_token`: `str(exc)` and the caplog records lack it.
- [ ] **Step 2: Run** `uv run pytest tests/test_notion_client.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Check every request and response shape against Context7 first ("Create a database", "Create a view", "Uploading small files", "Create a page", "Refresh a token").
- [ ] **Step 4: Run** `uv run pytest tests/test_notion_client.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Notion client with pacing, retries and file upload`.

### Task 4: Card builder

**Files:**
- Create: `backend/app/notion/cards.py`
- Test: `backend/tests/test_notion_cards.py`

**Interfaces:**
- `build_card(q: dict, a: dict, share: float, subject: str, question_images: list[str], answer_images: list[str]) -> tuple[dict, list[dict]]` returns `(properties, children)` for `client.create_page`.
  - `q` and `a` are the dicts from `tools.get_task(…, False)[0]` and `tools.get_task(…, True)[0]`.
  - The image lists are file upload ids. Images that could not be uploaded are already left out, so an empty list means "use the text fallback".
- `Type` is `Multiple choice` when `q["mc_options"]` is non-empty, else `Open`.
- Text blocks are split into rich-text items of at most 2000 characters, and the top level and the toggle each carry at most 100 children. When something is cut, the last child is a paragraph `… cut, see the exam in exam-sim.`

- [ ] **Step 1: Write the failing tests:**
  - `test_properties_match_the_schema`: the title is `Exam 1 · Task 2 a)`, and the Score % fraction, Status `New`, Subject, Exam and Type are as given.
  - `test_question_crops_hide_the_text`: with question images there is no question text paragraph.
  - `test_text_fallback_without_crops`: context, question and lettered MC options appear.
  - `test_answer_lives_in_the_toggle`: no solution image, text or `Correct:` line outside the toggle.
  - `test_mc_key_shows_letters`: `mc_key=[1]` gives `Correct: B`, only when there is no answer image.
  - `test_no_solution_note`.
  - `test_long_text_split_at_2000`.
  - `test_children_capped_at_100`.
- [ ] **Step 2: Run** `uv run pytest tests/test_notion_cards.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** as a pure module: no DB, no HTTP. The block shapes are `image` (`type: file_upload`), `paragraph`, `bulleted_list_item` and `toggle`.
- [ ] **Step 4: Run** `uv run pytest tests/test_notion_cards.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: build Notion crop cards`.

### Task 5: The exporter

**Files:**
- Create: `backend/app/notion/export.py`
- Test: `backend/tests/test_notion_export.py` (reuse `seed`, `attempt` and `crop` from `tests/test_mcp_tools.py`; monkeypatch `export.client`'s functions with a fake that records calls and hands out ids)

**Interfaces:**
- Consumes: Task 3's client and its exceptions, Task 4's `build_card`, `tools.weak_refs`/`latest_shares`/`get_task`, `anki.BELOW`/`anki.LIMIT`, `NotionDatabase`, `NotionCard`, `encrypt`/`decrypt`.
- `class ExportFailed(Exception)` with `.code` in `nothing_weak`, `notion_not_connected`, `notion_auth`.
- `export_subject(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> int` returns the number of pages created.

Order inside `export_subject`:
1. Load the user's Notion `Integration`. None raises `notion_not_connected`.
2. Get `weak_refs`. None raises `nothing_weak` before any Notion call.
3. Take `pg_advisory_lock(<64-bit hash of the integration id>)` on the session's connection and release it in `finally`. This makes exports of the same connection run one at a time across workers, so there is one database and one refresh at a time.
4. Get the access token. Refresh first if `expires_at` is less than 5 minutes away.
5. Ensure the `NotionDatabase`, creating it once and committing.
6. For each ref not in `notion_cards`: upload the question crops, then the answer crops (`get_task(True)` paths minus the question paths, as in `anki.build_deck`); build the card; `create_page`; add a `NotionCard` and commit. Mark it with `shortcut:` (a crash between Notion's answer and the commit leaves one duplicate page).
- Error handling:
  - `NotionAuth` refreshes once: store the new access and refresh tokens encrypted and commit, then retry the same call. With no refresh token, or a refresh that fails with 400/401, raise `ExportFailed("notion_auth")`.
  - `NotionGone` on `create_page`: delete the stored database row and its cards, create a new database, and restart the loop once. A second `NotionGone` propagates.

- [ ] **Step 1: Write the failing tests:**
  - `test_first_export_creates_database_and_one_page_per_weak_subtask`: returns 2 for `seed`'s weak `A1a`, `A1b`; rows land in both tables; each page's children hold the uploaded ids.
  - `test_second_export_adds_only_new_cards`: lower another subtask's grade; the second call creates exactly that page.
  - `test_resume_after_crash`: the fake raises `NotionError` on the second page. The first card row is committed and the error propagates. The next call sends only the rest.
  - `test_not_connected`, and `test_nothing_weak_makes_no_notion_call`.
  - `test_deleted_database_is_recreated_once`, and `test_second_gone_propagates`.
  - `test_401_refreshes_and_stores_rotated_tokens`.
  - `test_failed_or_missing_refresh_is_notion_auth`.
  - `test_expiring_token_is_refreshed_first`.
  - `test_unuploadable_crop_falls_back_to_text`: the fake `upload_image` returns `None`.
  - `test_foreign_course_is_nothing_weak`: another user's course id finds no refs.
- [ ] **Step 2: Run** `uv run pytest tests/test_notion_export.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `export_subject` as described above.
- [ ] **Step 4: Run** `uv run pytest tests/test_notion_export.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: export weak subtasks to Notion`.

### Task 6: Endpoint and worker job

**Files:**
- Modify: `backend/app/api/subjects.py`, `backend/app/worker/main.py`
- Test: `backend/tests/test_notion_export.py` (append endpoint tests; reuse the `http`/`committed` style of `tests/test_anki.py`), `backend/tests/test_worker.py` (append)

**Interfaces:**
- `POST /api/subjects/{subject_id}/notion` (plain `def`):
  - Answers `202` with `{"jobId": "<id>"}` and `Location: /api/jobs/<id>`.
  - Answers `404` when Notion is disabled or the Subject is unknown or foreign (same check as `download_anki`).
  - Answers `409 {"detail": {"code": "notion_not_connected"}}` when the user has no Notion row, and `409 {"detail": {"code": "nothing_weak"}}` when `weak_refs` is empty.
  - An active job for the course is returned instead of a new one, including when the insert hits `uq_jobs_active_notion` (catch `IntegrityError`, roll back, select the active one).
  - The job gets `kind="notion"`, `filename="notion"`, `subject=course.name`, `course_id`, `user_id`.
- Worker: in `run_once`, `job.kind == "notion"` runs `export_subject(db, job.user_id, job.course_id)`. `ExportFailed(code)` ends the job as `failed` with that code and no retry. Other exceptions take the existing retry-then-`server` path. `upload_path(job.id).unlink(missing_ok=True)` is harmless for these jobs. `GET /api/jobs/{id}` and its `/events` already serve any kind; add no fields.

- [ ] **Step 1: Write the failing tests:**
  - `test_post_queues_a_notion_job`, and `test_post_twice_returns_the_same_job`.
  - `test_post_without_connection_is_409`, and `test_post_nothing_weak_is_409`.
  - `test_foreign_subject_is_404`, `test_disabled_is_404`, and `test_needs_login`.
  - Worker: `test_worker_runs_a_notion_job_to_done` (monkeypatched `export_subject`), `test_worker_maps_export_failed_to_error_code` (`notion_auth`, `attempts` stays 1, status `failed`), and `test_worker_retries_other_errors_then_gives_up`.
- [ ] **Step 2: Run** `uv run pytest tests/test_notion_export.py tests/test_worker.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the route and the worker branch.
- [ ] **Step 4: Run** `uv run pytest -q` and `ruff check . && ruff format .`. Expected: all PASS, lint clean.
- [ ] **Step 5: Commit** `feat: queue a Notion export from a subject`.

### Task 7: Frontend and docs

**Files:**
- Modify: `frontend/src/lib/integrations.ts`, `frontend/src/lib/api.ts` (`waitForJob`), `frontend/src/lib/subjects.ts`, `frontend/src/components/frame/SettingsPanel.vue`, `frontend/src/views/StatisticsView.vue`
- Create: `frontend/src/components/frame/NotionIntegration.vue`, `docs/notion.md`
- Test: `frontend/src/components/frame/__tests__/NotionIntegration.spec.ts`, `frontend/src/views/__tests__/StatisticsView.spec.ts` (append), `frontend/src/lib/__tests__/subjects.spec.ts` (append)

**Interfaces:**
- `integrations.ts`: rename `SlackConnection` to `Connection` (update `SlackIntegration.vue`), and `Integrations.notion: { enabled: boolean; connections: Connection[]; databaseUrl: string | null }`.
- `api.ts`: pull the SSE part of `waitForJob` out into `followJob(jobId: string): Promise<{ status: 'done' | 'failed'; error_code: string | null }>`. `waitForJob` keeps its behavior on top of it, so its tests stay green.
- `subjects.ts`: `exportToNotion(id: string): Promise<string>` resolves with the job id. On a 409, it throws `Error(<detail.code>)`, the way `downloadAnki` throws `nothing_weak`.
- `NotionIntegration.vue` copies `SlackIntegration.vue`'s shape and is hidden when `enabled` is false. It has an "Add to Notion" link to `/api/integrations/notion/connect`, the workspace name with "Disconnect", and "Open flashcards" when `databaseUrl` is set. It reads `?integration=notion` ("Notion connected.") and `notion_failed` ("Connecting Notion failed, try again.") and removes only those two values, so the Slack component keeps its own.
- Statistics, Subject layer: next to the Anki button, "Send weak questions to Notion", shown only when Notion is connected.
  - While the job runs it reads "Sending…" and is disabled.
  - On `done` it shows "Sent. Open in Notion", linking to the refreshed `databaseUrl`.
  - Errors go in a `role="alert"` element: `nothing_weak` gives "No questions scored below 60% in this subject yet."; `notion_not_connected` and `notion_auth` give "Reconnect Notion in Settings."; anything else gives "Couldn't send to Notion. Try again."

- [ ] **Step 1: Write the failing tests:**
  - Card: hidden when disabled; lists the workspace; disconnect calls `disconnectIntegration`; shows the `notion` and `notion_failed` notices; leaves `?integration=slack` in the URL.
  - `exportToNotion`: POSTs and returns the id; a 409 throws its code.
  - `followJob`: resolves on a `failed` event with its code (mock `EventSource` as the existing `waitForJob` tests do).
  - Statistics button: absent when not connected; "Sending…" while running; the "Open in Notion" link on `done`; each error code shows its text.
- [ ] **Step 2: Run** `npx vitest run`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the lib functions, the card, and the button.
- [ ] **Step 4: Write `docs/notion.md`.** Cover:
  - Creating the public integration in Notion's developer portal: redirect URI `<public base>/api/integrations/notion/callback`; capabilities read content, insert content, update content (views).
  - The env vars.
  - What a card and the three views look like.
  - Crops only, with text where a crop is missing.
  - Existing cards are never updated, and Status is not read back.
  - One workspace per user.
  - Disconnect does not revoke at Notion.
  - A deleted database is recreated on the next export.
  - Free workspaces skip crops over 5 MiB.
  Link it from `docs/roadmap.md` and the spec.
- [ ] **Step 5: Run** `npx vitest run` and `npx vue-tsc --noEmit`. Expected: PASS.
- [ ] **Step 6: Commit** `feat: Notion card in settings and an export button per subject`.

---

## After the tasks (project workflow, `CLAUDE.md`)

1. Run `/code-review high` and `/security-review`, since OAuth, tokens and an outbound API are touched. Append every unfixed finding to `docs/findings.md` and name them in the final reply.
2. Run `graphify update .`.
3. Write `docs/2026-11-25-phase-5b2-handoff.md` (done / not done / decisions).
4. The manual check with a real Notion integration stays open:
   - Connect, then export a Subject.
   - See the database with the six properties and the Board and Gallery views, with crops as gallery covers.
   - Open a card and see the `Answer` toggle.
   - Export again and see no duplicates.
   - Trash the database in Notion and export again.
   - Disconnect.
5. Record in the handoff three things that come from the docs only: the real create-database response (does it carry property ids?), the error Notion gives for a trashed database, and whether `expires_in` comes back for public integrations.
