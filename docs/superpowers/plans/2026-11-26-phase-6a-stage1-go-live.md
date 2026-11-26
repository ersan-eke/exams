# Phase 6a Stage 1: go live Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve exam-sim at `https://exams.ersaneke.com` today, from the home VM through a Cloudflare tunnel. Sign-in is
invite-only, and signed-out visitors can't use the server's CPU or disk.

**Architecture:** One origin. cloudflared → nginx (frontend image) → `/api` and `/mcp` proxied to the FastAPI `api`
container. Images are built on the VM from a checkout with `deploy/compose.prod.yaml`. The backend trusts the proxy's
forwarded headers. An email allowlist (`ALLOWED_EMAILS`) gates login and, when set, the two routes that are open to
signed-out users today (`POST /api/exams`, `POST /api/grade`).

**Tech Stack:** FastAPI + Authlib, Vue 3 + vitest, nginx-unprivileged, Docker Compose, cloudflared, pgvector/pg18.

**Spec:** `docs/superpowers/specs/2026-11-26-phase-6a-hosting-design.md` (section "Delivery in two stages", Stage 1 only).

## Before you start

- `main` has uncommitted Notion work (`backend/app/notion/*`, its tests, `docs/notion.md`, `docs/findings.md`, the
  handoff). Ask the user to commit or stash it before you branch. Never commit it yourself without asking.
- Work on branch `phase-6a-stage1`.

## Global Constraints

- The allowlist is unset in local dev, and then everything behaves exactly as today: account-free, every login accepted.
- The user's LLM key (`X-LLM-Key`) is never stored or logged. Neither nginx nor the backend logs headers.
- No compose service publishes a host port. Only cloudflared talks to the outside, and only outbound.
- Production secrets live in `deploy/.env` on the VM only. `deploy/.env` is git-ignored, and `deploy/.env.example` is
  committed.
- Migrations only add (tables, nullable columns, indexes), never drop or rename, so rollback to an older image works.
- Backend: `ruff check . && ruff format .` before committing. Tests: `uv run pytest` (backend), `npx vitest run`
  (frontend).
- Deliberate simplifications carry a `shortcut:` comment saying when to upgrade.

## Review Focus

1. A GitHub user with a hidden email, or an unverified email address, must not pass the allowlist. → Task 1 tests
   `primary_email` and the Google `email_verified` check.
2. A signed-out visitor sending `POST /api/grade` without a key gets 401 `sign_in`, not 400 `no_key`. The sign-in check
   has to run first. → Task 1 test.
3. Allowlist matching ignores case and surrounding spaces (`" Me@X.com "` matches `me@x.com`). → Task 1 test.
4. A spoofed `X-Forwarded-For` from the client must not change the address the grade rate limiter sees. nginx sends only
   `CF-Connecting-IP`. → Task 3 config plus the Task 4 live check.
5. Signed-out users who hit a guarded route see "sign in" text, not "Couldn't reach the server". → Task 2 tests.

---

### Task 1: Backend allowlist and sign-in for costly routes

**Files:**
- Modify: `backend/app/core/config.py` (add `ALLOWED_EMAILS`)
- Modify: `backend/app/api/auth.py` (GitHub scope + email lookup, Google `email_verified`, `allowed`, `invited_user`,
  callback denial)
- Modify: `backend/app/api/routes.py:51-78` (upload uses `invited_user`), `:178` (grade gets `invited_user`)
- Modify: `backend/.env.example` (document `ALLOWED_EMAILS`)
- Test: `backend/tests/test_auth.py`, `backend/tests/test_api.py` (or wherever upload/grade are tested now; follow the
  existing file)

**Interfaces:**
- Produces: `config.ALLOWED_EMAILS: frozenset[str]` (lower-cased, stripped, empty when unset).
- Produces: `auth.primary_email(emails: list[dict]) -> str | None`: the address with `primary` and `verified` both true,
  else `None`.
- Produces: `auth.allowed(email: str | None) -> bool`: `True` when `ALLOWED_EMAILS` is empty. Otherwise true only for an
  email in the set (case-insensitive).
- Produces: `auth.invited_user(user: User | None = Depends(optional_user)) -> User | None`: raises
  `HTTPException(401, detail={"code": "sign_in"})` when `ALLOWED_EMAILS` is set and `user is None`.
- Produces: the callback redirects to `/?login=denied` (303) for an identity that isn't allowed, and creates no
  user or session.
- Tests monkeypatch `app.core.config.ALLOWED_EMAILS`. So `auth.py` reads it as `config.ALLOWED_EMAILS` at call time, not
  through a `from … import`.

- [ ] **Step 1: Write the failing tests**

```python
def test_primary_email_needs_primary_and_verified():
    assert primary_email([{"email": "a@x.com", "primary": True, "verified": False},
                          {"email": "b@x.com", "primary": False, "verified": True}]) is None
    assert primary_email([{"email": "c@x.com", "primary": True, "verified": True}]) == "c@x.com"

def test_allowed_is_open_without_list(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset())
    assert allowed(None) and allowed("anyone@x.com")

def test_allowed_matches_case_insensitively(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset({"me@x.com"}))
    assert allowed("Me@X.com") and not allowed("other@x.com") and not allowed(None)

def test_callback_denies_unlisted_email(db, monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset({"me@x.com"}))
    # sign in via the existing signed_in()/fake_identity helper with email "stranger@x.com"
    # assert: response 303 to "/?login=denied", no "session" cookie, no User row with that email

def test_callback_accepts_listed_email(db, monkeypatch):  # same flow, email "ME@x.com": session cookie set

def test_upload_needs_sign_in_when_invite_only(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset({"me@x.com"}))
    r = TestClient(app).post("/api/exams", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "sign_in"

def test_grade_needs_sign_in_before_key_check(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset({"me@x.com"}))
    r = TestClient(app).post("/api/grade", json={})  # no X-LLM-Key
    assert r.status_code == 401 and r.json()["detail"]["code"] == "sign_in"

def test_signed_out_upload_still_works_without_list(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset())
    # POST /api/exams with b"%PDF-1.4" → 202, as today
```

`signed_in()` in `test_auth.py` takes no email today. Extend it with an `email: str | None = None` parameter, and leave
its existing callers unchanged.

- [ ] **Step 2: Run them and see them fail**

Run: `cd backend && uv run pytest tests/test_auth.py tests/test_api.py -k "primary_email or allowed or denies or accepts or sign_in or without_list" -v`
Expected: FAIL (ImportError for `primary_email` / `allowed`, then 202/400 where 401 is expected).

- [ ] **Step 3: Implement**

- `config.py`: `ALLOWED_EMAILS = frozenset(e.strip().lower() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip())`,
  with a one-line comment: unset means open (local dev); production compose requires it.
- `auth.py` GitHub settings: `client_kwargs={"scope": "user:email", **PKCE}`, and update the comment. In `identity()`
  for GitHub: `GET user/emails` with the same token, and use `primary_email(...)` as the email. Drop `info.get("email")`,
  because a public profile email is no proof of ownership here.
- `identity()` for Google: return `info.get("email") if info.get("email_verified") else None`.
- `callback()`: after `identity()`, if `not allowed(email)`, then `log.info("%s sign-in denied", provider)` (never the
  email) and `RedirectResponse("/?login=denied", status_code=303)`.
- `invited_user` as in Interfaces. In `upload_exam`, swap `optional_user` → `invited_user`. On `grade`, add
  `dependencies=[Depends(invited_user)]` to the decorator. If the test shows the key check still runs first, put it as
  the first parameter dependency instead.
- `shortcut:` comment on `invited_user`: existing sessions and MCP tokens of someone removed from the list stay valid
  until they expire. Revoke them on removal once the list changes often.
- `.env.example`: `ALLOWED_EMAILS=` with a comment: comma-separated, empty means anyone can sign in (local dev only),
  and production refuses to start without it.

- [ ] **Step 4: Run the whole backend suite**

Run: `cd backend && uv run pytest -q && ruff check . && ruff format --check .`
Expected: all pass, including the existing auth tests (they run with the allowlist empty).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/app/api/auth.py backend/app/api/routes.py backend/.env.example backend/tests/
git commit -m "feat: invite-only sign-in and sign-in for upload and grading when an allowlist is set"
```

---

### Task 2: Frontend messages for denied sign-in and "sign in first"

**Files:**
- Modify: `frontend/src/stores/account.ts` (read `?login=denied`)
- Modify: `frontend/src/components/frame/AppFrame.vue:36` (show the denied text)
- Modify: `frontend/src/lib/api.ts` (`UploadErrorCode` gets `'sign_in'`, 401 → `UploadError('sign_in')`)
- Modify: `frontend/src/lib/grading.ts:314-360` (`errorMessages.sign_in`, 401 fallback → `'sign_in'`)
- Test: `frontend/src/stores/__tests__/account.spec.ts`, `frontend/src/lib/__tests__/api.spec.ts`,
  `frontend/src/lib/__tests__/grading.spec.ts`

**Interfaces:**
- Consumes: the backend answers 401 `{"detail": {"code": "sign_in"}}` and redirects to `/?login=denied` (Task 1).
- Produces: `useAccountStore().loginDenied: Ref<boolean>`, next to `loginFailed`.

- [ ] **Step 1: Write the failing tests**
  - account: after `history.replaceState(null, '', '/?login=denied')` and `load()`, `loginDenied` is `true`,
    `loginFailed` is `false`, and the `login` param is gone from the URL.
  - api: `uploadExam` with a mocked 401 response rejects with `UploadError` code `'sign_in'`, and
    `uploadErrorMessage` of it is `'Sign in to upload exams.'`.
  - grading: a 401 grade response with body `{"detail":{"code":"sign_in"}}` throws `GradeError('sign_in')`, and its
    message is `'Sign in to grade answers.'`.

- [ ] **Step 2: Run them and see them fail**

Run: `cd frontend && npx vitest run src/stores/__tests__/account.spec.ts src/lib/__tests__/api.spec.ts src/lib/__tests__/grading.spec.ts`
Expected: FAIL on the three new tests.

- [ ] **Step 3: Implement**
  - Wire the three changes as in Files. Exact copy:
    - AppFrame (in the same `<span class="err">` slot as "Sign-in failed"):
      `This account isn't invited. Ask the owner for access.`
    - upload: `Sign in to upload exams.`
    - grading: `Sign in to grade answers.`
  - In the grade fallback chain, `res.status === 401` maps to `'sign_in'`.

- [ ] **Step 4: Run the whole frontend suite**

Run: `cd frontend && npx vitest run && npm run lint --if-present`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: show invite-only denial and sign-in-first messages"
```

---

### Task 3: nginx proxies `/api` and `/mcp`, with security headers

**Files:**
- Modify: `frontend/nginx.conf`

**Interfaces:**
- Produces: inside the compose network, `web:8080` serves the SPA and proxies `/api/` and `= /mcp` to `api:8000`.
  `api` is resolved at request time through Docker's DNS (`resolver 127.0.0.11 valid=10s;` plus a variable in
  `proxy_pass`), so the image also starts without an `api` host.
- Headers sent upstream: `Host $host`, `X-Forwarded-Proto` (the incoming `X-Forwarded-Proto`, else `$scheme`, through a
  `map`), and `X-Forwarded-For $http_cf_connecting_ip` (Cloudflare's client IP only, never the client-supplied chain).
  Task 4's uvicorn trusts these.

- [ ] **Step 1: Edit `nginx.conf`**
  - `client_max_body_size 100m;` (the largest upload cap, slides).
  - In the proxy locations: `proxy_http_version 1.1;`, `proxy_buffering off;`, `proxy_read_timeout 300s;`.
    Buffering off keeps the SSE routes (`/api/jobs/*/events`, `/api/grade`) and MCP streaming working.
  - At `server` level, `always`: `X-Content-Type-Options nosniff`, `Referrer-Policy strict-origin-when-cross-origin`,
    `X-Frame-Options DENY`, `Strict-Transport-Security "max-age=31536000"`. The existing asset locations that set their
    own `add_header` must repeat these, because nginx doesn't inherit `add_header` into a location that has its own.
  - `shortcut:` comment: no Content-Security-Policy yet; stage 2 adds it.
  - `access_log` stays off.
- [ ] **Step 2: Check the config**

Run: `docker run --rm -v "$PWD/frontend/nginx.conf:/etc/nginx/nginx.conf:ro" nginxinc/nginx-unprivileged:alpine3.22 nginx -t -c /etc/nginx/nginx.conf`
Expected: `syntax is ok` / `test is successful`.

- [ ] **Step 3: Commit**

```bash
git add frontend/nginx.conf
git commit -m "feat: nginx proxies /api and /mcp with security headers"
```

---

### Task 4: Production compose, non-root backend image, proxy headers

**Files:**
- Modify: `backend/Dockerfile` (non-root user `app`, uid/gid 10001; storage dir owned by it)
- Create: `deploy/compose.prod.yaml`
- Create: `deploy/.env.example`
- Modify: `.gitignore` (add `deploy/.env`)

**Interfaces:**
- Consumes: the Task 3 nginx and its forwarded headers. The Task 1 `ALLOWED_EMAILS`.
- Produces: services `db`, `migrate`, `api`, `worker`, `web`, `cloudflared`, used by the Task 5 runbook.
  Bind mounts: `/srv/exam-sim/pgdata` (db) and `/srv/exam-sim/storage` (api+worker, `STORAGE_DIR=/data/storage`).

- [ ] **Step 1: Write `compose.prod.yaml`**
  - `db`: `pgvector/pgvector:pg18`, `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?}`, healthcheck as in the root
    `compose.yaml`, volume `/srv/exam-sim/pgdata:/var/lib/postgresql`, network `backend` only.
  - `migrate`: build `../backend`, image `exam-sim-backend`, `command: alembic upgrade head`, `restart: "no"`,
    `depends_on: db: condition: service_healthy`.
  - `api`: same image. `command: uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips "*"`.
    Comment: safe because no port is published and nginx overwrites `X-Forwarded-For` with `CF-Connecting-IP`.
    Networks `backend` + `edge`. `depends_on: migrate: condition: service_completed_successfully`.
  - `worker`: same image, `command: python -m app.worker.main`, networks `backend` + `edge`, same `depends_on`, `mem_limit: 4g`,
    `cpus: 2`. The values are my call. The builder adjusts them to the VM's size and writes them in the runbook.
  - `web`: build `../frontend`, network `edge`, `depends_on: [api]`.
  - `cloudflared`: `cloudflare/cloudflared:<pin a current version>`, `command: tunnel --no-autoupdate run`,
    `TUNNEL_TOKEN: ${TUNNEL_TOKEN:?}`, network `edge`.
  - All services: `restart: unless-stopped` (except `migrate`), `security_opt: [no-new-privileges:true]`,
    `cap_drop: [ALL]`. The `db` image's entrypoint needs `CHOWN`, `SETUID`, `SETGID`, `FOWNER` and `DAC_OVERRIDE` back
    (`cap_add`). Verify in Step 4 and keep the smallest set that starts. No `ports:` anywhere.
  - Two networks:
    - `backend` (`internal: true`): `db`, `migrate`, `api`, `worker`.
    - `edge` (normal, has internet): `api`, `worker` (LLM providers, Slack, Notion), `web`, `cloudflared`.

    `db` is on no network with internet access.
  - Shared env for api/worker/migrate (YAML anchor):
    - `DATABASE_URL: postgresql+psycopg://examsim:${POSTGRES_PASSWORD:?}@db:5432/examsim`
    - `STORAGE_DIR: /data/storage`
    - `SECRET_KEY: ${SECRET_KEY:?}`, `INTEGRATIONS_KEY: ${INTEGRATIONS_KEY:?}`, `ALLOWED_EMAILS: ${ALLOWED_EMAILS:?}`
    - the GitHub/Google/Slack/Notion ids and secrets plus `SLACK_SIGNING_SECRET` as `${VAR:-}` (optional)
  - Comment at the top: stage 1 builds on the VM. Stage 2 switches `build:` to GHCR `image:` tags and adds the update
    timer. `shortcut:` the pull deploy can later become a push deploy (self-hosted GitHub Actions runner, GitLab CI or
    similar) when deploy feedback in CI matters more than a closed home network.
- [ ] **Step 2: `deploy/.env.example`**: every variable above with a one-line comment and how to generate it.
  - `POSTGRES_PASSWORD`: `openssl rand -hex 24`. Hex, so the URL needs no escaping.
  - `SECRET_KEY`: the `secrets.token_urlsafe` one-liner from `backend/.env.example`.
  - `INTEGRATIONS_KEY`: the Fernet one-liner from `backend/.env.example`.
  - `TUNNEL_TOKEN`: comes from the Cloudflare dashboard.
  - `ALLOWED_EMAILS`: required.
- [ ] **Step 3: Dockerfile** gets `RUN useradd --uid 10001 --user-group --no-create-home app && mkdir -p /data/storage && chown app:app /data/storage`
  and `USER app` after the code is copied. Keep the default `CMD`.
- [ ] **Step 4: Local proof (on the dev machine)**

Run:
```bash
cd deploy && cp .env.example .env.local-test   # fill with throwaway values, ALLOWED_EMAILS=me@example.com, TUNNEL_TOKEN=x
sudo mkdir -p /srv/exam-sim/{pgdata,storage} && sudo chown 10001:10001 /srv/exam-sim/storage  # or point the mounts at a temp dir via an override file
docker compose -f compose.prod.yaml --env-file .env.local-test up -d --build db migrate api worker web
docker compose -f compose.prod.yaml --env-file .env.local-test exec web \
  wget -S -O /dev/null --max-redirect=0 --header 'Host: exams.ersaneke.com' --header 'X-Forwarded-Proto: https' \
  http://localhost:8080/api/auth/github/login 2>&1 | grep -i location
docker compose -f compose.prod.yaml --env-file .env.local-test exec web wget -qO- http://localhost:8080/api/me
docker compose -f compose.prod.yaml --env-file .env.local-test down
```
Expected:
- `migrate` exits 0, and `api`/`worker` are up.
- `Location:` contains `redirect_uri=https%3A%2F%2Fexams.ersaneke.com%2Fapi%2Fauth%2Fgithub%2Fcallback`. GitHub needs a
  client id in the env, otherwise the route 404s.
- `/api/me` returns JSON.
- `docker compose ... config` fails with a clear message when `SECRET_KEY` is removed from the env file.
- `docker compose ps` shows no published ports.

The macOS dev machine may not allow `/srv`. Use a `compose.override.yaml` that's ignored by git, or `--project-directory`
with temp-dir mounts. Never change the prod paths for this.

- [ ] **Step 5: Commit**

```bash
git add deploy/compose.prod.yaml deploy/.env.example backend/Dockerfile .gitignore
git commit -m "feat: production compose with tunnel, hardened containers and non-root backend image"
```

---

### Task 5: Stage 1 runbook and the migration rule

**Files:**
- Create: `docs/hosting.md`
- Modify: `CLAUDE.md` (Run: pointer to `docs/hosting.md`. Rules: migrations only add.)
- Modify: `docs/roadmap.md` (status line: Phase 6a stage 1, next 6a stage 2 / 6b, then 5c)

**Interfaces:**
- Consumes: the Task 4 service names, paths and env vars.

- [ ] **Step 1: Write `docs/hosting.md`.** These sections, in order, as numbered commands (the user runs them over
  Tailscale SSH into the Debian VM):
  1. Check Docker (`docker compose version`). Create `/srv/exam-sim/{pgdata,storage}` and chown `storage` to 10001.
  2. Clone the private repo with a read-only deploy key (GitHub → repo → Settings → Deploy keys) into
     `/srv/exam-sim/app`.
  3. Cloudflare: Zero Trust → Networks → Tunnels → create one (cloudflared). Copy the token. Public hostname
     `exams.ersaneke.com` → `http://web:8080`. SSL/TLS: "Always Use HTTPS", minimum TLS 1.2. Security: managed WAF
     rules and Bot Fight Mode on.
  4. Production OAuth apps:
     - GitHub OAuth app, callback `https://exams.ersaneke.com/api/auth/github/callback`.
     - Google OAuth client, redirect URI `https://exams.ersaneke.com/api/auth/google/callback`. A new client in the same
       Google Cloud project as the dev client keeps the user ids the same.
     - Slack/Notion are optional for now. Their URLs follow `docs/slack.md` and `docs/notion.md` with the new host.
  5. `deploy/.env`: copy from `.env.example`, fill it, `chmod 600`, root-owned.
  6. One-time data move:
     - `pg_dump -Fc` the local DB, from the dev machine's `db` container.
     - Copy the dump and `backend/storage/` over Tailscale (`scp`/`rsync`).
     - On the VM: `up -d db`, `pg_restore --no-owner -d examsim` into the empty DB, then
       `psql -c "DELETE FROM integrations; DELETE FROM login_sessions;"`.
     - `rsync` the crops into `/srv/exam-sim/storage`, then `chown -R 10001:10001`.
     - Note: Slack/Notion get reconnected once, and the first GitHub/Google login lands in the existing account.
  7. `docker compose -f deploy/compose.prod.yaml --env-file deploy/.env up -d --build`. Check with `docker compose ps`
     and `logs migrate`.
  8. Update by hand until stage 2: `git pull && docker compose … up -d --build`. Rollback: `git checkout <sha>` + the
     same command. This works because migrations only add.
  9. Go-live check from a phone on mobile data:
     - The site loads over HTTPS.
     - Upload while signed out → "Sign in to upload exams."
     - An allowed login works. Another account → "isn't invited".
     - Upload an exam and the job finishes. Grade a subtask.
     - The login cookie shows `Secure` in the browser devtools.
  10. Known gaps until stage 2 (list): no CSP, no CI/backups/auto-update, the VM not hardened, no Proxmox isolation
     (only at home, never remotely), Cloudflare sees plaintext traffic including `X-LLM-Key`.
- [ ] **Step 2: Edit `CLAUDE.md` and `roadmap.md`** as in Files. The rule line: "Migrations only add (tables, nullable
  columns, indexes); a drop or rename is a later release once no deployed image reads the old shape (rollback runs an
  older image on the newer schema)."
- [ ] **Step 3: Commit**

```bash
git add docs/hosting.md CLAUDE.md docs/roadmap.md
git commit -m "docs: stage 1 hosting runbook and the add-only migration rule"
```

---

## After the tasks

`/code-review high` and `/security-review` over the branch. Record findings in `docs/findings.md`. The user runs
`docs/hosting.md` on the VM and does the go-live check. Write a handoff doc `docs/2026-11-26-phase-6a-stage1-handoff.md`.
