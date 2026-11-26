import base64
from dataclasses import dataclass

from .models import GradeIn, Part

PROMPT_VERSION = "2026-11-05.1"

_COMMON = """Widen points_min/points_max around points only when the answer is genuinely ambiguous or unreadable; \
otherwise set all three equal. Every rubric line has item, max, hit (points awarded), a one-line note and its source. \
In an image of the student's answer, everything the student drew or wrote by hand is blue; the rest is the \
printed exam. Text the student typed comes as text. Write plain text, no Markdown. Feedback is at most 4 short sentences addressed to the student. \
Reply with the JSON object only."""

SYSTEM_SOLUTION = f"""You grade a student's exam answer against the official solution.
First read the point split: the saved rubric wins if given, otherwise the solution's own point guide. Then grade strictly \
against it; do not apply your own view of what is correct. Rubric lines taken from the saved rubric or the solution's \
guide have source "solution"; lines you had to infer have source "inferred".
{_COMMON}"""

SYSTEM_OWN = f"""You grade a student's exam answer; no official solution exists.
First solve the task yourself, then build a rubric whose maxima sum to the task's points (every line has source \
"inferred"), then grade the answer against it. The reference tasks, if any, only show how this course hands out points; \
they are not the answer to this task. Course material excerpts, if any, show how the course teaches the topic; use them as \
context, not as the answer.
{_COMMON}"""


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class Image:
    png: bytes


@dataclass(frozen=True)
class CacheBreak:
    """Everything before this item is identical for repeated attempts at the same task (cacheable prefix)."""


Item = Text | Image | CacheBreak


def system_for(req: GradeIn) -> str:
    return SYSTEM_SOLUTION if req.solution else SYSTEM_OWN


def _part(label: str, p: Part) -> list[Item]:
    return [Text(f"{label}:\n{p.text}"), *(Image(base64.b64decode(i)) for i in p.images)]


def build_content(req: GradeIn) -> list[Item]:
    items = _part("Question", req.question)
    if req.solution:
        items += _part("Official solution", req.solution)
        if req.solution.rubric:
            lines = "\n".join(f"- {r.item} ({r.max} points)" for r in req.solution.rubric)
            items.insert(len(items) - len(req.solution.images), Text(f"Saved rubric:\n{lines}"))
    else:
        for n, r in enumerate(req.references, 1):
            items += _part(f"Reference task {n} ({r.points} points)", r.question)
            items += _part(f"Reference solution {n}", r.solution)
        if req.material:
            items.append(Text(f"Course material (context only):\n{req.material}"))
    return [*items, CacheBreak(), Text(f"Max points: {req.points:g}"), *_part("Student answer", req.answer)]
