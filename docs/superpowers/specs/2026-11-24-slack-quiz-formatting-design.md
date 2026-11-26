# Slack /quiz: page crops, kept question, self-check (design)

Phase 5a follow-up, from the manual check. Size: a project (it adds a public endpoint, so it needs `/security-review`).
Replaces the first draft of this file (text + Unicode formulas), dropped by the user in favour of crops.

## Intent and why

The user ran the manual check of `/quiz` and found plain text "looks horrible in most cases": exam questions are full of
formulas, tables and figures that the text extraction mangles (OCR-style LaTeX such as `( x { 0 } , y { 0 } )`). The
pipeline already cuts every question into PNG crops, and `get_task` already returns their paths. `/quiz` should show
those, so the question looks like the exam and is correct. Also: the question must stay on screen when the solution is
shown, and the message should nudge the user toward the web app.

## Goals

- A question is shown as its page crops (context crops first, then the subtask's), under a `header` block with the
  title and a `divider`. No question text in the message when crops exist.
- "Show solution" / an MC answer keeps the question and its crops, removes the buttons, adds a `divider`, then the
  solution: verdict, correct options, solution crops (from `get_task`'s solution paths), solution text.
- A simple self-check after the solution: "I got it" / "I missed it". A click swaps the buttons for one line and a link
  to the exam in the web app. Nothing is stored.
- A link to the exam in the web app (`/exams/<examId>/view`) in every message that has crops or a solution.

## Non-goals / anti-goals

- No LLM grading of typed replies (server has no LLM key, settled in the 5a handoff). Typing a reply stays a no-op.
- No Unicode formula converter, no LaTeX handling: dropped with the plain-text approach.
- No `markdown` block, no image upload to Slack (`files:write`), no new Slack scopes, no manifest change.
- Anti-goal: a way to browse exam images without the owner's link. The crop URL must not become a general file server.

## Constraints

- Slack `image` blocks need a public HTTPS `image_url` (max 3000 characters, png/jpg/gif). The existing tunnel is the
  public host; Slack's servers fetch the image.
- Slack's 3 s limit on the command/interaction answer is unchanged. The response only carries URLs, nothing is
  rendered or uploaded in the request.
- Block limits: header 150 chars, 50 blocks per message; crops observed so far are small (194 files, max 125 KB,
  about 957 px wide).
- `client.respond` posts with `replace_original: true`, which is why the question vanished.
- If Slack cannot download an image it may reject the whole message (shows as `invalid_command_response`). Not verified.
- The web app, not Slack, shows what the user needs beyond this; exam PDFs and crops are never committed (copyright).

## Approaches

1. **Signed crop URL on our own backend, `image` blocks.** Chosen. A new unauthenticated route
   `GET /api/slack/crops/<token>` serves exactly one crop. Reuses the existing Fernet key (`INTEGRATIONS_KEY`).
2. Upload crops to Slack (`files.upload`, scope `files:write`). Rejected: new scope and reinstall, an extra Slack
   round trip per crop inside the 3 s window, copies of exam images stored at Slack.
3. Keep text, add Unicode formulas. Rejected by the user.

Checked against Slack's docs (Context7 and the pages themselves) on 2026-11-24:
- `image_url` is "a publicly hosted image", "an HTTPS URL with no restrictions", max 3000 characters, png/jpg/jpeg/gif.
  A signed, unguessable URL on our host fits that.
- Slack's own answer for *private* images is `slack_file` (upload, then reference by file ID,
  <https://slack.com/blog/developers/uploading-private-images-blockkit>). It needs the `files:write` scope (re-install),
  the three-call external upload per crop, an async reply (the 3 s limit), and leaves copies of exam images at Slack.
  The pages are silent on whether a file uploaded by the app is visible in an *ephemeral* reply to the user.
- Not documented anywhere I could read: what Slack does when it cannot download an `image_url` (does the whole message
  fail?), byte/pixel limits, redirect handling. So the first plan task is a throwaway check in the real workspace
  (one crop URL in a real `/quiz` reply); `slack_file` becomes the fallback only if that check fails.

## Design

- **Token.** `crypto.encrypt("<exam_id>/<layer>/<name>")` (Fernet, same key and rotation as stored Slack tokens).
  `crypto.decrypt` gets an optional `ttl` so Fernet's built-in timestamp enforces expiry. TTL: 24 h (my call: Slack may
  re-fetch when an ephemeral message is reopened; shorten if Slack proves to cache at post time).
- **Route** (in `app/api/slack.py`, same router): decrypt, split, check `layer in {"blank", "ink"}`, check the name
  with the existing `CROP_NAME` regex, build the path from `exam_dir(exam_id)`, apply the same `resolve().is_relative_to`
  guard `_crops` uses, return `FileResponse` (`image/png`, `Cache-Control: private, max-age=86400`). Any failure (bad
  token, expired, bad name, missing file) is a plain 404. No DB access, no session, no Slack signature (Slack's image
  fetch carries none); the secret in the URL is the capability.
- **Producing URLs.** `quiz.question` and `quiz.answer` get the request base URL (already passed to the connect link).
  `blocks` turns each crop path into an `image` block (`alt_text` = exam, task, label). Path to layer and exam id
  comes from the path's parent directories, so `tools.get_task` is not changed for that.
- **Context crops.** `get_task` returns only the subtask's crops, but `Context` blocks have their own regions
  (`pipeline/models.py:55`). The Slack path needs them first. Builder: add them to what `get_task` returns (extra paths)
  or add a small helper next to `_crops`; keep MCP's output unchanged unless the extra crops belong there too.
- **Message layout.** Question: `header` (exam, task, label, points) + `divider` + context crops + subtask crops +
  + `actions` (option buttons or Show solution).
  Answer: the same blocks minus `actions`, then `divider`, verdict/solution blocks, then the self-check `actions`.
  Self-check click: same blocks minus the self-check buttons plus one `context` block with the line and the link.
  New `action_id`s `selfcheck_yes` / `selfcheck_no`, handled in the existing `interactions` route. Slack sends the
  message's current `message.blocks` in the interaction payload; the builder may reuse them for the self-check click
  instead of rebuilding from the DB (decide while building, keeping the 3 s limit in mind).
- **Questions without crops** (files missing): fall back to escaped question text as today (my call; the rare case
  should not produce an empty message). `visual` notice goes away (crops show the figures).
- **Link.** `{base}/exams/{exam_id}/view`; `exam_id` is the part before `/` in the task ref.

## Security

- The route is the one new public surface: it serves only files already inside one exam's crops directory, only
  names matching `CROP_NAME`, only for a token our key produced and under 24 h old. Fernet tokens are authenticated,
  so they cannot be forged or edited. A leaked URL exposes one crop for at most the TTL.
- Rotating `INTEGRATIONS_KEY` keeps working (MultiFernet) for both stored tokens and crop URLs.
- No exam text or key goes into logs. Run `/security-review`.

## Left to the builder

- Do MC option buttons still need the option text in the message? The crops show the question; whether they include the
  option lines depends on how the pipeline cut the regions. Check with a real MC question (button text is capped at
  75 characters). If the crop has them, the buttons can stay as letters only.
- Whether `/exams/:examId/view` can jump to the task; if so, deep link, else link to the exam.
- Whether Slack accepts the images through the tunnel at all (test in the real workspace before relying on it), and how
  it reports a failed fetch.
- Tests: token round trip, expiry, tampered token, bad name, missing file, path escape; block builders (header,
  dividers, no buttons in the answer, image count); route 404 for everything invalid.

## Known risks

- The `invalid_command_response` errors seen in the manual check are not explained by this change. The backend answered
  40/40 test requests under 0.3 s; the likely cause is the quick tunnel. Check uvicorn's log for failing
  `POST /api/webhooks/slack/commands`. If Slack cannot fetch images, new failures of the same kind are possible.
- Quick-tunnel hosts change on restart; old messages' image links then point at a dead host.
