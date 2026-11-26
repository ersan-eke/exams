# Phase 5a (Slack): what you have to do or check by hand

Work top to bottom. Branch `phase-5a-slack` (not merged yet). Setup reference: `docs/slack.md`.

## A. One-time setup

- [ ] 1. Install cloudflared (not installed here): `brew install cloudflared`.
- [ ] 2. Generate an `INTEGRATIONS_KEY`:
      `cd backend && uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
      and put it in `backend/.env`. Keep it safe: losing it makes stored Slack tokens unreadable (you would have to reconnect).
- [ ] 3. Start everything: `docker compose up -d db`, then in `backend/`: `uv run alembic upgrade head` (creates
      `integrations` and `webhook_events`), `uv run uvicorn main:app`, `uv run python -m app.worker.main`;
      in `frontend/`: `npm run dev`.
- [ ] 4. Start the tunnel: `cloudflared tunnel --url http://localhost:5173`. Note the `https://<random>.trycloudflare.com`
      host. A quick tunnel gets a NEW host on every restart: steps 5, 7 and 8 then need the new host again
      (or set up a named Cloudflare tunnel with a fixed host).
- [ ] 5. api.slack.com/apps > Create New App > From a manifest > pick a test workspace > paste
      `docs/slack-app-manifest.yml` with `<tunnel>` replaced by your host (4 places).
- [ ] 6. From Basic Information > App Credentials copy Client ID, Client Secret, Signing Secret into `backend/.env` as
      `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_SIGNING_SECRET`. Restart uvicorn.
- [ ] 7. Event Subscriptions page: the Request URL shows **Verified** (re-verify if you saved the manifest before
      the backend had the env vars). If not verified: open `https://<tunnel>/` in a browser; a Vite "Blocked request"
      page means `allowedHosts` doesn't cover your tunnel domain (`frontend/vite.config.ts`).
- [ ] 8. Sign-in through the tunnel: the session cookie is bound to the host, so you must sign in to exam-sim on
      `https://<tunnel>/`, not on localhost. Your GitHub/Google login app only knows
      `http://localhost:5173/api/auth/<provider>/callback`. Add `https://<tunnel>/api/auth/google/callback` to the Google
      client's redirect URIs, or for GitHub (one callback URL per OAuth app) create a second dev OAuth app for the tunnel
      host. Without this, step 9 fails at sign-in, not at Slack.

## B. The manual check (from the handoff, "Not done")

- [ ] 9. Open `https://<tunnel>/`, sign in, Settings > Slack > **Add to Slack** > allow. You come back with Settings
      open and "Slack connected."; the card lists the workspace.
      - [ ] 9a. If Slack says `redirect_uri` mismatch / bad redirect: the app built an `http://` URL. Check what Slack
            received (the `redirect_uri` parameter in the Slack consent page URL). Fix by running uvicorn with
            `--proxy-headers --forwarded-allow-ips 127.0.0.1` (Vite forwards cloudflared's `X-Forwarded-Proto`).
            Record what you found in the handoff.
      - [ ] 9b. While on the consent page URL: it contains `code_challenge=` (PKCE) and `state=`. If Slack rejects
            PKCE in the token exchange, you land on "Connecting Slack failed"; the backend log shows the OAuth error code.
- [ ] 10. In Slack: `/quiz` (no subject) lists your subjects; `/quiz nonsense` says unknown and lists them;
      `/quiz <your subject>` shows a question only you can see.
- [ ] 11. On an MC question click a wrong option ("Wrong." + solution), run `/quiz` again and click the right one
      ("Correct!"). If you have a multi-answer MC question, a correct single click says "Right, but more options are
      correct.". On a free-text question **Show solution** shows the solution.
- [ ] 12. Timing: each reply appears without Slack's "operation_timeout" / "didn't respond" error (3 s limit). Try your
      biggest exam. If it times out, note it (findings.md already has "match_solution runs before the 200").
- [ ] 13. Look at a question with a formula/figure: the "has figures not shown here" line appears. Check math with
      `<`/`>` renders literally (escaping).
- [ ] 14. Use `/quiz` from a second Slack user who has not connected: they get only the "connect" link, nothing of yours.
- [ ] 15. Settings > Slack > Disconnect: the row disappears; `/quiz` now answers with the connect link.
- [ ] 16. Optional, multi-user: connect the same workspace from a second exam-sim account (another Slack user),
      disconnect one: the other still works (shared bot token not revoked). Then uninstall the app in Slack
      (Settings > Remove app): both connections disappear (`app_uninstalled` event).
- [ ] 17. Replay test. Reconnect, then capture one events request (e.g. temporarily log raw body + the two
      `X-Slack-*` headers, or use Slack's "Retry" in Event Subscriptions). Replay it twice with `curl` to
      `https://<tunnel>/api/webhooks/slack/events` with the same headers: both 200, the second changes nothing.
      After 5 minutes, the same request: 401. Remove any temporary logging afterwards.
- [ ] 18. Log check: in the uvicorn/worker output, no `xoxb-` token, client secret or signing secret appears.
- [ ] 19. Settings UI in a browser (never looked at): the card looks right, "Add another workspace" shows when
      connected, error messages show when the backend is down, the `?integration=` query disappears from the URL,
      browser Back still works.

## C. Before merging

- [ ] 20. Optional: run `/code-review high` and `/security-review` yourself (the final whole-branch review stood in
      for them in this run).
- [ ] 21. Write the results of B into `docs/2026-11-20-phase-5a-handoff.md` (move the manual check from "Not done" to
      done, plus anything that failed), and decide whether the deviations in "Rulings" below are fine.
- [ ] 22. Rulings made without you (each is in the handoff's "Decisions already made"; reject any you disagree with):
      Disconnect revokes the bot token only for the last connection of a workspace; MCP `get_task` gained a `visual`
      key; a webhook request with a foreign `Origin` header gets 403 (Slack sends none).
- [ ] 23. Skim the 21 new entries under "Phase 5a Slack (final review)" in `docs/findings.md`; note that two of them
      must be fixed in 5b (the integrations list is not filtered by provider; connect URL built from `request.base_url`).
- [ ] 24. Clean up untracked leftovers: `.claude/settings.json.graphify-bak` and `.claude/worktrees/` (look before deleting).
- [ ] 25. Merge `phase-5a-slack` into `main` (or push + PR), then run `uv run pytest` and `npx vitest run` on `main`.

## D. Production later (not needed for the demo)

- [ ] 26. A fixed public host instead of a quick tunnel; Slack app URLs updated to it.
- [ ] 27. Back up `INTEGRATIONS_KEY`; to rotate, put the new key first (`new,old`), restart, later drop the old one.
