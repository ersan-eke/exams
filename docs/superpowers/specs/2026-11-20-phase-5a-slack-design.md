# Phase 5a: integrations + Slack (design)

Status: written by the assistant from the roadmap and one answer from the user ("it is a demo, but I'd use it myself, and it should feel like a real
industry-standard app"). **Approved 2026-11-21** including the calls marked *(my call)*; the bot token is kept encrypted. Roadmap: `docs/roadmap.md` Phase 5, split into 5a (this),
5b Notion export, 5c pipeline repair agent, 5d study coach.

## Intent

A signed-in student connects their Slack workspace to exam-sim ("Add to Slack"), then types `/quiz <subject>` in Slack and gets a question from
their own exams, answers it with buttons, and sees the solution. It is also the portfolio piece for webhooks: a signed, replay-protected,
idempotent Slack receiver, and encrypted per-user integration tokens.

## Goals

- Multi-user, multi-workspace: any exam-sim user can connect any workspace their Slack account may install apps into. No single-workspace env hack.
- `integrations` table holds the Slack bot token Fernet-encrypted (key rotation via comma-separated keys); the token never leaves the server and is
  never logged or returned by an API.
- One Slack webhook receiver with three endpoints (`events`, `commands`, `interactions`), each behind the same signature check:
  HMAC-SHA256 over `v0:<timestamp>:<raw body>`, `hmac.compare_digest`, 5-minute replay window.
- Events API: `url_verification` answered; `event_id` stored in `webhook_events` (`ON CONFLICT DO NOTHING`), so Slack's retries run once;
  `app_uninstalled` and `tokens_revoked` delete the integration rows of that workspace.
- `/quiz <subject>`: a random subtask with text, shown ephemerally (only the asker sees it). MC subtasks get one button per option; others get
  "Show solution". Clicking an MC option says right/wrong and shows the solution; clicking reveal shows the solution.
- The install flow carries an OAuth `state` (and PKCE) bound to the signed-in browser session; a callback with a missing or mismatched `state`, or
  without a signed-in user, links nothing.
- Button values carry only `subtask ref|option index` and are never trusted: every interaction re-resolves the Slack user to an exam-sim user and
  looks the subtask up among that user's own exams.
- Settings shows the connection (workspace name, Disconnect). Disconnect revokes the token at Slack (best effort) and deletes the row.
- Everything Slack-related is hidden/404 unless `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_SIGNING_SECRET` and `INTEGRATIONS_KEY` are set
  (same pattern as the login providers).

## Non-goals

- Notion (5b), repair agent (5c), study coach and scheduled DMs (5d). The `provider` column allows `notion` already; nothing else is built for it.
- Grading free-text answers in Slack. The server holds no LLM key (CLAUDE.md rule: the key is sent per request, never stored), and Slack requests
  carry none. *(my call)* Free-text subtasks only offer "Show solution"; the student compares themselves.
- Recording Slack answers as attempts (`record_practice`). *(my call)* Left out so a mis-click in Slack cannot change grades; 5d can add it.
- Crop images in Slack: Slack cannot fetch our session-protected crops. Text only; the message says when a question has figures the text misses.
- Slack Marketplace distribution, token rotation (Slack bot tokens do not expire by default; `expires_at` stays NULL).

## Anti-goals

- A signature check that can be skipped by a missing header, or that compares against a re-encoded body.
- One user reaching another user's questions through a Slack identity or a tampered button value.
- A plaintext token in the DB, a log line, or a response.

## Constraints

- Backend rules from `CLAUDE.md`: sync `Session`, endpoints without `await` are `def`; `async def` touches the session only in `run_in_threadpool`.
  `shortcut:` comments for simplifications. `uv add` for deps (`cryptography`, already pulled in by authlib, is declared explicitly).
- Slack needs a public HTTPS URL: dev uses a tunnel (documented), the manifest is committed.
- The same-origin middleware in `main.py` only blocks requests that carry an `Origin` header; Slack sends none.
- Slack must get a 200 within 3 seconds: no LLM, no slow work in the handlers; posting to `response_url` runs after the response.

## Approaches

1. **Per-user "Add to Slack" OAuth, identity = installing user's Slack id** *(chosen)*. Each exam-sim user runs the install flow; the row maps
   `(workspace, slack user id)` to the exam-sim user and stores that workspace's bot token. Matches how real Slack apps link accounts; an unlinked
   Slack user gets an ephemeral "connect your account" link.
2. One workspace configured by env vars (bot token in `.env`) with a manual user mapping: least code, but a demo of a hack, not an app.
3. Slack "Sign in with Slack" first, then install: needs a second OAuth flow and user-token scopes for no extra capability.

## Decisions left to the builder

Block Kit layout details, wording of messages, the settings card's markup, where exactly `?integration=` is read in the frontend.
