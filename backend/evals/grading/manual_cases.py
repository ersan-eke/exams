"""Turn hand-transcribed answers (private/manual/<alias>.md) of exams the importer excludes into grading-eval cases (manual-cases.jsonl).

Format: `#` lines are comments. Entry line `<id> | <points> | <answer first line>`; lines indented 4 spaces continue the answer, except
indented `@max `, `@question `, `@solution ` lines, which override that field. Answer `[mc]` marks a multiple-choice subtask (counts for
the sum check, yields no case).
"""

import json
import sys
from pathlib import Path

from app.grading.models import GradeIn, Part, Solution
from app.pipeline import render_variants
from app.pipeline.extract import extract
from app.pipeline.structure import group
from evals.grading.import_scans import _file_b64, _subtasks, find_pairs
from evals.grading.scan_points import read_cover_total

FIELDS = ("@max ", "@question ", "@solution ")


def parse_manual(text: str, name: str = "manual") -> list[dict]:
    entries: list[dict] = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("    ") and entries:
            body = line[4:]
            e = entries[-1]
            key = next((f for f in FIELDS if body.startswith(f)), None)
            if key:
                e[key.strip("@ ")] = body[len(key) :].strip()
            else:
                e["answer"] += "\n" + body
        elif line.strip() and not line.startswith("#"):
            parts = [p.strip() for p in line.split("|", 2)]
            try:
                if len(parts) != 3:
                    raise ValueError
                entries.append({"id": parts[0], "points": float(parts[1].replace(",", ".")), "answer": parts[2]})
            except ValueError:
                raise ValueError(f"{name}:{n}: expected '<id> | <points> | <answer>', got {line!r}") from None
    return entries


def build_manual_cases(alias, entries, exam, blank_dir, ink_dir) -> tuple[list[dict], int, list[str], int]:
    """cases, mc entries, unmatched ids, dropped (missing max or points above max)."""
    subs = {s.id: s for s in _subtasks(exam)}
    cases, mc, unmatched, dropped = [], 0, [], 0
    for e in entries:
        s = None if "max" in e else subs.get(e["id"])  # @max = text-only case, structure ignored
        if e["answer"] == "[mc]" or (s and s.mc_key is not None):
            mc += 1
            continue
        if s is None and "max" not in e:
            unmatched.append(e["id"])
            continue
        mx = float(e["max"]) if "max" in e else s.points
        if not mx or e["points"] > mx:
            dropped += 1
            continue
        regions = s.regions if s else []
        request = GradeIn(
            points=mx,
            question=Part(
                text=(s.text if s else "") or e.get("question", ""),
                images=[i for r in regions if r.visual is not False for i in _file_b64(blank_dir, r.image)],
            ),
            solution=Solution(
                text=(s.solution_text if s else "") or e.get("solution", ""), images=[i for r in regions for i in _file_b64(ink_dir, r.image)]
            ),
            answer=Part(text=e["answer"], images=[]),
        )
        cases.append({"id": f"manual/{alias}/{e['id']}", "expected": e["points"], "request": request.model_dump(mode="json", exclude_none=True)})
    return cases, mc, unmatched, dropped


def _load(folder: Path) -> tuple[list[dict], list[str]]:
    all_cases, lines = [], []
    for alias, scan, sol in find_pairs(folder):
        md = folder / "manual" / f"{alias}.md"
        if not md.is_file():
            continue
        entries = parse_manual(md.read_text(), str(md))
        total, cover = sum(e["points"] for e in entries), read_cover_total(scan)
        if sol is None:
            lines.append(f"{alias}: excluded (no solution pdf)")
            continue
        pages = extract(sol)
        exam = group(pages, sol.name, pdf_path=sol)
        dirs = render_variants(sol, exam, pages, folder / "work" / alias, ink=True)
        cases, mc, unmatched, dropped = build_manual_cases(alias, entries, exam, dirs["blank"], dirs["ink"])
        ok = cover is not None and abs(total - cover) < 1e-6
        lines.append(
            f"{alias}: {len(cases) if ok else 0} cases, {mc} mc, {len(unmatched)} unmatched {unmatched}, {dropped} dropped, sum {total:g} vs cover {cover}, {'ok' if ok else 'excluded'}"
        )
        if ok:
            all_cases += cases
    return all_cases, lines


def load_manual(folder: Path) -> list[dict]:
    return _load(folder)[0]


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    folder = Path(argv[0] if argv else "evals/grading/private")
    if not folder.is_dir():
        sys.exit(f"folder not found: {folder}")
    if not (folder / "manual").is_dir():
        sys.exit(f"no manual folder in {folder}")
    try:
        cases, lines = _load(folder)
    except ValueError as err:
        sys.exit(str(err))
    print("\n".join(lines))
    (folder / "manual-cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cases))


if __name__ == "__main__":
    main()
