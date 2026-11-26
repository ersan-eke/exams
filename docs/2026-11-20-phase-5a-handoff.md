# Phase 5a Slack: status and what's left

Written 2026-11-21. Spec: `docs/superpowers/specs/2026-11-20-phase-5a-slack-design.md`. Plan:
`docs/superpowers/plans/2026-11-20-phase-5a-slack.md`. Setup: `docs/slack.md`, manifest `docs/slack-app-manifest.yml`.

## Done

- `integrations` and `webhook_events` tables; tokens encrypted with MultiFernet (`INTEGRATIONS_KEY`, `core/crypto.py`).
- Signature check (`slack/signature.py`): HMAC-SHA256 over `v0:ts:body`, `compare_digest`, timestamp within ±300 s.
- `POST /api/webhooks/slack/{events,commands,interactions}`. Events: `url_verification`, `event_id` dedup
  (`ON CONFLICT DO NOTHING`), `app_uninstalled` and `tokens_revoked` delete the connections. The worker deletes
  webhook events older than 7 days.
- OAuth: `GET /api/integrations/slack/connect` and `/callback` (PKCE, Authlib), `GET /api/integrations`,
  `DELETE /api/integrations/{id}`.
- `/quiz <subject>`: ephemeral question with MC buttons or Show solution; Slack mrkdwn escaped; a notice when the
  question has figures; unlinked users get the connect link.
- Settings card (`SlackIntegration.vue`) with the `?integration=slack|failed` notice.

## Not done

- Manual check with a real Slack app and tunnel (needs you): (1) save the manifest, the events URL verification passes;
  (2) connect from Settings, the card shows the workspace; (3) `/quiz <subject>` shows a question, a click gives
  right/wrong plus the solution; (4) disconnect removes the row and `/quiz` then answers with the connect link;
  (5) replay one captured events request twice with `curl` (same signature): the second is a no-op; with a timestamp
  older than 5 minutes: 401; (6) the `redirect_uri` Slack receives is `https://` (X-Forwarded-Proto through
  Vite to uvicorn's proxy headers), otherwise the OAuth round trip fails.
- Notion export, repair agent, study coach: 5b to 5d.
- Unfixed review findings are in `docs/findings.md`.

## Decisions already made (don't revisit)

- **Signature rules:** every webhook route verifies the signature first; wrong or stale (±300 s) gives 401. Retried events
  dedupe on `event_id`.
- **One row per Slack identity:** unique on (workspace, Slack user). A second exam-sim account cannot claim a connection
  that another account owns.
- **No LLM in Slack:** the server holds no key, and Slack expects an answer in 3 s. Grading stays in the app and MCP.
- **Ephemeral, text only:** replies are visible to the asker only; no crops.
- **Disconnect and revoke:** bot tokens are shared per workspace, so Disconnect revokes at Slack only when it deletes the
  last exam-sim connection of that workspace; otherwise it only deletes the row.
- **Figure notice:** the message says when a question has visual regions. For that, MCP `get_task` gained a `visual` key.
- **Foreign `Origin`:** the same-origin middleware answers 403 on the webhooks; Slack sends no `Origin`.
