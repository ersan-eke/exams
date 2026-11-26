"""Which subtasks still have no point value, grouped by what the exam says about them.

Run from backend/: uv run python -m evals.text_first.points_report ../samples
Prints counts per category plus a few examples (exam, task, subtask ids only: the PDFs are copyrighted).
"""

import re
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from app.pipeline.extract import extract
from app.pipeline.models import ExamStructure, Subtask, Task
from app.pipeline.structure import POINTS_RE, group

SUM_HINT = re.compile(r"\d\s*P?\s*\+|\+\s*\d|^[+=\s]+$|\+\s*$")  # "2+3", "+++=" left after the points are cut out
EACH_HINT = re.compile(r"\bje\s*\d|points?\s*each|pro\s*Teilaufgabe\s*kann", re.IGNORECASE)
TOTAL_HINT = re.compile(r"/\s*\d+(?:[.,]\d+)?\s*$|[(\[]\s*\d+(?:[.,]\d+)?\s*[)\]]\s*$")


def category(exam: ExamStructure, task: Task, s: Subtask) -> str:
    kind = "mc" if s.mc_options else "other"
    intro = " ".join([task.title] + [c.text for c in task.context])
    rule = task.mc_rule or exam.mc_rule
    if s.mc_options and rule and rule.kind == "per_tick":
        return f"{kind}/per_tick_without_key"
    if SUM_HINT.search(task.title):
        return f"{kind}/header_sum"
    if EACH_HINT.search(intro):
        return f"{kind}/points_each"
    if TOTAL_HINT.search(task.title):
        return f"{kind}/slash_or_bracket_total"
    if POINTS_RE.search(" ".join(s.text.splitlines()[:3])):
        return f"{kind}/points_word_in_question"
    if task.points is None:
        return f"{kind}/nothing_stated"
    return f"{kind}/task_total_only"


def _one(pdf: Path) -> tuple[str, list[tuple[str, str, str]], int, int]:
    exam = group(extract(pdf), str(pdf), pdf_path=pdf)
    rows = [(category(exam, t, s), t.id, s.id) for t in exam.tasks for s in t.subtasks if s.points is None]
    subs = [s for t in exam.tasks for s in t.subtasks]
    return pdf.name, rows, sum(bool(s.mc_options) for s in subs), len(subs)


def points_report(root: Path) -> dict[str, list[tuple[str, str, str]]]:
    """category -> [(exam, task, subtask)] for every subtask still without points."""
    out: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    with ProcessPoolExecutor() as pool:
        for name, rows, _, _ in pool.map(_one, sorted(root.rglob("*.pdf"))):
            for cat, tid, sid in rows:
                out[cat].append((name, tid, sid))
    return dict(out)


def main() -> None:
    report = points_report(Path(sys.argv[1]))
    for kind in ("mc", "other"):
        total = sum(len(v) for k, v in report.items() if k.startswith(kind + "/"))
        print(f"{kind}: {total} without points")
        for cat, rows in sorted(report.items(), key=lambda kv: -len(kv[1])):
            if cat.startswith(kind + "/"):
                print(f"  {len(rows):5}  {cat}   e.g. {rows[0]}")


if __name__ == "__main__":
    main()
