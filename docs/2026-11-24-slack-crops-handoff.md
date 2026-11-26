# Slack /quiz crops handoff

## Done
- Signed crop route `GET /api/slack/crops/{token}` (24 h token, PNG only, `slack/crops.py`), `blocks.py`: header, divider, crop images (escaped text fallback without crop files), buttons, "Open in exam-sim" link.
- Answer keeps the question on top, a divider, then verdict and correct options, and the solution crops (the solution text only when there are no crops). No self-check buttons; the "Open in exam-sim" link ends the message.
- `/quiz` returns an empty 200 and posts the message via `response_url` (`client.respond(..., replace_original=False)`) in a BackgroundTask; without a `response_url` it answers inline. `client.respond` logs Slack's error body (300 chars) on non-200.
- Context crops (`tools.context_crops`, same selection as `get_task` via `_applicable_context`) come before the subtask's crops in question and answer.
- The old "figures not shown here" notice is gone: the crops show the figures.
- Setup notes: `docs/slack.md` ("Page crops in messages"). Unfixed review findings: `docs/findings.md`.

## Not done
- **Task 3, the manual gate, was never run** (no human or Slack available); the code assumes Slack renders the image URLs. If it does not, `slack_file` (spec, approach 2) is the fallback and needs its own spec change. To run it:
  1. Start the backend with `uv run uvicorn main:app --proxy-headers --forwarded-allow-ips 127.0.0.1`, the worker, `npm run dev` and the tunnel; update the Slack app URLs to the current tunnel host.
  2. Run `/quiz numprog` and `/quiz grnvs` ten times. Record: do images show and are they readable? Are the image URLs `https://`? Is any reply `invalid_command_response`? Do MC questions show their option text in the crop, or only A/B/C on the buttons?
  3. If images fail, stop and bring the result to the user. If MC options are missing from crops, also show option text (button text already carries it).
  4. `curl -sI <an image url>` returns 200 `image/png`.

## Decisions already made
- Image caps keep a message under Slack's 50 blocks: question message at most 40 images, clamped to 47 minus the option rows; answer message 25 question (context included) and 20 solution images.
- Crop URLs are signed, expire after 24 h and need a public `https` base.
- No LLM in Slack (unchanged).

## Known limits
- `quiz.answer` calls `get_task` twice (with and without solution) to split question from solution crops.
- An `answer` click with choice `-1` is not validated.

## Later changes (after the first handoff)

- **Self-check buttons were dropped** ("I got it"/"I missed it"); the plan, spec and Task 5 still describe them: do not rebuild them. The answer shows the verdict, the correct options and the solution crops (solution text only when there are no solution crops).
- `/quiz` acks at once and posts via `response_url` (`client.respond` only posts to `https://hooks.slack.com/`); failed posts log Slack's error body.
- `/quiz` picks randomly among the 10 weakest questions of the whole subject (`find_tasks(limit=None)`, `quiz.WEAKEST`).
- "Open in exam-sim" links to `/exams/<id>/view?subtask=<key>`; `ExamPreviewView.vue` scrolls to that question (twice, 400 ms apart, because crops shift the layout).

## Closed

The Slack gate (Task 3) was run by the user in the real workspace on 2026-11-25: images render and `/quiz` works. Phase 5a is closed.
