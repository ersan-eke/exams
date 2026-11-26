# Phase 6a stage 1 handoff: go live, invite-only

Spec `docs/superpowers/specs/2026-11-26-phase-6a-hosting-design.md` (Stage 1), plan
`docs/superpowers/plans/2026-11-26-phase-6a-stage1-go-live.md`, runbook `docs/hosting.md`.

## Done

- `ALLOWED_EMAILS` allowlist (`core/config.py`). Unset = open (local dev, as before). Set to a value that parses empty
  (`","`) = refuse to start.
- The OAuth callback denies an identity that isn't listed, before any user or session is created → `/?login=denied`.
  GitHub uses only the verified primary address from `user/emails` (scope `user:email`). Google needs `email_verified`.
  A GitHub emails error → `/?login=failed`.
- When invite-only: `POST /api/exams` and `POST /api/grade` need a signed-in user (`invited_user`, 401 `sign_in`). A
  middleware in `main.py` refuses signed-out `POST /api/exams` and `/api/documents` before the multipart body is read.
  FastAPI parses forms before dependencies, so without it a stranger's 100 MB upload hit the disk before the 401.
- Frontend: the "isn't invited" text, plus "Sign in to upload exams." and "Sign in to grade answers." on a 401.
- `frontend/nginx.conf` proxies `/api/` and `= /mcp` to `api:8000`, resolved at request time.
  - Headers: X-Forwarded-For comes from `CF-Connecting-IP` only. Security headers are set and access_log is off.
  - Buffering is off, for SSE and MCP.
- `deploy/compose.prod.yaml` runs db, migrate, api, worker, web and cloudflared.
  - No published ports. Every container has cap_drop ALL and no-new-privileges, and the backend runs as uid 10001.
  - Networks: `backend` is internal (db). `edge` gives internet to api, worker and web. `tunnel` connects cloudflared
    and web only.
  - The api runs with `--no-access-log`.
- `docs/hosting.md`: runbook, one-time data move, go-live check, known gaps.
- `CLAUDE.md`: the add-only migration rule. `docs/roadmap.md`: the agreed order.
- Fixed type errors in two frontend tests that were already broken before this branch and broke `npm run build`.
- Tests: backend 644, frontend 394, `npm run build` OK. Two sync tests flaked once on a host clock jump (recorded).

## Not done

- **The user runs `docs/hosting.md` on the VM and does the go-live check.** The real backend image build has never run
  (the local proof used images without torch). The first `docker compose build` on the VM is its proof.
- Next, per the roadmap: 6b demo mode, together with the Cloudflare rate limit, CSP, VM automatic security updates and
  nightly backups. Then publish. Later: 5c, 5d, CI and auto-deploy, the ZAP scan, and the Proxmox firewall (once home).
- Open findings: `docs/findings.md` → "Hosting stage 1".

## Decisions already made

- Uploads and grading need a signed-in user only when the allowlist is set. Ask, slides, chats and sync already needed
  one.
- uvicorn runs with `--forwarded-allow-ips "*"`, not the spec's "compose network only", because there's no fixed
  subnet. It holds because no port is published, cloudflared can reach only `web`, and nginx overwrites XFF.
- A malformed GitHub emails body counts as "no email" (denied under an allowlist), not `login=failed`.
- cloudflared sits on its own `tunnel` network, so it can't reach the api directly.
- No uvicorn access log in production, because query strings carry OAuth codes and Slack crop tokens.
- The backend image keeps the CUDA torch for now. CPU-only torch comes with the stage 2 GHCR images.
- Images are built on the VM from a checkout made with a read-only deploy key. There's no CI deploy yet.
