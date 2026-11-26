"""An Anki deck (.apkg) of a Subject's weak subtasks: question and crops on the front, solution on the back. No LLM."""

import hashlib
import html
import shutil
import tempfile
import uuid
import zlib
from io import BytesIO
from pathlib import Path

import genanki
from sqlalchemy.orm import Session

from .db.models import Course
from .mcp import tools

LIMIT = 200
BELOW = 0.6
MODEL_ID = 1_607_392_319  # fixed: a new id would make Anki treat every re-import as a different note type

MODEL = genanki.Model(
    MODEL_ID,
    "exam-sim question",
    fields=[{"name": "Question"}, {"name": "Answer"}, {"name": "Source"}],
    templates=[{
        "name": "Card",
        "qfmt": "{{Question}}",
        "afmt": '{{FrontSide}}<hr id="answer">{{Answer}}<div class="source">{{Source}}</div>',
    }],
    css=".card { text-align: left; font-size: 18px; } .card img { max-width: 100%; } .source { margin-top: 1em; color: #888; font-size: 13px; }",
)  # fmt: skip


def _html(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


def _imgs(paths: list[Path], media: Path) -> str:
    """Copy crops into `media` under a content hash name, so equal files are one media entry."""
    names = []
    for p in paths:
        name = hashlib.sha1(p.read_bytes()).hexdigest()[:16] + ".png"
        shutil.copyfile(p, media / name)
        names.append(name)
    return "".join(f'<img src="{n}">' for n in names)


def build_deck(db: Session, user_id: uuid.UUID, course: Course, below: float = BELOW, limit: int = LIMIT) -> bytes | None:
    """The .apkg bytes of the subtasks whose latest score share is below `below`, or None when there are none."""
    refs = tools.weak_refs(db, user_id, course.id, below, limit)
    if not refs:
        return None
    shares = tools.latest_shares(db, user_id, course.id)
    deck = genanki.Deck(zlib.crc32(str(course.id).encode()), f"exam-sim::{course.name}")
    with tempfile.TemporaryDirectory() as tmp:
        media = Path(tmp)
        for ref in refs:
            q, q_paths = tools.get_task(db, user_id, ref, False)
            a, paths = tools.get_task(db, user_id, ref, True)  # shortcut: two calls per card, fine for 200; fold into one if profiled
            exam, key = ref.split("/", 1)
            # the crops show the question as printed; the extracted text (PDF noise, letters that may not match the layout) is the fallback only
            question = []
            if not q_paths:
                question = [_html(t) for t in (q["task_context_text"], q["text"]) if t]
                question += [f"{chr(65 + i)}. {_html(o)}" for i, o in enumerate(q["mc_options"])]
            sol = a["solution"]
            answer_imgs = _imgs(paths[len(q_paths) :], media)
            answer = []
            if not answer_imgs:
                answer = [_html(sol["text"])] if sol["text"] else []
                if sol["mc_key"]:
                    answer.append("Correct: " + ", ".join(chr(65 + i) for i in sol["mc_key"]))
            if not answer and not answer_imgs:
                answer = ["No solution stored"]
            share = shares[(uuid.UUID(exam), key)]
            source = " · ".join(_html(s) for s in (q["exam"], q["task"], q["label"]) if s) + f" · {round(share * 100)}%"
            deck.add_note(genanki.Note(
                MODEL,
                ["<br>".join(question) + _imgs(q_paths, media), "<br>".join(answer) + answer_imgs, source],
                guid=genanki.guid_for(exam, key),
                tags=[t.replace(" ", "_") for t in (course.name, q["exam"])],
            ))  # fmt: skip
        package = genanki.Package(deck)
        package.media_files = [str(p) for p in media.iterdir()]
        out = BytesIO()
        package.write_to_file(out)
    return out.getvalue()
