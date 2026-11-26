# Flashcards in Notion

Send the weak questions of a Subject (latest score strictly below 60 %, at most 200, same rule as `docs/anki.md`) to a
Notion database. On the Subject's statistics page, **Send weak questions to Notion** appears once Notion is connected.
The Notion features stay hidden until `NOTION_CLIENT_ID`, `NOTION_CLIENT_SECRET` and `INTEGRATIONS_KEY` are set.

## Set up

1. Open the Developer portal (app.notion.com/developers/connections, also reached from Notion's Settings > Developer / Connections).
   In **Build** > **Connections**, click **Create new connection** and choose **OAuth** (not API token). Fill in the name, a development
   workspace and the redirect URI `<public base>/api/integrations/notion/callback` (same tunnel rules as `docs/slack.md`; open the app through
   that host so the OAuth state cookie survives). Installation scope: **Any workspace** (public), or **select 1 or more workspaces** for
   only your own; it can't be changed later. Capabilities: read content, insert content, update content (the last one creates the views).
   The **Configuration** tab then shows the OAuth client ID and client secret. No Marketplace listing or security review is needed.
2. In `backend/.env` (see `.env.example`): `NOTION_CLIENT_ID`, `NOTION_CLIENT_SECRET` (OAuth client ID and secret from the
   Configuration tab) and `INTEGRATIONS_KEY` (a Fernet key, as for Slack). Restart the backend.
3. Settings > **Notion** > Add to Notion, pick the pages to share, allow. The card then lists the workspace.

## What you get

- A database `Flashcards: exam-sim` with the properties `Question` (title), `Subject`, `Exam`, `Task`, `Type` (Multiple choice / Open),
  `Score %` and `Status` (New / Learning / Known). New cards start as `New`.
- Six views: **Table** (the default), **Board** (grouped by `Status`), **Gallery** (the first crop as cover), **By subject** and
  **By exam** (one-line tables grouped by Subject or Exam; click a group header to fold it) and **Exam × Task** (a compact board,
  exams as columns, tasks as folding rows). Notion groups at most two levels deep, so there is no Subject > Exam > Task tree.
  Views are created best effort: if Notion refuses one, it is logged and the database still works.
- One card per weak question. The title is `<exam> · <task> <label>`. The body holds the question crops, then a toggle
  `Answer` with the solution crops. Text appears only where a crop is missing (question text, options, solution text,
  `Correct: <letters>`); with neither, the card says `No solution stored.`
- Crops over 5 MiB are skipped on free workspaces (Notion's upload limit); the card falls back to text.

## Rules

- Existing cards are never updated, and nothing is read back from Notion: `Status` is yours. Exporting again adds only questions that have no card yet.
- One Notion workspace per user. Connecting the same workspace again keeps its database and cards; connecting another one replaces the first.
- Disconnect (Settings > Notion) deletes the connection and the stored card list here. It does not revoke the integration at Notion; remove it under Settings > Connections in Notion.
- If you delete the database in Notion, the next export creates a new one and sends all weak cards again.
- Notion allows about 3 requests per second, so a deck of 200 cards takes a few minutes. The button reads "Sending…" until the job ends.
- A token Notion rejects ends the job with "Reconnect Notion in Settings."

## Manual check (open)

The database is created at workspace level with `parent: {"type": "workspace", "workspace": true}` (an omitted parent is rejected
with 400 "body.parent should be defined", despite Notion's docs); it lands in the connecting user's **Private** section. Confirmed live 2026-11-25. Then: export a Subject, see the six properties and the Board and Gallery views with crops as covers,
open a card and see the `Answer` toggle, export again (no duplicates), trash the database and export again, disconnect.
