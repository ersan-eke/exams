# Quiz yourself from Slack

Connect a Slack workspace to your exam-sim account, then type `/quiz <subject>` in any channel or DM. exam-sim answers
privately (ephemeral) with one of your own questions. The Slack features stay hidden until the three Slack env vars and
`INTEGRATIONS_KEY` are set.

## Set up

1. Slack needs a public HTTPS URL. Start a tunnel to the Vite dev server, which proxies `/api`:

   ```sh
   cloudflared tunnel --url http://localhost:5173
   ```

2. api.slack.com/apps > Create New App > From a manifest. Paste `docs/slack-app-manifest.yml` with `<tunnel>` replaced
   by the tunnel host. Slack checks the events URL on save, so the backend must already run with the env vars below.
3. In `backend/.env` (see `.env.example`): `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_SIGNING_SECRET` (Basic
   Information > App Credentials) and `INTEGRATIONS_KEY`
   (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`; comma-separated, newest
   first, to rotate). Restart the backend.
4. Open the app through the tunnel URL, sign in, Settings > **Slack** > Connect. The card then lists the workspace.
   Open the app through the tunnel host, not `localhost`, so the OAuth state cookie survives the round trip.
   Vite only serves hosts it knows: `frontend/vite.config.ts` allows `.trycloudflare.com`; for another tunnel domain add it
   to `server.allowedHosts`, or every request gets 403.

## What `/quiz` does

- `/quiz <subject>` picks a random subtask with text among the 10 weakest of the whole subject (latest score, lowest first; never-attempted count as 0.5, ties are random). Multiple choice shows one button per option;
  any other question shows **Show solution**. A click answers right/wrong where it can, and shows the solution.
- Without a subject, or with an unknown one, it lists your subjects.
- Before you connect, `/quiz` answers with the connect link.
- The question shows its page crops as images (context crops first); without crop files it shows the text.
  After an answer or **Show solution** the question stays, the solution follows: verdict and correct option(s), then the solution crops, or the solution text when there are no crops. An "Open in exam-sim" link ends the message.
- `/quiz` acknowledges at once (empty 200) and posts the question to the command's `response_url` in the background: Slack checks an inline reply,
  including every image URL, inside 3 seconds. If Slack rejects that post (e.g. `invalid_blocks`), the status and the first 300 characters of the reply are in the server log (`slack respond failed`).

It does not grade free text (no LLM: the server holds no LLM key, and Slack's 3 second limit rules out a model call),
and answers in Slack are not recorded as attempts. Use the web app or MCP (`docs/mcp.md`) for that.

## Disconnect

Settings > Slack > Disconnect deletes the connection. The bot token is revoked at Slack only when no other exam-sim
connection uses that workspace. Uninstalling the app in Slack removes every connection of that workspace.

## Page crops in messages

- Slack fetches image URLs itself, so they must be public `https`. Behind a tunnel run uvicorn with `--proxy-headers --forwarded-allow-ips 127.0.0.1`, or the URLs come out as `http://`.
- Crop URLs (`/api/slack/crops/<token>`) expire after 24 h; old messages show broken images after that, and also when the tunnel host changes.
