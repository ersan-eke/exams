# Open findings

Small review findings that were deliberately not fixed when a ticket was implemented. Not a backlog of tickets: pick from here
when touching the same area, or promote an entry to a GitHub issue when it bites.

**After every ticket's `/code-review`:** append each finding you did not fix as an entry below (what, where, why left, when it
matters). When you fix one later, delete the entry in the same commit. Findings the ticket asked for, or that were wrong, are not recorded.

Entry format: `- **summary** (area, from #ticket): failure scenario in one line. *Left because:* … *Fix when:* …`

## Open

### Grading material (#13)
- **A twice-imported paper still matches as material** (`rag/material.py`, from #20): the copy has another id, so it is not excluded and its answers can reach the grading prompt. *Left because:* #20 scoped duplicates out; upload dedup (#18) already blocks identical files. *Fix when:* it bites; match by content hash or title.
- **Old client sends `exam_id`** (`grading/models.py`, from #20): a stale SPA bundle after deploy sends the renamed field; if extras are ignored, the graded exam is not excluded from its material. *Left because:* single deploy, reload fixes it. *Fix when:* clients outlive deploys.
- **Solution-exam test fixture is a copy of the question** (`tests/test_rag_ask.py`, from #20): "Solution 2024" reuses the exam's own question text, so it does not model differently keyed solution tasks. *Left because:* the test still proves the exclusion; a differently keyed solution is extra realism. *Fix when:* touching that test.
- **Test asserts fixture labels** (`tests/test_rag_ask.py`, from #13): `"[chapter3, p. 2]"` and `"Endterm 2024"` tie the test to the fixture and the label format. *Left because:* cosmetic and test-only. *Fix when:* either changes.

### Typing help (#14)
- **Vocabulary rebuilt and re-tokenised on every hints request** (`rag/hints.py`, from #14): one `tokens()` call per word plus per hyphen part, on every debounced keystroke. *Left because:* fine for a few thousand pages (see the `shortcut:` comment). *Fix when:* typing lags; tokenise the joined string once or cache the `Vocab` per Subject.
- **`_vocab` test helper duplicates the loop in `vocabulary()`** (`tests/test_rag_slides.py`, from #14): drops the length/digit filters, so it can drift. *Fix when:* touching `vocabulary()`; move the add-title step into `Vocab.add(text)`.
- **A hyphen part shares its spelling counter with standalone words** (`rag/hints.py`, from #14): "TCP-Handshke" could be corrected to just "Handshake"; "TCP" vs "tcp" picks the more frequent. *Left because:* rare and cosmetic.

### Chat send (#15)
- **`busy` is one flag for all Chats** (`ChatPane.vue`, from #15): while A sends and B is open, B's form stays disabled; B's own send could be re-enabled by A finishing. Pre-existing. *Fix when:* per-Chat busy state is needed.
- **A failed list refresh after a successful send shows "Couldn't start the Chat"** (`ChatPane.vue` `submit`, from #15): the message was saved, the student may resend and duplicate it. Pre-existing. *Fix when:* seen in practice; move `refresh()` out of the try.
- **Unexplained single failure in a full `npx vitest run`** (frontend, seen while implementing #15): not reproduced in three reruns, failing test not captured. *Left because:* it did not reproduce in three reruns, so there is nothing to debug. *Fix when:* it shows up again; note the test name here.

### Viewer (#16)
- **A `page` or `terms` change during an in-flight load restarts the download** (`PdfViewer.vue` `draw`, from #16): a slow PDF can keep restarting while the parent updates props. Pre-existing. *Fix when:* seen in practice; track the pending URL and only restart when it changes.
- **`pdf!` dereferenced twice after the load block** (`PdfViewer.vue`, from #16): safe only while nothing awaits between the check and the use. *Fix when:* an `await` is added there; capture `const doc = pdf` once.

### Deck titles and filenames (#17)
- **Inline NUL-strip copies remain** (`api/subjects.py`, `api/chats.py`, `api/sync.py` `_put_exam`, from #21): they can drift from `core/text.clean`. *Left because:* each has its own empty/length rule (`sync.py`: `""` clears the course, `None` keeps it, while `clean` turns `""` into `None`). *Fix when:* touching any of them; give `clean` an explicit empty-string result or keep the copy.
- **The 255-char filename cap can cut off `.pdf`** (`api/documents.py` upload, from #17): the cap is invented (columns are unbounded text); the title fallback then has no suffix to strip. *Fix when:* long filenames show up; cap the stem and keep the extension.
- **`upload_raw` test helper is hand-built multipart** (`tests/test_documents.py`, from #17): fixed boundary `X`, unescaped form values. *Fix when:* a test needs other form values or PDF bytes containing `--X`.

### Duplicate uploads (#18)
- **A multi-file drop overwrites its own notices** (`AddMaterial.vue` `add`, from #18): a later success clears `error`/`existing`, so a duplicate or failed file earlier in the batch goes unnoticed; the message also doesn't name the file. Pre-existing for errors. *Fix when:* batches of mixed files matter; collect one notice per file.
- **Same file in the same Subject gives no notice** (`AddMaterial.vue`, from #18): the 200 resolves like a new upload, nothing says it was already there. Ticket keeps this ("as today"). *Fix when:* students ask; return a flag or compare the Deck's `page_count`.
- **A duplicate answer can name a Deck the worker is still reading** (`api/documents.py` `_duplicate`, from #18): `job_id: null` makes the client resolve at once, also for a plain re-upload during the first job. *Fix when:* the list shows half-read Decks; return the running job's id.
- **Only `IntegrityError` cleans up the stored upload** (`api/documents.py` upload, from #18): any other failure in flush/commit (DB disconnect) leaves `uploads/<job>.pdf` behind. Pre-existing. *Fix when:* touching upload; remove the file in a `finally` unless committed.

### Phase 4b review follow-ups (#11)
- **`clean` is a generic name** (`core/text.py`, from the 2026-11-20 review): it is called for Subjects, titles and filenames. *Left because:* a rename touches many call sites right before a merge. *Fix when:* touching it; `clean_text`.
- **`*args` hides the purpose of two helpers** (`api/sync.py` `_once_more_on_conflict(put, db, *args)`, `db/session.py` `read_then_release(db, read, *args)`, from the review): call sites don't show what the arguments are. *Left because:* each has two callers. *Fix when:* a third caller appears; take `functools.partial` or a typed callable.
- **`exclude_exams` is an open list capped at 10** (`grading/models.py`, `rag/material.py`, from #20/the review): it is always the graded exam plus its solution exam. *Left because:* the client sends what it has and an old client still works. *Fix when:* the contract changes again; use two named fields.
- **`Vocab(Counter)` carries the spelling map** (`rag/hints.py`, from the review): `hints()` reaches into `vocab.spelling`. *Left because:* works and is tested. *Fix when:* touching `vocabulary()`; see the `_vocab` helper entry, put the add-step into `Vocab.add(text)` too.
- **"First seen" for hint spellings follows an unordered query** (`rag/hints.py` `vocabulary()`, from the 2026-11-20 review): the `DeckPage` select has no `ORDER BY`, so a spelling tie goes to whatever row order Postgres returns. *Left because:* stable in practice and the tie is cosmetic. *Fix when:* a tie flips between requests; order by `DeckPage.document_id, DeckPage.page`.
- **Worker title test has no input that needs cleaning** (`tests/test_worker.py` `test_exam_title_is_cleaned_and_capped`, from the review): `Job.filename` cannot hold NUL, so only the cap is pinned; removing the strip would still pass. *Left because:* the route strips NUL first, so the worker never sees it. *Fix when:* touching the worker title; add a filename with a trailing space.
- **`_once_more_on_conflict` retries only once, and no test shows a new warning from our own code survives the `filterwarnings` entries** (accepted in the review): three or more simultaneous first PUTs can still 500 (documented `shortcut:`). *Left because:* accepted. *Fix when:* seen in practice.

### Phase 5a Slack (final review)
- **Empty entry in `INTEGRATIONS_KEY` breaks every call** (`core/crypto.py`, from T1): `"a,"` gives `Fernet("")`, a ValueError on each encrypt/decrypt, and `SLACK_ENABLED` doesn't validate the key. *Left because:* a config typo that fails loudly. *Fix when:* touching crypto; filter on `k.strip()`.
- **No test that `decrypt` raises `InvalidToken` on a wrong key** (`tests/`, from T1). *Fix when:* touching crypto.
- **Redundant `finally: db.rollback()`** (`tests/test_slack_events.py` `test_webhook_event_conflict_is_ignored`, from T1). *Fix when:* touching that test.
- **Non-canonical timestamps are accepted** (`slack/signature`, from T2): `" 1"`, `"+1"`, `"1_0"` and non-ASCII digits pass because `sign()` runs over `str(int(ts))`; no bypass, the signed value is what Slack sent. *Fix when:* touching the verifier; sign the raw header and require `isdigit()` ASCII.
- **`/api/integrations` list is not filtered by `provider == "slack"`** (`api/integrations.py`, from T3): any other provider's rows would show as Slack workspaces. *Fix when:* 5b adds a provider (must fix then).
- **Same-user simultaneous callbacks report failed though the row exists** (`api/integrations.py` `_save`, from T3). *Left because:* the connection is saved either way. *Fix when:* seen.
- **Forged-state test doesn't assert no row was created** (`tests/test_integrations.py`, from T3). *Fix when:* touching it.
- **Concurrent disconnects in one workspace can both skip the revoke** (`api/integrations.py` `disconnect`, from T3): a valid bot token is left unrevoked; fail-safe. *Fix when:* seen; lock the workspace's rows.
- **A connect racing the last-row disconnect can leave the new row with a revoked token** (`api/integrations.py`, from T3). *Fix when:* seen; reconnect fixes it.
- **Missing `event_id`/`team_id` become `""`, a shared dedup key; a non-string `challenge` is echoed** (`api/slack.py` events, from T4). *Left because:* only signed input. *Fix when:* touching events; reject with 400.
- **Non-object-event test doesn't assert no `WebhookEvent` row was written** (`tests/test_slack_events.py`, from T4). *Fix when:* touching it.
- **`respond()` posts to any `response_url`** (`slack/client.py`, from T5): no `https://hooks.slack.com/` allowlist; input is signed. *Fix when:* before public deployment; check the prefix.
- **`int(idx)` accepts `-1`, `" 1"`, `"1_0"`** (`api/slack.py`, from T5): they end as "Wrong.". *Fix when:* touching it; require `idx.isdecimal()`.
- **`test_quiz_lists_buttons` depends on random picks** (`tests/test_slack_quiz.py`, from T5): fails with p = 2^-10. *Fix when:* it flakes; monkeypatch `random.choice`.
- **`match_solution` runs before the 200** (`slack/quiz.py`, from T5): cost on large exams is unmeasured against Slack's 3 s limit. *Fix when:* a big exam times out.
- **The 2900-char cut runs on escaped text** (`slack/blocks.py`, from T5): it can split an entity such as `&amp;`. *Fix when:* seen; cut before escaping.
- **A long task context can push the subtask text out of the cut, with no "..." marker** (`slack/blocks.py`, from T5). *Fix when:* seen; cut each part separately.
- **No test for AppFrame auto-opening settings on `?integration=`** (`AppFrame.vue`, from T6). *Fix when:* touching AppFrame.
- **Signed-out redirect keeps `?integration=` and shows no notice** (frontend, from T6). *Fix when:* seen.
- **The notice is never cleared** (`SlackIntegration.vue`, from T6): it stays after Disconnect. *Fix when:* seen; clear it in `run`.
- **Connect link base URL is `http://` unless proxy headers are trusted** (`api/slack.py` `base` from `request.base_url`, from the final review). *Left because:* dev goes through Vite. *Fix when:* deploying; run uvicorn with `--proxy-headers` and a forwarded-allow list.

## Older findings (before this doc)

Collected 2026-11-15 from earlier sessions, handoff docs, issues and `shortcut:` comments. Status was checked by grep against
`phase-4-rag` (e6c9989), not by running anything: treat "probably open" as a lead, not a fact. Already fixed ones are left out.

### Tracked as GitHub issues (not repeated here)
#19 third-party test warnings (the #20 solution-exam part is fixed; duplicate imports are listed above).

### Ask, Chat and slide search (#3 to #10, #12)
- **Typing help runs the exam-task search and discards it** (`ChatPane.vue` `previewSearch`, #7): wasted request per pause.
- **Hints is a GET, so partial drafts reach access logs** (`/api/search/hints`, #7).
- **`hints.py` imports the private `_match` from `slides.py`** (#7). *Fix when:* touching either.
- **Did-you-mean flags only the first questionable word and can pick a close slide-body word** (`hints.py`, #7).
- **AI Outline can overwrite a fresh read if the Deck is re-read during the LLM call** (`documents.py` `outline_ai`, #9); no tests for its `not_read` response or rate limit.
- **Key-header and error-status mapping duplicated** between `chats.ask_turn` and the outline endpoint (#9, #12).
- **No `lock_timeout` for many quick messages to one Chat** (#12); **`chats.py:127` rewrites the whole message list per message** (`shortcut:`).
- **Ask review leftovers** (#6, #8, #10): overlay builds of one slide share a label; image-only page sent with empty text; asking twice without a new message re-asks; dev preview uses a plain modal instead of `RequestPreview`; past exam tasks can't be pinned; a failure after Chat creation leaves a half-set-up Chat; back/forward between `?subject=` values on the Ask page isn't handled; only the first PDF bookmark per page is kept; study page doesn't check sign-in; a scanned Deck never gets an Outline; backfill re-embeds every existing Deck once.
- **Search tuning** (#3): BM25 `B=0.5` fitted to 11 eval cases, eval prints counts but enforces no target, idle-worker backfill tested only by direct call; `MIN_SIM=0.3` tuned on two decks; `search.py:18` HNSW filter-after-scan limit (`shortcut:`).
- **Viewer highlight limits** (#4, `shortcut:`): highlights the question's words not the matched terms, skips 1-2 letter words ("IP"), any viewer failure says "wasn't found", no re-render on resize, GradingRow links pass no terms; range requests on the file endpoint unchecked.
- **RAG/Ask gaps**: no streaming, no OCR for scanned slides, exercise not paired with its solution, first grading request loads the embedding model (1-2 s).
- **"Deck" rename in the UI** (Ask redesign handoff item 6): "not yet applied", wording unverified.

### Sync (Phase 3a, `docs/2026-11-03-sync-handoff.md`) — probably open
- Grades are `Numeric(6,2)`: 0.333 becomes 0.33, 10000+ gives a 500 (`db/models.py:44`).
- A refused localStorage write (full or blocked) leaves a handed-in attempt or edited exam out of the push outbox, so it stays on this device until edited again (`lib/db.ts` `saveDirty`, `shortcut:`). The local save itself is unaffected; the "reload inside the 500 ms delay" loss from the earlier note did not reproduce (#22, covered by `attempt.spec.ts`).
- **A failed `putAttempt` in `flush()` is never retried** (`stores/attempt.ts`, from #22): `flush()` clears the save timer first and callers use `void flush()`, so a rejected IndexedDB put (quota, closed DB) loses that edit and is an unhandled rejection. *Fix when:* seen in practice; catch in `flush`, re-arm the timer.
- **Page-hide saving is only tested with fake-indexeddb** (`attempt.spec.ts`, from #22): jsdom can't show whether a real IndexedDB write started in `pagehide` survives teardown. *Fix when:* an edit goes missing after a real reload; check in a browser.
- **Attempt-store listeners on `document`/`window` are never removed** (`stores/attempt.ts`, from #22): every store created in tests (or by HMR) keeps its handlers, so a `pagehide` event also runs older stores' flushes. *Fix when:* tests become order-dependent; register once or remove on dispose.
- A permanently broken server exam stops the sync cursor; a pulled exam that turns `hasInk` true doesn't fetch crops.
- Same PDF on two devices before syncing becomes two exams (`sync.py:82`); a second account on one browser gets the first's local data pushed (`stores/account.ts:34`); claiming an anonymous exam needs only its UUID.
- Missing `createdAt` stored as 1970, empty `rubrics {}` stored as null; no "last synced" UI.

### MCP (Phase 3b)
- `GET /api/tokens` has no id tiebreak (`auth.py:163`); no test for the 100-char token name bound; Copy button gives no feedback (`McpTokens.vue:42`).
- A non-numeric `point_overrides` value breaks score queries (`mcp/tools.py:45`); courses with only hidden/solution exams show `exams: 0`.
- Tokens never expire; OAuth 2.1 not built (`mcp/auth.py:19`, by design).

### Grading and pipeline (Phases 1 to 2b)
- Skip reasons lost on reload; a 25 MB body (413) shows "too many images"; Anthropic low credit may arrive as 400 so `no_credits` never fires; Google non-SAFETY block reasons show "couldn't grade"; OpenRouter reasoning isn't streamed (`openrouter.py:22`); Gemini aliases unconfirmed.
- Grading eval not rerun against the new prompt or on real cases (`backend/evals/grading`); no real-provider run.
- Text-first: old exams need re-upload, LaTeX formulas only on Apple Silicon, tables stay crops, long deferred points-rules list, no docling timeout (`worker/main.py:69`), invalid typed point value stays visible and clearing drops the override silently, `planGrading` ignores overrides.
- Subject names: PDF first-page course-title fallback not built (`lib/stats.ts:11`), 189 of 306 sample files guess "Other"; "GRNVS" vs "grnvs" possibly fixed by 0f80a65.
- Unverified: whether MC auto-scored subtasks are counted server-side (probably fixed by f6ef659).

### Foundation and tooling
- `/?login=failed` not shown in the UI; "Stays on this device" wording isn't strictly true for anonymous uploads; `waitForJob` timeout is a `shortcut:` (`lib/api.ts:73`).
- Not built: Slack webhooks, Notion/Slack OAuth, deployment (nginx `/api`, Dockerfile, compose services).
- 4 ESLint errors predate Phase 4 (`Sheet.vue`, `Modal.vue`, `GradingList.vue`, `grading.ts`).
- Never done by hand: live-key run, 375px header, Gemini free tier, two-browser sync, `claude mcp add` / `mcp-remote` Desktop setup. `/security-review` on `phase-4-rag` unconfirmed.
- Not swept: `.superpowers/sdd/*/progress.md` "minor (deferred)" lists and "Left to the builder" sections under `docs/superpowers/`.
- The other 41 `shortcut:` markers are deliberate simplifications; list them with `/ponytail-debt`.

### Test warnings (#19)
- **Warning filters are not scoped to the emitting module** (`backend/pyproject.toml`, from #19): if our own code ever passed `force_full_page_ocr` or similar, the global ignore would hide it. Nothing in `app/` or `tests/` uses them today. *Left because:* ticket asks for category + message matching only. *Fix when:* our code starts using those docling/transformers options; add a `module=` field to each entry.
- **Filters only cover pytest** (`backend/pyproject.toml`, from #19): `app.pipeline.smoke`, `app.pipeline.cli` and `app.worker.main` still print the same three warnings. *Left because:* ticket scope is `uv run pytest`. *Fix when:* the noise bothers the smoke hook output; bump docling/transformers.
- **Filter comments don't use the `shortcut:` form** (`backend/pyproject.toml`, from #19): `/ponytail-debt` won't list them. *Left because:* ticket prescribes "remove when an upgrade stops emitting it". *Fix when:* convenient; rewrite as `# shortcut: hides <lib> warning, drop on next <lib> bump`.
- **`pyproject.toml` is now the pytest config file** (from #19): a later `pytest.ini` or `tox.ini` would take precedence and silently drop these filters. *Fix when:* adding any other pytest config file; keep everything in `pyproject.toml`.

### Review fixes batch (14 findings, 2026-11-20)
- **The upload cap stops the stored copy, not the temporary spool** (`core/storage.py` `save_capped`, `api/routes.py` `upload_exam`): Starlette parses the whole multipart body to a temp file before the handler runs, so a 40 GB anonymous POST fills the temp disk until the 413. *Left because:* the permanent fill is closed; no proxy limit exists in the repo to lean on. *Fix when:* the server is public; add a Content-Length check in middleware or a proxy body limit.
- **A Deck deleted mid-job can leave its PDF on disk** (`worker/main.py` `process_document` vs `api/documents.py` delete): the worker's `copyfile` re-creates `documents/<id>/` after the delete's `rmtree`; the retry then finds no Deck and never cleans it. *Fix when:* touching either; `rmtree` the dir on the rollback path.
- **A failed later sync page leaves the UI stale** (`frontend/src/lib/sync.ts` `pull`): page 1 is written, page 2 throws `Stop`, `pulled` is not bumped, and next time page 1's rows are skipped as already local. *Fix when:* seen; bump `pulled` in a `finally` whenever `wrote` has entries.
- **The job-stream deadline counts connection time, not time without progress** (`api/routes.py` `job_events`): a healthy job slower than 15 min is reported `failed/server` while it still finishes. *Fix when:* jobs run that long; compare against the job's `locked_at` age.
- **An old text layer can still write into the box** (`PdfViewer.vue` `draw`, pre-existing): a draw already at `layer.render()` is not cancelled, so a newer draw's `replaceChildren()` is followed by stray divs. *Fix when:* seen; keep the `TextLayer` handle and `cancel()` it like `rendering`.
- **`test_scored_loads_exams_in_one_go` pins a query count** (`tests/test_mcp_tools.py`, `<= 11`): breaks when `_scored` legitimately needs one more query. *Fix when:* it breaks; compare against a many-task exam instead.

### Slack /quiz crops (2026-11-24)
- **`quiz.answer` calls `get_task` twice** (`slack/quiz.py`): once with, once without the solution, to split question from solution crops. *Fix when:* touching it; return the split from `tools`.
- **`answer` click with choice `-1` is not validated** (`api/slack.py`): only a hand-crafted payload sends it. *Fix when:* touching `_interact`.
- **Crop key reuse relies on payload shape** (`slack/crops.py`, `core/crypto.py`): `INTEGRATIONS_KEY` also encrypts the Slack token; it is rejected as a crop token only because `xoxb-...` has no `/`. *Fix when:* a third use of the key; add a `crop:` prefix or a separate key.
- **Combined crop cap can hide the subtask** (`slack/blocks.py`): context crops come first, so a very large context pushes out the subtask's crops. *Fix when:* seen.
- **Crops replace all text** (`slack/blocks.py` `_question_body`): a subtask with missing crop files next to a context with crops shows only the context image; a text-only context next to subtask crops is dropped. *Fix when:* seen.
- **No test that the answer message puts context crops first** (`tests/test_slack_quiz.py`). *Fix when:* touching it.
- **`answer_blocks` takes an unused `ref`** (`slack/blocks.py`): left over from the dropped self-check. *Fix when:* touching it; drop it from the signature and callers.
- **Link and image base URL come from the unsigned Host header** (`api/slack.py`, `request.base_url`): a replayed signed request (300 s window) with another Host would put attacker-host links in the ephemeral message. Needs a captured signed request. *Fix when:* before exposing beyond a dev tunnel; add a `PUBLIC_URL` setting.
- **`_command` runs inside Slack's 3 s ack window** (`api/slack.py`): it now scans the whole subject. *Fix when:* a large subject times out; build the message in the background task with its own session.
- **Jump scroll can pull a scrolling user back, and ignores a changed `?subtask`** (`ExamPreviewView.vue`): only `params.examId` is watched; the second scroll fires after 400 ms. *Fix when:* seen.
- **No test for an unlinked user over `response_url`** (`tests/test_slack_quiz.py`). *Fix when:* touching it.

### Anki export (#5b-1, 2026-11-23)
- **A note can have an empty front** (`anki.py` `build_deck`): no text, no context, no MC options and no crops leave `Question` empty, and Anki skips the card on import. *Left because:* pipeline subtasks always have text or a crop. *Fix when:* seen; fall back to the label or skip the note.
- **An untitled exam adds an empty tag** (`anki.py`): `Exam.title` may be `""`. *Fix when:* seen; filter falsy tags.
- **Scores are computed twice per export** (`anki.py`, `mcp/tools.py` `weak_refs`): `weak_refs` and `build_deck` each call `latest_shares`. *Fix when:* export is slow; let `weak_refs` return the shares map.
- **Button shows for subjects without a Course** (`StatisticsView.vue`): exams whose subject is guessed from the title find no match in `listSubjects()`, so the user sees a retry message that never helps. *Fix when:* seen; hide the button or show a specific message.
- **The object URL is revoked right after the click** (`lib/subjects.ts` `downloadAnki`): older Firefox may cancel the download. *Fix when:* seen; revoke in a `setTimeout`.
- **Cap past 200 weak subtasks is silent** (`anki.py`): the rest are cut without telling the user, and there is no `shortcut:` comment. *Fix when:* a Subject has more; raise `below` hint in the UI or add a `shortcut:` note.
- **Two Anki tests are weak** (`tests/test_anki.py`): `test_images_are_embedded_once` relies on every seed crop having the same bytes; `test_guids_stable_across_exports` adds an attempt instead of re-grading one. *Fix when:* touching them.

### Notion export (#5b-2, 2026-11-25)
- **Same workspace, different Notion user replaces the row** (`api/integrations.py` `_save`): the upsert key includes `external_user_id`, so reconnecting one workspace as another Notion user deletes the old row and cascades away its database and cards. *Left because:* only a user switching Notion accounts inside one workspace. *Fix when:* seen; key Notion rows on (user, workspace).
- **Reconnect during an export can overwrite the fresh tokens** (`notion/export.py` `_Token._refresh` vs `_save`): the export's refresh writes tokens from the old grant. *Left because:* rare, both grants probably work. *Fix when:* seen.
- **A 5xx retry on `POST /oauth/token` resends a rotated refresh token** (`notion/client.py` `_call`): ends as `notion_auth`, the user reconnects. *Fix when:* seen; don't retry the token endpoint.
- **A 5xx retry on `POST /pages` can duplicate a page** (`notion/client.py`, `shortcut:` in `export.py`), like the crash between Notion's answer and the commit. *Fix when:* duplicates are reported.
- **A non-auth 4xx from `create_page` fails the whole export** (`notion/export.py`): one card Notion refuses ends the job as `server` after retries, and the cards after it are never sent. *Fix when:* seen; skip and log the card.
- **An empty Subject or Exam gives a select `{"name": ""}`, an empty title gives `[]`** (`notion/cards.py`). *Left because:* pipeline exams have titles. *Fix when:* seen.
- **A failed view is never retried** (`notion/client.py` `create_database`): it is logged and the database works without it. *Fix when:* seen.
- **Network errors are not classified** (`notion/client.py`): `httpx.TransportError` skips the client retry and goes through the worker's job retry. *Fix when:* flaky networks waste attempts.
- **Advisory lock edge cases** (`notion/export.py`): `lock.commit()` sits before the `try` (tiny leak window); the Session idles in a transaction while waiting; a job waiting on the lock sends no heartbeat, so a first export over 15 minutes can get the waiting job re-claimed or shown as failed. *Fix when:* two exports of one connection overlap in practice.
- **Disconnect during an export** (`notion/export.py`): `db.refresh` or the card insert fails, the job goes through one generic retry before `notion_not_connected`. *Fix when:* seen.
- **A deleted database is noticed only when a new card is sent** (`notion/export.py`): nothing is read back, so a re-export with no new weak cards does nothing. *Left because:* one-way by design. *Fix when:* sync lands.
- **`nothing_weak` is checked before the active-job lookup** (`api/subjects.py` Notion POST): a second click after the running job emptied the weak set gets 409 instead of the job. *Fix when:* seen.
- **Worker `ExportFailed` path has no `db.rollback()`** (`worker/main.py`): harmless while it is raised outside a failed flush. *Fix when:* the exporter raises it after a DB error.
- **Statistics button edge cases** (`StatisticsView.vue`): no confirmation when `databaseUrl` is null; `notionState`/`notionError` survive a subject change; "Sent." shows even when 0 cards were created (the job carries no count). The Settings link reads "Reconnect or switch workspace" once connected (unrequested wording). *Fix when:* touching the view.
- **Notion test gaps** (`tests/`): the denied-OAuth test uses a bad state, so the `error`/missing-code branches are unproven; no test for a refresh 500 or a failed early refresh, nor that tokens stay unchanged after a failed refresh; the lock test can hang pytest if an assertion fails (non-daemon thread); `test_job_kind_notion_is_accepted` assumes one jobs row and its neighbour deletes all jobs; the spacing test checks `sleeps[1:]` only; no Slack-side test for `?integration=notion`; unused `monkeypatch` param and `others` query in Notion disconnect; mid-file imports in `test_notion_export.py`. *Fix when:* touching them.
- **Downgrade deletes Notion jobs** (`alembic/versions/a1b2c3d4e5f6_notion.py`): forced by the two-value CHECK. *Left because:* downgrade only.
- **A new `httpx.Client` per request** (`notion/client.py`): a TLS handshake per call. *Left because:* fine at 3 requests per second.
- **SSE silence is counted from when the stream first sees `locked_at`** (`api/routes.py` `job_events`): a client joining a job already silent for 14 minutes waits up to 15 more before "failed". Errs late, never early. *Fix when:* seen; compare against `locked_at` itself.
- **A job deleted mid-stream raises `AttributeError`** (`api/routes.py` `job_events`, pre-existing): `_read_job` returns `(None, None)`. *Fix when:* anonymous cleanup races a stream; end the stream as failed.

### Hosting stage 1 (#6a-1, 2026-11-26)
- **Malformed provider body gives a 500** (`api/auth.py` `identity()`): a non-string GitHub email, a non-JSON 200 or a missing `id` raises instead of redirecting to `/?login=failed`. Fails closed. *Fix when:* seen in logs; catch `ValueError`/`KeyError` next to `httpx.HTTPError`.
- **Document upload 401 shows "Couldn't read X"** (`lib/documents.ts` `uploadDocument`, `AddMaterial.vue`): pre-existing; slides always needed sign-in and the UI only offers upload when signed in. *Fix when:* a signed-out path to AddMaterial appears; map 401 to sign-in text.
- **Secrets in logs on errors** (`frontend/nginx.conf` `error_log warn`; uvicorn on the worker): an upstream error logs the request line with its query string, which can hold a single-use OAuth `code`. The api runs with `--no-access-log`. *Left because:* single-use codes, local Docker logs only. *Fix when:* logs leave the VM; set `error_log ... error`.
- **Idle SSE/MCP streams drop after 300 s** (`frontend/nginx.conf` `proxy_read_timeout`). *Left because:* `EventSource` reconnects. *Fix when:* a long MCP call or grading stream is cut off; raise it on those locations.
- **`X-Forwarded-Proto` map trusts the client on a direct hit to `web:8080`** (`frontend/nginx.conf`): only reachable from inside the compose networks. *Fix when:* any port is published; hard-set `https`.
- **The worker can reach `api:8000` directly** (`deploy/compose.prod.yaml`, both on `edge`): a compromised worker (it parses untrusted PDFs) could spoof `X-Forwarded-For` to the grade rate limiter. Minor next to the DB credentials it already holds. *Fix when:* the network layout is revisited in stage 2.
- **Backend image pulls CUDA torch** (`backend/Dockerfile` via docling): several GB, slow first build on the VM. *Fix when:* stage 2 GHCR images; add torch as a direct dep from the CPU index for Linux.
- **OAuth state cookie lacks `Secure`** (`main.py` `SessionMiddleware`, pre-existing `https_only=False`). *Left because:* "Always Use HTTPS" + HSTS. *Fix when:* touching main.py; derive `https_only` from an env var.
- **Hardening narrower than spec layer 4** (`deploy/compose.prod.yaml`, `shortcut:` comment): only the worker has CPU/memory limits; no `read_only` root filesystems. *Fix when:* stage 2.
- **Two `test_sync.py` tests flake on a host clock jump** (seen during the 6a-1 fix wave, machine suspend): they compare the wall clock to the DB's `now()`. Passed on rerun. *Fix when:* it recurs; note the test names.
- **Data move copies `storage/cache/`** (`docs/hosting.md` step 6): model downloads travel along. Harmless, only size.

### Grading eval on real exams (branch grading-eval-real-exams, Task 7)
- **Manual .md drops blank lines inside an answer** (`evals/grading/manual_cases.py` `parse_manual`): an empty line between paragraphs vanishes, a whitespace-only indented line is kept. *Left because:* transcriptions use no blank lines. *Fix when:* a transcription needs paragraphs.
- **Sum check runs after `render_variants`** (`manual_cases.py` `_load`): an excluded exam still renders its crops first. *Left because:* 5 exams, seconds. *Fix when:* more exams.
- **Unmatched / no-solution / no-cover paths not asserted** (`tests/test_eval_scans.py`): only checked by absence. *Fix when:* touching the loader.
- **Duplicate entry ids give duplicate case ids** (`manual_cases.py`): a copy-paste slip in a .md produces two cases with one id. *Fix when:* it bites; reject duplicates in `parse_manual`.
- **CLI default folder is relative** (`manual_cases.py` `main`): works only when run from `backend/`, like `import_scans`. *Fix when:* run from elsewhere.

### Grading eval on real exams (branch grading-eval-real-exams)
- **Two scores on one baseline in x<70 concatenate** (`evals/grading/scan_points.py` `read_scores`): not seen in data; fails safe via the sum check. *Fix when:* an exam drops out for it.
- **`pdf.pages[0]` IndexError on an empty PDF** (`scan_points.py` `read_cover_total`): a traceback on a corrupt scan. *Fix when:* scans come from elsewhere.
- **Sigma PDF wrapper path untested** (`tests/test_eval_scans.py`): `test_read_cover_total_no_sigma` covers the wrapper only. *Fix when:* touching `read_cover_total`.
- **`c["text"] in "0123456789,."` is a substring check** (`scan_points.py:32`): empty text passes, but cannot form a `_SCORE` fullmatch. *Fix when:* touching `read_scores`; use a set.
- **Watermark digits on a score line would still merge** (`scan_points.py`): fails safe via the sum check. *Fix when:* seen in data.
- **A per-exam exception aborts the whole import run** (`evals/grading/import_scans.py` `main`). *Fix when:* more than a handful of exams; catch per exam and mark "error".
- **`match` runs twice per exam; `render_page` reopens the `PdfDocument` per page** (`import_scans.py`): speed only. *Fix when:* import time matters.
- **Excluded rows in coverage.md show 0, not '-'** (`import_scans.py` `main`): cosmetic. *Fix when:* touching the table.
- **"unmatched" counts subtasks with points None/0 and dropped cases** (`import_scans.py` `_import_one`): handoff wording fixed, the number still mixes causes. *Fix when:* the split matters.
- **One solution can pair two scans** (`import_scans.py` `find_pairs`): not in the real data; coverage.md shows the pairing. *Fix when:* it shows twice.
- **Test doesn't assert skipped cases count as unmatched** (`tests/test_eval_scans.py` `test_build_cases_skips_points_above_max_and_question_line_only`). *Fix when:* touching `build_cases`.
- **45pt region minimum is a magic number** (`import_scans.py` `build_cases`, has a `shortcut:` comment). *Fix when:* a real question is under 45pt.
- **The "2px" test pixel sits 1px from the edge** (`tests/test_eval_scans.py` clip test): naming only. *Fix when:* touching it.
- **Crop page size comes from the scan render, not `exam.page_sizes`** (`import_scans.py:102`): right only while scan and solution pages are the same size (A4). *Fix when:* a non-A4 scan.
- **`--limit 0` or negative is not rejected** (`evals/grading/run_eval.py:58`): `[:0]` grades nothing, `-1` drops the last case. *Left because:* dev-only CLI. *Fix when:* someone mistypes it.
- **New report columns untested** (`tests/test_eval.py`): `within_half`/`within_one` are tested in `metrics`, not in the written table. *Fix when:* touching the report.
- **A bbox past the image edge pads black** (`evals/grading/scan_crop.py:16` `clean_crop`): PIL fills outside pixels with black, which reads as ink. *Left because:* regions come from the same-size solution page. *Fix when:* page sizes differ (see above).
- **`convert("RGB")` drops alpha without a white background** (`scan_crop.py:16`): a transparent scan turns black. *Left because:* scans are opaque. *Fix when:* a PNG-with-alpha source appears.
- **Any non-solution PDF in the folder counts as a scan** (`import_scans.py` `find_pairs`): a stray PDF shows up as an unpaired row. *Left because:* coverage.md shows it. *Fix when:* the folder holds other PDFs.
