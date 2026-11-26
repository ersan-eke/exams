"""Pipeline regression check on a small, representative set of sample PDFs.

    python -m app.pipeline.smoke             # run the set, compare with the baseline (exit 1 on change)
    python -m app.pipeline.smoke --update    # accept the current output as the new baseline
    python -m app.pipeline.smoke --select    # run all of samples/, pick a new set covering every feature

The baseline holds numbers and issue messages only, never exam text (the PDFs are copyrighted).
Crops aren't rendered: the check covers extraction and structure; the full run (cli.py) covers the rest.
Runs automatically after Claude Code edits files under app/pipeline/ (.claude/hooks/pipeline-smoke.sh).
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from .extract import extract
from .models import ExamStructure
from .structure import group

ROOT = Path(__file__).parents[3]
SAMPLES = ROOT / "samples"
BASELINE = ROOT / "backend" / "tests" / "pipeline_smoke.json"


def summarize(exam: ExamStructure) -> dict:
    subtasks = [s for t in exam.tasks for s in t.subtasks]
    return dict(
        kind=exam.kind,
        solution=exam.is_solution,
        status=exam.status,
        tasks=len(exam.tasks),
        subtasks=len(subtasks),
        points=sum(t.points or 0 for t in exam.tasks),
        stated=exam.total_points_stated,
        duration=exam.duration_minutes,
        mc_rule=exam.mc_rule.kind if exam.mc_rule else None,
        mc=sum(bool(s.mc_options) for s in subtasks),
        mc_keys=sum(s.mc_key is not None for s in subtasks),
        answer_boxes=sum(len(s.answer_boxes) for s in subtasks),
        multipage=sum(len({r.page for r in s.regions}) > 1 for s in subtasks),
        issues=sorted(i.message for i in exam.issues),
    )


def run(pdf: Path) -> dict:
    try:
        return summarize(group(extract(pdf), str(pdf), pdf_path=pdf))
    except Exception as e:
        return {"crash": type(e).__name__}


def features(course: str, s: dict) -> set[str]:
    """What a PDF exercises; the selected set must cover every feature found in samples/."""
    if "crash" in s:
        return {f"course:{course}", "crash"}
    f = {f"course:{course}", f"kind:{s['kind']}", f"status:{s['status']}", f"mc_rule:{s['mc_rule']}"}
    f |= {name for name in ("solution", "mc", "mc_keys", "answer_boxes", "multipage", "duration", "stated") if s[name]}
    # "A2b: empty region" and "A3b: empty region" are the same kind of issue
    f |= {"issue:" + re.sub(r"\[.*\]|\d+(\.\d+)?|^\w+: ", "#", i) for i in s["issues"]}
    return f


def select(results: dict[str, dict]) -> list[str]:
    """Greedy set cover: keep adding the PDF that covers the most features still missing."""
    feats = {p: features(Path(p).parent.name, s) for p, s in results.items()}
    missing, chosen = set().union(*feats.values()), []
    while missing:
        best = max(sorted(feats), key=lambda p: len(feats[p] & missing))
        chosen.append(best)
        missing -= feats[best]
    return sorted(chosen)


def run_all(paths: list[str]) -> dict[str, dict]:
    out = {}
    for p in paths:
        t0 = time.time()
        out[p] = run(SAMPLES / p)
        print(f"{time.time() - t0:5.1f}s {p}", file=sys.stderr)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="overwrite the baseline with the current output")
    ap.add_argument("--select", action="store_true", help="re-pick the set from all of samples/")
    args = ap.parse_args()

    if args.select:
        everything = run_all(sorted(str(f.relative_to(SAMPLES)) for f in SAMPLES.rglob("*.pdf")))
        chosen = select(everything)
        BASELINE.write_text(json.dumps({p: everything[p] for p in chosen}, indent=1, ensure_ascii=False) + "\n")
        print(f"{len(chosen)} of {len(everything)} PDFs cover every feature -> {BASELINE}")
        return

    baseline = json.loads(BASELINE.read_text())
    missing = [p for p in baseline if not (SAMPLES / p).exists()]
    if missing:
        sys.exit(f"sample PDFs missing (samples/ isn't in git): {missing}")
    current = run_all(list(baseline))
    if args.update:
        BASELINE.write_text(json.dumps(current, indent=1, ensure_ascii=False) + "\n")
        print(f"baseline updated ({len(current)} PDFs)")
        return

    changed = 0
    for p, want in baseline.items():
        got = current[p]
        diff = {k: (want.get(k), got.get(k)) for k in want.keys() | got.keys() if want.get(k) != got.get(k)}
        if diff:
            changed += 1
            print(f"CHANGED {p}")
            for k, (a, b) in sorted(diff.items()):
                print(f"  {k}: {a!r} -> {b!r}")
    print(f"{len(baseline) - changed}/{len(baseline)} unchanged")
    sys.exit(1 if changed else 0)


if __name__ == "__main__":
    main()
