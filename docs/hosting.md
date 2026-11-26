# Hosting (stage 1)

The app runs at https://exams.ersaneke.com from a home Debian 13 VM. A Cloudflare tunnel is the only way in: no port is
published, `cloudflared` only dials out. Sign-in is invite-only (`ALLOWED_EMAILS`). You run the steps below over Tailscale SSH.

Services (`deploy/compose.prod.yaml`): `db`, `migrate`, `api`, `worker`, `web` (nginx), `cloudflared`. Networks: `backend`
(internal: db, migrate, api, worker), `edge` (internet: api, worker, web) and `tunnel` (cloudflared and web only, so
cloudflared can't reach the api).

All commands below run on the VM from `/srv/exam-sim/app`, unless they say "dev machine". Set this once per shell (`sudo` because `deploy/.env` is root-only, step 5):

```
DC="sudo docker compose -f deploy/compose.prod.yaml --env-file deploy/.env"
```

## 1. Docker and folders

1. `docker compose version` (install Docker Engine and the compose plugin first if this fails).
2. `sudo mkdir -p /srv/exam-sim/pgdata && sudo install -d -o "$USER" -g "$USER" /srv/exam-sim/app` (the app folder is yours, so the clone, `git pull` and `cp` below need no sudo).
3. `sudo install -d -o 10001 -g 10001 /srv/exam-sim/storage`. Do this before the first `up`: the backend runs as uid/gid
   10001, and a folder Docker creates itself is root-owned, so the api and worker could not write.

## 2. Clone the repo

1. On the VM: `ssh-keygen -t ed25519 -f ~/.ssh/exam-sim-deploy -N ""`.
2. GitHub > repo > Settings > Deploy keys > Add deploy key. Paste `~/.ssh/exam-sim-deploy.pub`, leave "Allow write access" off.
3. `GIT_SSH_COMMAND="ssh -i ~/.ssh/exam-sim-deploy" git clone git@github.com:ersan-eke/exam-sim.git /srv/exam-sim/app`
4. `cd /srv/exam-sim/app && git config core.sshCommand "ssh -i ~/.ssh/exam-sim-deploy"` so later `git pull` uses the key.

## 3. Cloudflare

1. Zero Trust > Networks > Tunnels > Create a tunnel > Cloudflared. Copy the token (it goes into `TUNNEL_TOKEN` in step 5).
2. In the tunnel's Public Hostname tab: hostname `exams.ersaneke.com`, service `http://web:8080`.
3. SSL/TLS: turn on "Always Use HTTPS" and set the minimum TLS version to 1.2.
4. Security: turn on the managed WAF rules and Bot Fight Mode. On the free plan Bot Fight Mode can't be skipped by WAF
   rules and may challenge non-browser clients (Claude Code on `/mcp`, Slack webhooks); if those fail through the
   tunnel, turn Bot Fight Mode off.

## 4. Production OAuth apps

1. GitHub OAuth app, callback `https://exams.ersaneke.com/api/auth/github/callback`.
2. Google OAuth client, redirect URI `https://exams.ersaneke.com/api/auth/google/callback`. Create it as a new client in the
   same Google Cloud project as the dev client: the user ids stay the same, so your existing account is found.
3. Slack and Notion are optional for now. Their URLs follow `docs/slack.md` and `docs/notion.md` with the new host.

## 5. `deploy/.env`

1. `cp deploy/.env.example deploy/.env`, then fill it in (the comments in the file say how to generate each secret).
   `ALLOWED_EMAILS` is the comma-separated list of accounts that may sign in.
2. `sudo chown root:root deploy/.env && sudo chmod 600 deploy/.env`. Compose commands then need root, which is why `$DC`
   starts with `sudo`.
3. Never commit this file (`deploy/.env` is git-ignored).

## 6. One-time data move

Skip this to start with an empty database.

1. Dev machine, from the repo root: `docker compose exec -T db pg_dump -Fc -U examsim examsim > examsim.dump`.
2. Dev machine: `scp examsim.dump <vm>:/tmp/` and `rsync -a backend/storage/ <vm>:/tmp/storage/` (`<vm>` is the Tailscale name).
3. VM: `$DC up -d db`, wait until `$DC ps` shows `db` healthy.
4. VM: `$DC exec -T db pg_restore --exit-on-error --no-owner -U examsim -d examsim < /tmp/examsim.dump`.
5. VM: `$DC exec -T db psql -U examsim -d examsim -c "DELETE FROM integrations; DELETE FROM sessions;"`.
   Stored Slack/Notion tokens are encrypted with your dev `INTEGRATIONS_KEY` and sessions belong to the dev host, so both go.
6. VM: `sudo rsync -a /tmp/storage/ /srv/exam-sim/storage/ && sudo chown -R 10001:10001 /srv/exam-sim/storage`.
7. Remove the copies: `rm -rf /tmp/examsim.dump /tmp/storage`.

Afterwards Slack and Notion are connected once more, and your first GitHub/Google login lands in the existing account
(matched by email).

## 7. First start

1. `$DC up -d --build`. The first build takes a long time: the backend image pulls the CUDA build of torch through docling
   (2.5 GB or more). This build has not been run before, so it is the proof that the image works. Read the build output.
2. `$DC ps`: `db`, `api`, `worker`, `web`, `cloudflared` are up, `migrate` has exited with code 0.
3. `$DC logs migrate api worker`: the migration ran and no write errors (a permission error means step 1.3 was skipped).
4. The worker is limited to `mem_limit: 4g` and `cpus: 2` in `deploy/compose.prod.yaml` (embeddings and PDF parsing). Adjust them to the VM.
5. Later improvement: a CPU-only torch would make the image far smaller.

## 8. Update and roll back (by hand until stage 2)

- Update: `git pull && $DC up -d --build`.
- Roll back: `git checkout <sha> && $DC up -d --build`. It works because migrations only add (rule in `CLAUDE.md`): the older
  image runs on the newer schema.

## 9. Go-live check

From a phone on mobile data (not your home Wi-Fi):

1. The site loads over HTTPS.
2. Upload while signed out: it says "Sign in to upload exams."
3. Log in with an allowed account. It works.
4. Log in with another account. You land on `/?login=denied` with "This account isn't invited. Ask the owner for access."
5. Upload an exam and the job finishes. Grade a subtask.
6. In the browser devtools the login cookie shows `Secure`.

## 10. Known gaps

Stage 1 ships without these. Order (agreed 2026-11-26): live and invite-only, then 6b demo mode with the parts of stage 2
that public demo exposure needs, then publish (the link goes on the CV), then the rest.

With 6b:

- A Cloudflare rate limit.
- A content security policy (there is none yet).
- Automatic security updates on the VM.
- Nightly backups (until then there are none: the database and `/srv/exam-sim/storage` live on this one VM).

Later:

- CI with automatic deploys (updates are by hand), and the attack (ZAP) scan.
- Proxmox isolation and firewall: only when you are at home, never remotely. The VM is otherwise not hardened further.

Always true: Cloudflare terminates TLS, so it sees plaintext traffic, including the `X-LLM-Key` header.
