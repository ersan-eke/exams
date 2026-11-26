# Backend foundation: status and what's left

Written 2026-10-28, after building Postgres, async upload jobs and login. Nothing here is committed yet.

## The original goal

1. **SQL / data model**: move from IndexedDB-only to Postgres with users, courses, exams, tasks, subtasks,
   regions, attempts, answers, grades, documents and chunks. Alembic for migrations.
2. **Auth**: (a) GitHub/Google login for optional accounts and sync; (b) OAuth into third-party apps
   (Notion, Slack).
3. **REST + webhooks**: async uploads (`POST /exams` returns a `job_id`, processing runs in the
   background, completion is pushed to the client); inbound Slack Events API with an HMAC check,
   idempotency and retries.

## Status

| Part | Done | Not done |
|---|---|---|
| 1. Data model | Postgres in compose, SQLAlchemy models, Alembic (3 migrations). Tables: users, courses, exams, tasks, subtasks, attempts, answers, subtask_times, grades, jobs, oauth_accounts, sessions. The worker writes exams to the database. | `documents` and `chunks` tables are missing. `regions` is a JSONB column on purpose, not a table. The frontend still keeps everything in IndexedDB; nothing writes attempts, answers, grades or courses to Postgres. |
| 2. Auth | (a) GitHub/Google login, server-side sessions, ownership checks, cross-site protection, account popover in the UI. | No real login has been done yet (needs registered OAuth apps). Sync isn't built. (b) Notion/Slack OAuth isn't built. |
| 3. REST + webhooks | Async upload: `202` + `job_id`, Postgres job queue, worker, SSE progress, retries, cleanup. | Inbound Slack webhook isn't built. No outbound webhook, on purpose: a browser has no public URL to receive one, so SSE replaces it. |

## How to run it

- Database: `docker compose up -d db` (root `compose.yaml`, Postgres 18).
- From `backend/`: `uv run alembic upgrade head`, then `uv run uvicorn main:app` and
  `uv run python -m app.worker.main` (`uv sync` installs everything from `pyproject.toml`/`uv.lock`).
- Frontend: `npm run dev` in `frontend/`. It proxies `/api` with `changeOrigin: false`, which is
  required: the backend builds OAuth callback URLs from the Host header and checks Origin against it.
- Tests: `uv run pytest` in `backend/` (uses its own `examsim_test` database, rebuilt by
  replaying the migrations; skipped if Postgres isn't running) and `npx vitest run` in `frontend/`.
- Real login: copy `backend/.env.example` to `backend/.env` and fill in the OAuth app credentials.
  Callback URL: `http://localhost:5173/api/auth/{github|google}/callback`.

## Decisions already made (don't revisit)

- **Columns vs JSONB:** columns for anything joined, filtered or summed (points, times, grades); JSONB
  for what is always read and written whole (pipeline geometry, pen strokes).
- **IDs:** UUIDs created by the client, so offline records keep their ID.
- **Job queue:** the Postgres `jobs` table is the queue, claimed with `FOR UPDATE SKIP LOCKED`. No Redis.
- **Progress:** pushed to the browser over SSE (`fastapi.sse`).
- **Sessions:** a row in Postgres behind an `HttpOnly`, `SameSite=Lax` cookie, not JWT. Only a SHA-256
  hash of the cookie is stored.
- **Account linking:** by the provider's account ID, never by email.
- **Privacy:** accounts are opt-in. Without one, the server only processes uploads: the PDF is deleted
  after processing and anonymous exams after 24h.

## Where things live

- `backend/app/db/models.py`: all tables.
- `backend/app/db/exams.py`: `ExamStructure` to rows and back.
- `backend/app/db/session.py`: engine, `SessionLocal`, `get_db`.
- `backend/app/core/config.py`: env settings (loads `backend/.env`).
- `backend/app/core/storage.py`: file paths for uploads and crops.
- `backend/app/api/routes.py`: upload, jobs, SSE, exam fetch.
- `backend/app/api/auth.py`: OAuth login, sessions, `optional_user`.
- `backend/app/worker/main.py`: the worker (claim, process, retry, cleanup).
- `backend/main.py`: middleware (OAuth state cookie, Origin check).
- `frontend/src/lib/api.ts`: `uploadExam` (POST, wait on SSE, fetch the exam).
- `frontend/src/stores/account.ts`: the signed-in user.

## Left for the step that needs it

### 1. Data model

- **`documents` table:** source PDF metadata with `UNIQUE(user_id, sha256)`, the hash computed on the
  server. Add it with server-side duplicate detection once users exist. The client already
  fingerprints PDFs in `stores/library.ts`; don't trust that hash.
- **`chunks` table:** `document_id`, page, text, `embedding vector(n)` via pgvector, in its own
  migration when RAG starts. This conflicts with deleting the PDF after processing
  (`worker/main.py`); decide whether to keep the extracted text instead.
- **Writing attempts to rows:** answers, grades and times, the counterpart of `app/db/exams.py`. Mapping:
  - `Attempt.snapshot` becomes `answers.version='main'`, and the final answers become `'over'`.
  - `ViewState` is not synced (per-device UI state).
  - `StoredExam.solutionFor` is replaced by `attempts.solution_exam_id`.
- **Courses:** the `courses` table exists but nothing uses it; the subject is still guessed by
  `subjectOf` on the client.

### 2. Auth

- **Sync (the most important next step):**
  - First fix this: a signed-in upload is saved on the server, but the client stores the exam under
    its own `crypto.randomUUID()` and never records the server's exam ID, and there is no "list my
    exams" endpoint. So signed-in uploads can't be found again. The client must keep the server's
    exam ID, or send its own ID along with the upload.
  - Then add `GET /api/exams` (the user's exams), `PUT /api/attempts/{id}` (full replace) and
    `GET /api/sync?since=<updated_at>`. `updated_at` on exams and attempts is meant as the sync cursor.
  - Conflicts: last write wins per record.
  - Add a `current_user` dependency that returns 401 for these routes. Only `optional_user` exists.
- **(b) Notion/Slack OAuth:** an `integrations` table with user_id, provider, external workspace ID,
  access/refresh tokens encrypted with Fernet (key from env), scopes and expiry. Same authorization
  code flow as login, but the tokens are kept and refreshed. Build it together with the feature that
  uses it.
- **Small items:**
  - Show the `/?login=failed` redirect (cancelled consent) in the UI.
  - Handle the first-login race: two simultaneous first logins with the same account cause an
    `IntegrityError` and a 500. Catch it and retry the lookup in `start_session`.
  - Optionally refresh the user's name and email on later logins.

### 3. Webhooks and jobs

- **Inbound Slack:** `POST /api/webhooks/slack`.
  - Answer `url_verification` by echoing the challenge.
  - Check the HMAC-SHA256 over `v0:{X-Slack-Request-Timestamp}:{raw body}` (`await request.body()`,
    before parsing) with `hmac.compare_digest`, and reject timestamps older than 5 minutes.
  - Store `event_id` under `UNIQUE` with `ON CONFLICT DO NOTHING` (Slack retries, up to 3 times).
  - Queue it as a job and return 200 within 3s. `jobs` needs a `kind` column for that.
  - The Origin check in `main.py` doesn't block this, because Slack sends no Origin header.
- **Pushing job updates instantly:** replace the 1s polling (`job_events` in `routes.py` and the loop in
  `worker/main.py`) with Postgres LISTEN/NOTIFY when there are many clients.
- **Heartbeat:** add one inside long stages, once OCR or docling makes a stage take longer than `STALE`
  (15 min) in `worker/main.py`. Note that the current pipeline takes about 1.4s for a 12-page PDF;
  docling isn't used in it (`ml_services/layout_analyzer.py` is a stub).
- **Smaller items:**
  - Upload size limit. PDFs now sit on disk until the worker processes them.
  - A timeout for the event stream in `waitForJob` (`frontend/src/lib/api.ts`). If the server stays
    unreachable, the browser keeps reconnecting and the upload never finishes.
  - Progress display in `PdfDropZone`. The stream already sends `stage`.
- **Deployment:**
  - Add `/api` to `frontend/nginx.conf` with `proxy_set_header Host $host` and unbuffered streaming
    (`proxy_buffering off`) for SSE.
  - Write a real `backend/Dockerfile` (it's still a placeholder), and add `api` and `worker` services
    to the root `compose.yaml`. `frontend/compose.yaml` is still separate.
  - Set `SECRET_KEY` and the OAuth credentials in production.

## Other known gaps

- **Privacy wording:** "Stays on this device" isn't strictly true for anonymous uploads: the crops stay
  on the server for up to 24h.
- **Git state:** nothing from this work is committed. The git index has odd staged renames from before
  this work (e.g. `.env -> backend/app/api/routes.py`); look at them before committing.
- **Shortcuts:** search the code for `shortcut:` to find each deliberate simplification and when to
  upgrade it.
