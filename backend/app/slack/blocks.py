"""Slack message payloads. All Slack JSON shapes live here."""


def esc(text: str) -> str:
    # Slack treats <...> as links/mentions; only these three characters need escaping
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text[:2900] or "-"}}


def _option(i: int, text: str) -> str:
    return f"{chr(65 + i)}. {esc(text)}"


def _header(task: dict) -> dict:
    pts = f" ({task['points']:g} pts)" if task.get("points") else ""
    text = f"{task['exam']} · {task['task']} {task['label']}{pts}".replace("  ", " ")
    return {"type": "header", "text": {"type": "plain_text", "text": text[:150]}}


def _exam_link(url: str) -> dict:
    url = esc(url).replace("|", "%7C")
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": f"<{url}|Open in exam-sim>"}]}


def _images(task: dict, urls: list[str]) -> list[dict]:
    alt = f"{task['exam']}, {task['task']} {task['label']}"[:2000]
    return [{"type": "image", "image_url": u, "alt_text": alt} for u in urls]


def _question_body(task: dict, urls: list[str]) -> list[dict]:
    """Crops as images; without crop files the question text instead."""
    if urls:
        return _images(task, urls)
    text = "\n\n".join(esc(t) for t in (task.get("task_context_text"), task["text"]) if t)[:2800]
    return [_section(text or "_No question text._")]


def question_blocks(task: dict, urls: list[str], exam_url: str) -> list[dict]:
    opts = task["mc_options"]
    if opts:
        buttons = [
            {
                "type": "button",
                "action_id": "answer",
                "value": f"{task['id']}|{i}",
                "text": {"type": "plain_text", "text": f"{chr(65 + i)}. {o}"[:75]},
            }
            for i, o in enumerate(opts)
        ]
        rows = [{"type": "actions", "elements": buttons[i : i + 5]} for i in range(0, len(buttons), 5)]
    else:
        btn = {"type": "button", "action_id": "reveal", "value": task["id"], "text": {"type": "plain_text", "text": "Show solution"}}
        rows = [{"type": "actions", "elements": [btn]}]
    # shortcut: at most 40 images, fewer when option rows need the room (Slack allows 50 blocks); split or link out if a question needs more
    body = _question_body(task, urls)[: min(40, 47 - len(rows))]  # header, divider and link take 3 blocks
    return [_header(task), {"type": "divider"}, *body, *rows, _exam_link(exam_url)]


def verdict(task: dict, choice: int | None) -> str | None:
    key = task["solution"]["mc_key"]
    if choice is None or not key:
        return None
    if set(key) == {choice}:
        return "Correct!"
    return "Right, but more options are correct." if choice in key else "Wrong."


def answer_blocks(task: dict, ref: str, choice: int | None, question_urls: list[str], solution_urls: list[str], exam_url: str) -> list[dict]:
    """The question stays on top, the solution follows after a divider. Solution crops replace the solution text."""
    sol = task["solution"]
    parts = [verdict(task, choice)]
    if sol["mc_key"]:
        right = ", ".join(_option(i, task["mc_options"][i]) for i in sol["mc_key"] if 0 <= i < len(task["mc_options"]))
        parts.append(f"Correct option(s): {right}")
    if not solution_urls:
        parts.append(esc(sol["text"]) or "_No written solution stored._")
    # shortcut: 25 question + 20 solution images keep the message under Slack's 50 blocks (header, 2 dividers, section, link take 5); link out if more are needed
    out = [_header(task), {"type": "divider"}, *_question_body(task, question_urls)[:25], {"type": "divider"}]
    text = "\n\n".join(p for p in parts if p)
    if text:
        out.append(_section(text))
    return [*out, *_images(task, solution_urls)[:20], _exam_link(exam_url)]


def message(text: str, blocks: list[dict] | None = None) -> dict:
    return {"response_type": "ephemeral", "text": text, "blocks": blocks or [_section(text)]}


def connect_message(url: str) -> dict:
    return message(f"Connect your exam-sim account first: {url}", [_section(f"Connect your exam-sim account first: <{url}|open exam-sim>")])
