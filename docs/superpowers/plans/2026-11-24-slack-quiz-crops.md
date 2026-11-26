# Slack /quiz crops Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/quiz` shows page crops instead of text, keeps the question when the solution is shown, and ends with a self-check that points to the web app.

**Architecture:** Slack `image` blocks point at a new signed, expiring URL on our backend (`GET /api/slack/crops/<token>`, Fernet token from the existing `INTEGRATIONS_KEY`). `app/slack/crops.py` makes and checks those tokens; `app/slack/blocks.py` builds header/divider/image/actions blocks; `app/slack/quiz.py` gathers crop paths from `tools.get_task` and passes URLs to the builders. No DB writes, no new Slack scopes, manifest unchanged.

**Tech Stack:** FastAPI, `cryptography` Fernet (already installed), pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-slack-quiz-formatting-design.md`

## Global Constraints

- Crop URL token TTL: 86400 s (24 h). Slack `image_url` max 3000 characters; `image_url` must be `https`.
- Block limits: `header` text 150 characters, `section` text 3000, 50 blocks per message, button text 75, image `alt_text` 2000.
- The crop route is unauthenticated: it serves only a file named by a valid, unexpired Fernet token, only layers `blank`/`ink`, only names matching `CROP_NAME`, only inside `exam_dir(exam_id)`. Every failure is a plain 404.
- No LLM grading, no stored self-check result (spec non-goals).
- Never commit exam PDFs or crops; tests write PNGs into the temp `STORAGE_DIR` that `tests/conftest.py` sets.
- Backend rules: `uv run`, `ruff check . && ruff format .` before each commit; shortcuts carry a `shortcut:` comment.
- After code changes run `graphify update .` (project rule).

## Review Focus

- A question whose crop files are missing: the message falls back to escaped text, never empty. (Task 2)
- A tampered, truncated or expired token, or a token naming `../x.png`: 404, nothing served. (Task 1)
- A question with context plus many crops: stays within 50 blocks and keeps the buttons. (Task 2)
- A very long exam title: the header is cut to 150 characters, not rejected by Slack. (Task 2)
- The request base URL is `http://` behind the tunnel (uvicorn without `--proxy-headers`): the manual check must show `https://` image URLs. (Task 3)
- Clicking a self-check button twice or as an unlinked user: second click re-renders the same message; unlinked gets the connect message. (Task 5)

---

### Task 1: Crop token and route

**Files:**
- Modify: `backend/app/core/crypto.py` (`decrypt` gets `ttl`)
- Create: `backend/app/slack/crops.py`
- Modify: `backend/app/api/slack.py` (new route; fix the module docstring, it says every route checks Slack's signature)
- Test: `backend/tests/test_slack_crops.py`; add one TTL case to `backend/tests/test_crypto.py`

**Interfaces:**
- Produces: `crypto.decrypt(token: str, ttl: int | None = None) -> str` (raises `cryptography.fernet.InvalidToken` when expired or bad).
- Produces: `crops.TTL = 86400`; `crops.crop_url(base: str, path: Path) -> str`; `crops.crop_file(token: str) -> Path | None`.
- Produces: route `GET /api/slack/crops/{token}` returning `image/png` with `Cache-Control: private, max-age=86400`, or 404.

- [ ] **Step 1: Write failing tests** in `test_crypto.py`: `test_ttl_rejects_old_token` (monkeypatch `time.time` forward past the ttl, or use `ttl=-1`; assert `InvalidToken`). In `test_slack_crops.py`, with a PNG written to `exam_dir(exam)/"blank/crops/a.png"`:
  - `test_round_trip`: `crop_file(token_from(crop_url("https://h", path))) == path`.
  - `test_url_is_https_base_plus_token_and_short`: starts with `https://h/api/slack/crops/`, length < 3000.
  - `test_bad_tokens_return_none`: `""`, `"x"`, a valid token with last char changed, a token of `encrypt("<exam>/blank/../x.png")`, `encrypt("<exam>/other/a.png")`, `encrypt("not-a-uuid/blank/a.png")`, an expired token (`monkeypatch.setattr(crops, "TTL", -1)`).
  - `test_missing_file_returns_none`.
  - `test_route_serves_png_and_404s_everything_else`: `TestClient(app).get(url_path)` is 200, `content-type: image/png`, body equals the file bytes; garbage token is 404; route works without any Slack headers or cookies.
  - `test_route_404_when_slack_disabled`: `monkeypatch.setattr(config, "SLACK_ENABLED", False)` then 404.
- [ ] **Step 2: Run** `cd backend && uv run pytest tests/test_slack_crops.py tests/test_crypto.py -v` — expect FAIL (missing module / signature).
- [ ] **Step 3: Implement** `decrypt(token, ttl=None)` passing `ttl` to `MultiFernet.decrypt`. In `crops.py`: `crop_url` derives exam id, layer, name from `path.parents[2].name`, `path.parents[1].name`, `path.name`, encrypts `"<exam>/<layer>/<name>"`, returns `f"{base}/api/slack/crops/{token}"`. `crop_file` decrypts with `ttl=TTL`, returns `None` on `InvalidToken`/`ValueError`, checks `uuid.UUID(exam)`, layer in `{"blank", "ink"}`, `CROP_NAME.fullmatch(name)`, builds `exam_dir(id)/layer/"crops"/name`, applies the same `resolve().is_relative_to(exam_dir(id).resolve())` and `is_file()` guard as `tools._crops`. The route is `async def` returning `FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})`; 404 when `not config.SLACK_ENABLED` or `crop_file` is `None`. No `verified_body`, no DB dependency.
- [ ] **Step 4: Run** the same pytest command — expect PASS; then `uv run pytest tests/test_slack_signature.py tests/test_slack_events.py -q` still passes.
- [ ] **Step 5: Commit** `feat: signed crop URLs for Slack image blocks` (after `ruff check . && ruff format .`).

### Task 2: Question message with crops

**Files:**
- Modify: `backend/app/slack/blocks.py` (`_heading` becomes a `header` block; `question_blocks` new signature; remove the figure notice)
- Modify: `backend/app/slack/quiz.py` (`question` gathers crop URLs)
- Modify: `backend/app/api/slack.py` (`_command` passes `base` to `quiz.question`)
- Modify tests: `backend/tests/test_slack_quiz.py` (`test_figure_notice*`, `test_long_text_and_many_options`, `test_mrkdwn_is_escaped` use the old API or notice)
- Test: `backend/tests/test_slack_quiz.py`

**Interfaces:**
- Consumes: `crops.crop_url(base, path)` (Task 1); `tools.get_task(db, user_id, ref, False) -> (task, paths)`.
- Produces: `blocks.header(task: dict) -> dict` (a `header` block, `plain_text`, text cut to 150, not mrkdwn-escaped); `blocks.exam_link(url: str) -> dict` (a `context` block, `<url|Open in exam-sim>`).
- Produces: `blocks.images(task: dict, urls: list[str]) -> list[dict]` — `image` blocks, `alt_text` = exam, task, label (cut to 2000), capped at 40 images (`shortcut: 40 keeps the message under Slack's 50 blocks, split or link out if a question ever needs more`).
- Produces: `blocks.question_blocks(task: dict, urls: list[str], exam_url: str) -> list[dict]` = `[header, divider, *images, actions, exam_link]`; when `urls` is empty, `[header, divider, section(escaped text with context), actions, exam_link]` (the fallback, same text rules as today).
- Produces: `quiz.question(db, user_id, subject, base) -> dict`; `exam_url = f"{base}/exams/{exam_id}/view"`, `exam_id = ref.partition("/")[0]`.

- [ ] **Step 1: Write failing tests** (extend the existing fixtures; write PNGs for the regions' `image` names of `MC` and `TXT` into `exam_dir(seed["exam"])/"blank/crops"`; add a `seed_crops` fixture or a `crops(db, seed)` helper in the test file):
  - `test_question_has_header_divider_images_and_buttons`: block types in order `header`, `divider`, `image`..., `actions`, `context`; image URLs start with `http://testserver/api/slack/crops/`; no `section` with question text.
  - `test_missing_crop_files_fall_back_to_text`: no PNGs → a `section` contains `"Which?"` (escaped), buttons still present, message not empty.
  - `test_header_cut_to_150`: exam title of 300 characters → header text length ≤ 150.
  - `test_many_crops_stay_under_50_blocks`: `blocks.question_blocks` with 60 URLs and 7 MC options → `len(blocks) <= 50` and the `actions` block still present.
  - `test_exam_link_points_at_exam_view`: context block text contains `/exams/<exam id>/view`.
  - Update the three old tests to the new shape or delete the figure-notice tests (the notice no longer exists).
- [ ] **Step 2: Run** `uv run pytest tests/test_slack_quiz.py -v` — expect FAIL.
- [ ] **Step 3: Implement** the interfaces above. `quiz.question` calls `tools.get_task(db, uid, ref, False)`, maps `paths` through `crops.crop_url(base, p)`, builds the message with `blocks.message(top_level_text, blocks.question_blocks(...))`; keep the top-level `text` as the notification fallback (exam + label, no question text).
- [ ] **Step 4: Run** `uv run pytest tests/test_slack_quiz.py tests/test_slack_crops.py -q` — expect PASS.
- [ ] **Step 5: Commit** `feat: show page crops in /quiz questions`.

### Task 3: Gate — one real question in Slack (manual, throwaway)

**Files:** none changed; findings go into `docs/2026-11-24-slack-crops-handoff.md` (created in Task 6).

- [ ] **Step 1: Start** backend with `uv run uvicorn main:app --proxy-headers --forwarded-allow-ips 127.0.0.1`, the worker, `npm run dev`, and the tunnel; update the Slack app URLs to the current tunnel host (checklist A).
- [ ] **Step 2: Run** `/quiz numprog` and `/quiz grnvs` ten times in Slack. Record: do images show (and do they look readable)? Are the image URLs `https://`? Is any reply `invalid_command_response`? Do MC questions show their option text in the crop, or only A/B/C on the buttons?
- [ ] **Step 3: Decide.** Images show → continue. Images fail → stop and bring the result back to the user; `slack_file` (spec, approaches 2) is the fallback and needs its own spec change. MC options missing from crops → Task 4 must also show option text (button text already carries it, so likely nothing to do).
- [ ] **Step 4: Check the tunnel side:** `curl -sI <an image url>` returns 200 `image/png`.

### Task 4: Answer keeps the question, adds solution crops

**Files:**
- Modify: `backend/app/slack/blocks.py` (`answer_blocks`)
- Modify: `backend/app/slack/quiz.py` (`answer`)
- Modify: `backend/app/api/slack.py` (`_interact` passes `base` through, already available)
- Test: `backend/tests/test_slack_quiz.py` (`test_answers` and friends)

**Interfaces:**
- Consumes: Task 2's `header`, `images`, `exam_link`, `crops.crop_url`.
- Produces: `blocks.answer_blocks(task: dict, ref: str, choice: int | None, question_urls: list[str], solution_urls: list[str], exam_url: str, check: bool | None = None) -> list[dict]` (`ref` and `check` are used from Task 5 on) = `[header, divider, *question images (or fallback text section), divider, verdict/correct-options/solution-text section, *solution images, exam_link]`; no `actions` block yet (Task 5 adds the self-check).
- Produces: `quiz.answer(db, user_id, ref, choice, base) -> dict`. Question crop paths come from `get_task(..., False)`, solution crops are `paths_with_solution[len(question_paths):]` (the solution call returns the question crops first, then ink and solution crops; see `tools.get_task`).

- [ ] **Step 1: Write failing tests:** `test_answer_keeps_question_and_separates_solution`: after a wrong click the message has a `divider` between the question images and the solution section, contains the question's image URLs, has no `actions` block; `test_solution_crops_follow_solution_text` using a second PNG in `ink/crops` for an exam with ink (or the seeded solution exam, see `test_mcp_tools.py:135-140` for how it is seeded); `test_text_only_question_answer_keeps_fallback_text`. Keep the verdict assertions of `test_answers` (`Correct!`, `Wrong.`, `B. y`, `because`, `free solution`).
- [ ] **Step 2: Run** `uv run pytest tests/test_slack_quiz.py -v` — expect FAIL.
- [ ] **Step 3: Implement** `answer_blocks` and `quiz.answer` as specified; keep `esc` on all text sections.
- [ ] **Step 4: Run** `uv run pytest tests/test_slack_quiz.py -q` — expect PASS.
- [ ] **Step 5: Commit** `feat: keep the question and show solution crops after answering`.

### Task 5: Self-check buttons

**Files:**
- Modify: `backend/app/slack/blocks.py` (`answer_blocks` gets `check: bool | None = None`)
- Modify: `backend/app/slack/quiz.py` (`answer(..., check)`)
- Modify: `backend/app/api/slack.py` (`interactions` parsing: two new `action_id`s)
- Test: `backend/tests/test_slack_quiz.py`

**Interfaces:**
- Changes: `answer_blocks(task, ref, choice, question_urls, solution_urls, exam_url, check=None)` (signature from Task 4): `check is None` → append an `actions` block with buttons `action_id` `got_it` ("I got it") and `missed_it` ("I missed it"), `value` = `f"{ref}|{-1 if choice is None else choice}"`; `check is True/False` → no buttons, instead a `context` block "Nice." / "Worth another look in exam-sim." followed by the `exam_link`.
- Consumes/changes: `quiz.answer(db, user_id, ref, choice, base, check=None)`; the `interactions` route maps `got_it`/`missed_it` to `check=True/False` and parses the `|`-separated choice, where `-1` means `None`; same 400 behavior as today for malformed values.

- [ ] **Step 1: Write failing tests:** `test_answer_has_self_check_buttons`; `test_got_it_swaps_buttons_for_one_line_and_link` (click → `sent[0][1]` has no `actions`, contains "Nice." and `/exams/<id>/view`); `test_missed_it_line`; `test_self_check_keeps_verdict` (verdict text from the original choice is still shown); `test_self_check_twice_renders_same_message`; `test_unlinked_self_check_gets_connect`; `test_bad_self_check_value_is_400` (non-string, no `|`, non-int).
- [ ] **Step 2: Run** `uv run pytest tests/test_slack_quiz.py -v` — expect FAIL.
- [ ] **Step 3: Implement** as above. Nothing is written to the DB.
- [ ] **Step 4: Run** `uv run pytest tests/test_slack_quiz.py tests/test_slack_crops.py -q` — expect PASS.
- [ ] **Step 5: Commit** `feat: self-check buttons after the Slack solution`.

### Task 6: Context crops, docs, handoff, reviews

**Files:**
- Modify: `backend/app/mcp/tools.py` (add `context_crops(db, user_id, ref) -> list[Path]`; extract the context selection `get_task` already uses (`position.get(c.get("applies_from"), -1) <= sub.position`) into one helper both use)
- Modify: `backend/app/slack/quiz.py` (question and answer put context crops before the subtask's)
- Test: `backend/tests/test_mcp_tools.py` (context crops), `backend/tests/test_slack_quiz.py`
- Modify: `docs/slack.md` ("shows no page crops" is no longer true; add: image URLs must be public `https`, run uvicorn with `--proxy-headers --forwarded-allow-ips 127.0.0.1` behind a tunnel, crop URLs expire after 24 h, old messages break when the tunnel host changes)
- Create: `docs/2026-11-24-slack-crops-handoff.md` (done / not done / decisions, Task 3's findings)
- Modify: `docs/findings.md` (every unfixed review finding, per project rules)

**Interfaces:**
- Produces: `tools.context_crops(db: Session, user_id: uuid.UUID, ref: str) -> list[Path]` — crop files of the context blocks that apply to this subtask, `blank` layer, same `_crops` guard; `get_task`'s own output is unchanged.

- [ ] **Step 1: Write failing tests:** `test_context_crops_for_applicable_context_only` (a context with `applies_from` later than the subtask is excluded; missing files skipped); `test_question_shows_context_crops_first` in the Slack tests (context image block precedes the subtask's).
- [ ] **Step 2: Run** `uv run pytest tests/test_mcp_tools.py tests/test_slack_quiz.py -q` — expect FAIL.
- [ ] **Step 3: Implement** `context_crops` and wire it into `quiz.question` / `quiz.answer`; the 40-image cap from Task 2 applies to the combined list.
- [ ] **Step 4: Run** the full suite `uv run pytest` (needs the DB) and `ruff check . && ruff format .`; then `graphify update .` from the repo root. Expected: all green.
- [ ] **Step 5: Reviews:** `/code-review high` and `/security-review` (the public crop route is the new surface); record unfixed findings in `docs/findings.md` and say which in the final reply.
- [ ] **Step 6: Commit** `feat: context crops, docs and handoff for Slack crops`.
