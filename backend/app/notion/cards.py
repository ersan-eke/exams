"""A Notion card (page properties and body blocks) for one weak subtask. Pure: no DB, no HTTP."""

TEXT_MAX = 2000
CHILDREN_MAX = 100
CUT = "… cut, see the exam in exam-sim."


def _rich(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text[i : i + TEXT_MAX]}} for i in range(0, len(text), TEXT_MAX)]


def _block(kind: str, text: str) -> dict:
    return {"type": kind, kind: {"rich_text": _rich(text)}}


def _image(upload_id: str) -> dict:
    return {"type": "image", "image": {"type": "file_upload", "file_upload": {"id": upload_id}}}


def _cap(blocks: list[dict], n: int) -> list[dict]:
    return blocks if len(blocks) <= n else blocks[: n - 1] + [_block("paragraph", CUT)]


def _select(name: str) -> dict:
    return {"select": {"name": name.replace(",", " ")[:100]}}  # Notion select names: no commas, at most 100 characters


def build_card(q: dict, a: dict, share: float, subject: str, question_images: list[str], answer_images: list[str]) -> tuple[dict, list[dict]]:
    """`(properties, children)` for `client.create_page`. Text only where the crops are missing (as in the Anki deck)."""
    title = " · ".join(s for s in (q["exam"], " ".join(x for x in (q["task"], q["label"]) if x)) if s)
    properties = {
        "Question": {"title": _rich(title)},
        "Subject": _select(subject),
        "Exam": _select(q["exam"]),
        **({"Task": _select(q["task"])} if q["task"] else {}),
        "Type": {"select": {"name": "Multiple choice" if q["mc_options"] else "Open"}},
        "Score %": {"number": share},
        "Status": {"select": {"name": "New"}},
    }
    if question_images:
        body = [_image(i) for i in question_images]
    else:
        body = [_block("paragraph", t) for t in (q["task_context_text"], q["text"]) if t]
        body += [_block("bulleted_list_item", f"{chr(65 + i)}. {o}") for i, o in enumerate(q["mc_options"])]
    sol = a["solution"]
    answer = [_image(i) for i in answer_images]
    if not answer:
        if sol["text"]:
            answer.append(_block("paragraph", sol["text"]))
        if sol["mc_key"]:
            answer.append(_block("paragraph", "Correct: " + ", ".join(chr(65 + i) for i in sol["mc_key"])))
    if not answer:
        answer = [_block("paragraph", "No solution stored.")]
    toggle = {"type": "toggle", "toggle": {"rich_text": _rich("Answer"), "children": _cap(answer, CHILDREN_MAX)}}
    return properties, _cap(body, CHILDREN_MAX - 1) + [toggle]  # one slot is the toggle
