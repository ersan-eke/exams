# Phase 6a: hosting at exams.ersaneke.com

## Why

Run exam-sim on the user's home server so the user and a few friends can use it from anywhere, with Slack `/quiz` and the
Notion export working from day one. It's also the base for 6b (a demo mode for recruiters). The repair agent (roadmap 5c)
and the study coach come after both.

## Delivery in two stages (user, 2026-11-26)

The user needs the site live **within a few hours** for their CV, and is away from home for about a month, with access
to the VM over Tailscale only. So this phase ships in two stages. Stage 1 must still meet every anti-goal.

**Stage 1: go live today (build and run on the VM, by hand)**
- Backend: trust proxy headers, the allowlist, sign-in for writes, plus their tests.
- nginx proxy for `/api` and `/mcp`, with the basic security headers (no CSP yet).
- `deploy/compose.prod.yaml` with the container hardening from layer 4, `deploy/.env.example`, and the required-secret
  checks. Images are **built on the VM** from a checkout (`docker compose build`), with no CI and no GHCR yet. The private
  repo is cloned on the VM with a read-only deploy key.
- Cloudflare: tunnel and hostname, "Always use HTTPS", managed WAF rules, bot protection (dashboard toggles).
- Production GitHub and Google OAuth apps. The one-time data move from local, done before the first production login.
- Slack and Notion: the code is ready as is. Registering their production apps is done when time allows, and isn't
  needed for go-live.
- A short `docs/hosting.md` runbook covering what stage 1 needs.

**Stage 2: polish (next sessions)**
- Backend CI and GHCR images, the pull-deploy timer, nightly backups and a restore drill.
- CSP, the pipeline security jobs and Dependabot, VM hardening (SSH, unattended-upgrades, host firewall), the
  Cloudflare rate limit.
- Slack/Notion production apps if not done yet, the ZAP scan, `/security-review`, and the full manual check.
- **Proxmox firewall isolation only once the user is home**, never remotely. Tailscale running in the VM may need its
  own allow rule.

Recruiters who open the link in stage 1 see the sign-in screen. Trying the app needs 6b (demo mode).

## Goals

- `https://exams.ersaneke.com` serves the app, the API (`/api`), and MCP (`/mcp`) from one origin.
- GitHub and Google login, Slack (OAuth, `/quiz`, events), and Notion (OAuth, export) work against that URL.
- Only accounts on an allowlist can sign in. The allowlist holds the user and their friends.
- A push to `main` that passes CI reaches the server within minutes, with no manual steps.
- Database migrations run on every deploy. If one fails, the old version keeps serving.
- A nightly backup of the database and the crops, plus one restore that has been tried and works.

## Non-goals

- Demo mode, recruiter access, and a server-paid LLM key: that's 6b.
- Off-site backups, monitoring/alerting, a staging environment, scaling past one VM.
- Making the repo or the images public.

## Anti-goals (a failure even if it works)

- Any port on the home router opened, or the home IP exposed.
- Local dev loses its account-free mode, or its dev OAuth/Slack apps.
- A stranger can sign in, or use the server's CPU and disk (see "Anonymous use" below).
- The user's LLM key appears in any server, nginx, or tunnel log.
- GitHub can run code on the home server.

## Constraints

- Server: Proxmox host. The app runs in a Debian 13 VM (amd64) with Docker. Domain `ersaneke.com` is on Cloudflare.
- Repo `ersan-eke/exam-sim` is **private**. So the GHCR images are private, and the VM needs a read-only registry token.
- Cloudflare free plan: request bodies up to 100 MB. Slide uploads are capped at exactly 100 MB (`documents.MAX_BYTES`),
  so a deck at the cap may be refused by Cloudflare first. That's acceptable.
- Cloudflare terminates TLS, so it sees plaintext traffic, including the `X-LLM-Key` header. This is accepted for a
  small private deployment, and the docs should say so. The server still never stores or logs the key (project rule).
- One origin is required. The login cookie is `SameSite=Lax`, and `same_origin_writes` (`backend/main.py`) compares
  `Origin` with `Host`. So the frontend can't live on GitHub/Cloudflare Pages.

## Approaches considered (deploy)

1. **Pull from the VM (chosen).** CI pushes images to GHCR. A systemd timer on the VM runs `docker compose pull` + `up -d`
   every few minutes. GitHub never reaches the server, and there are no SSH keys in GitHub. The cost: deploys land a few
   minutes late, and a failed deploy shows up in the VM's journal, not in GitHub.
2. Self-hosted GitHub Actions runner on the VM: instant, visible in GitHub, but GitHub workflows run code at home.
3. GitHub Actions over SSH through Cloudflare Access: instant, but an SSH key goes into GitHub, and it's the most setup.

User's note: start with 1. **Upgrade path:** move to a push deploy (a self-hosted GitHub Actions runner, GitLab CI, or a
similar tool) once deploy feedback in the CI UI matters more than keeping the home network closed. Record it as a
`shortcut:` comment in the updater.

## Design

### Traffic

```
browser ─https─> Cloudflare ─tunnel (outbound from VM)─> cloudflared ─http─> web (nginx :8080)
                                                                         ├─ /        static Vue build
                                                                         ├─ /api/    → api:8000
                                                                         └─ /mcp     → api:8000
```

- `cloudflared` runs as a compose service with a remotely managed tunnel (`TUNNEL_TOKEN`). The public hostname
  `exams.ersaneke.com` maps to `http://web:8080`. No compose service publishes a port to the host.
- The frontend image's `nginx.conf` gains `location /api/` and `location = /mcp` proxies to `api:8000`. They keep the
  original `Host` (the origin check needs it) and pass the scheme as `https`. `client_max_body_size` covers the largest
  upload cap. Proxy buffering is off for the SSE routes (`/api/jobs/*/events`, `/api/grade`).
- Keepalives already exist: FastAPI's `EventSourceResponse` sends `: ping` every 15 s when idle, which is under
  Cloudflare's ~100 s idle cut. No code change is needed, only no buffering in nginx.
- Security headers from nginx: `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options: DENY` /
  `frame-ancestors 'none'`, HSTS, and a full CSP (see Security layers).

### Backend changes for running behind a proxy

- uvicorn runs with proxy headers trusted (`--proxy-headers`, with forwarded IPs allowed from the compose network only).
  Then `request.url_for(...)` builds `https://exams.ersaneke.com/...` for the GitHub, Google, Slack, and Notion
  callbacks, and the login cookie gets `Secure` (`auth.py`, `secure=request.url.scheme == "https"`). The Slack crop URLs
  (`slack.py`, `request.base_url`) come out right as well.
- Acceptance: through the tunnel, `GET /api/auth/github/login` redirects with
  `redirect_uri=https://exams.ersaneke.com/api/auth/github/callback`, and the login cookie carries `Secure`.

### Allowlist

- A new setting, `ALLOWED_EMAILS` (comma-separated, case-insensitive). When set, the OAuth callback refuses any identity
  whose email isn't in the list, and redirects to `/?login=denied`. That covers new and existing users, so removing
  someone from the list stops their next login. When unset (local dev), everyone may sign in, as today.
- The email check runs on the email the provider returns from `identity()`. GitHub returns `null` when the user hides
  their email, and that counts as denied. The builder decides whether to fetch the verified primary email
  (`user:email` scope) or tell such friends to sign in with Google.
- Existing sessions and MCP tokens of a removed user stay valid until they expire. That's acceptable for friends
  (`shortcut:` comment).
- The frontend shows a short message for `login=denied`.

### Anonymous use (user's decision: sign-in for anything that writes or costs server work)

Today "accounts are opt-in, so every route works without one" (`auth.optional_user`). When `ALLOWED_EMAILS` is set,
the routes that upload or cost server work need a signed-in user and answer 401 otherwise. Those are exam and slide
upload, grading, Ask, and sync. Reads, `/api/me`, the auth routes, the Slack webhooks, and `/mcp` (it has its own bearer
token) stay as they are. When the allowlist is unset (local dev), everything stays account-free, as today. The builder
lists the exact routes from `app/api/` in the plan. Any route that starts a job or calls an LLM belongs on the list. The
frontend shows sign-in instead of failing on a 401. One backend test per guarded route group, with the allowlist on and
off. 6b's demo accounts count as signed-in users.

### Moving the local data (user's decision: move it, once)

- Before go-live, copy the local database (`pg_dump`/`pg_restore`) and the local `STORAGE_DIR` crops to the server, once.
  Users, exams, attempts, grades, subjects, slides and their chunks come along.
- Production gets **new** `SECRET_KEY` and `INTEGRATIONS_KEY` (my call). `SECRET_KEY` only signs the 10-minute OAuth
  state cookie, and login sessions are hashed DB tokens, so nothing breaks. The Slack and Notion tokens were issued to the
  dev apps, and production uses its own apps (below), so they would fail anyway. The copy deletes the `integrations` rows
  and `login_sessions`, and you reconnect Slack and Notion once. That way no dev key is ever used in production.
- GitHub and Google user ids are the same across OAuth apps, so the moved `oauth_accounts` still match at the first
  production login. The builder checks this for Google on the first login, before deleting anything locally.
- The steps go in the hosting doc as a one-time runbook, not code.

### OAuth and Slack/Notion apps (my call)

Production gets its own GitHub, Google, Slack and Notion apps. A GitHub OAuth app has one callback URL, and a Slack app
has one set of request URLs, so moving the dev apps would break local dev.

### Migrations stay backward-compatible (my call)

Rollback means running an older image against the newer schema, with no `alembic downgrade`. So migrations only add
(tables, nullable columns, indexes). A drop or rename is its own later release, made once no running image reads the old
shape. The rule goes in the hosting doc and in `CLAUDE.md` Rules.

### Running it

- `deploy/compose.prod.yaml` (my call on the location) has these services: `db` (`pgvector/pgvector:pg18`), `migrate`
  (backend image, `alembic upgrade head`, one-shot), `api`, `worker`, `web` (frontend image), and `cloudflared`. `api`
  and `worker` start only after `migrate` completed successfully. `db` only after it's healthy.
- Secrets live in `deploy/.env` on the VM, never committed. Compose refuses to start without the required ones
  (`${VAR:?}`): `POSTGRES_PASSWORD`, `SECRET_KEY`, `INTEGRATIONS_KEY`, `TUNNEL_TOKEN`, and the GitHub/Google/Slack/Notion
  client ids and secrets plus `SLACK_SIGNING_SECRET`. `DEV` stays unset. A committed `deploy/.env.example` lists them.
- Storage: `STORAGE_DIR` and the Postgres data are bind mounts under `/srv/exam-sim/` (my call). That way the Proxmox VM
  backup and the nightly dump both cover them.
- Image tag: `IMAGE_TAG` in `.env`, default `latest`. Rollback means setting it to a `sha-xxxxxxx` tag and running
  `up -d`.
- `deploy/README.md` (or `docs/hosting.md`, following the `docs/slack.md` pattern) gives the one-time setup: Docker
  check, GHCR login, creating the tunnel and hostname in Cloudflare, registering the callback URLs with
  GitHub/Google/Slack/Notion, the Slack request URLs, and installing the systemd units.

### CI

- New `.github/workflows/backend.yml`: on push/PR touching `backend/**`, run `ruff check` + `ruff format --check`, then
  `uv run pytest` against a `pgvector/pgvector:pg18` service container (`examsim_test`). On push to `main` only, build
  and push `ghcr.io/ersan-eke/exam-sim/backend:{latest,sha-…}` (amd64 only).
- The frontend workflow already tests and pushes `…/frontend:{latest,sha-…}`. It stays as is, apart from what the
  nginx change needs. The builder checks that its image name matches what compose pulls.
- The pipeline smoke test needs the PDFs, which aren't in the repo, so it stays local-only.

### Deploy on the VM

- `exam-sim-update.timer`, every 5 min (my call), runs a script: `docker compose pull`, then `docker compose up -d` if
  any image changed. It logs to the journal.
- A failed `migrate` leaves `api`/`worker` on the old containers. The builder verifies this on the VM, since it's
  compose behaviour, and otherwise adjusts the script to run `migrate` first and stop on failure.
- `shortcut:` comment on the upgrade path to a push deploy (above).

### Backups

- `exam-sim-backup.timer`, nightly: `pg_dump -Fc` from the `db` container into `/srv/exam-sim/backups/`, keeping 7
  days. Crops are already on the bind mount. Proxmox's VM backup is the second copy.
- Acceptance: restore the newest dump into a scratch database and see the row counts match. Write the steps in the
  hosting doc.

### Security layers (user: "make it bulletproof")

Defense in depth: no single bug or slip should give away the VM, and a lost VM must not reach the rest of the home network.

1. **Cloudflare:** tunnel only, no open ports. Free managed WAF rules and bot protection. One rate-limit rule on
   `/api/auth/*` and the upload routes. "Always use HTTPS", minimum TLS 1.2.
2. **Home network isolation (Proxmox firewall, user's setup):** the Proxmox host also runs Home Assistant OS, and the
   Fritz!Box offers no VLANs. So isolation comes from the Proxmox firewall on the VM's network card, enforced on the host
   where a compromised VM can't switch it off:
   - Firewall on at the datacenter, node and VM-NIC levels, with `ipfilter` and the MAC filter on so the VM can't change
     its IP to dodge the rules.
   - VM outbound: internet allowed. The whole home subnet (Fritz!Box default `192.168.178.0/24`, check the real one)
     denied. That covers the Proxmox UI, Home Assistant, the Fritz!Box admin page and the other devices. The only
     exception is DNS (53) to the Fritz!Box, or use a public resolver and allow nothing local.
   - VM inbound: SSH from the user's PC only.
   - Datacenter input policy stays as is, so a rule mistake can't lock the user out of the Proxmox UI. Do this step at
     home, not over a remote link. Verify from inside the VM: `curl` to the Home Assistant and Proxmox IPs fails, and the
     internet works.
3. **VM:** host firewall (nftables/ufw) denying inbound except SSH from the LAN. SSH keys only, no root login,
   `unattended-upgrades` for security updates, `deploy/.env` mode 600 root-owned.
4. **Containers:** non-root users, `read_only` root filesystems where the image allows (tmpfs for scratch),
   `no-new-privileges`, `cap_drop: [ALL]`. The `db` sits on an internal network only `api`/`worker`/`migrate` join. The
   Docker socket is never mounted. CPU/memory limits on every service, strictest on `worker`: it parses uploaded PDFs,
   the riskiest input, so a hostile PDF hits its limits instead of the host.
5. **App:** the allowlist, sign-in for writes, `Secure` cookies, the existing origin check and upload caps. A full
   **Content-Security-Policy** from nginx (`default-src 'self'`, widened only where the built app needs it, e.g.
   `img-src data: blob:`), no longer a shortcut. Security tests in pytest: signed-out → 401 on every guarded route,
   non-allowlisted → denied, cookie flags, cross-origin write → 403, `DEV` endpoint → 404.
6. **Pipeline and dependencies:** CI runs Python and npm dependency audits, ruff's security rules (`S`), a secret scan
   over the history, and an image vulnerability scan that fails on critical findings. Dependabot does weekly updates for
   uv, npm, Docker and GitHub Actions. Actions pinned to commit SHAs, workflow `permissions` minimal. The exact tools
   are left to the builder (check current docs), with one tool per job.
7. **Proof:** `/security-review` over the diff, an OWASP ZAP baseline scan against the live site with no high
   findings, and the manual check below.

### Security review

`/security-review` over the phase diff, plus a manual check: no host ports published, the allowlist enforced, cookies
`Secure`, `DEV` unset (the dev preview endpoint returns 404), no `X-LLM-Key` in any log, Slack signature checks
passing through the tunnel.

## Left to the builder

The exact nginx directives, the uvicorn forwarded-IP value, the systemd unit details, the hosting doc layout, how GitHub
emails are fetched for the allowlist, and test shape (the allowlist gets backend tests; nginx/compose are verified live).

## Manual check (end of phase)

From a phone on mobile data: open the site, see sign-in when trying to upload while signed out, sign in with an allowed account, get denied with another one, upload an
exam and watch the job finish, grade a subtask, run `/quiz` in Slack, run a Notion export, and connect Claude Code to
`/mcp`. Push a trivial commit and see it live within 10 minutes. Restore a backup once.
