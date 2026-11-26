"""Offline grading eval: grade exported cases with a real provider and report how close the points are to the expected ones.

Run from backend/: uv run python -m evals.grading.run_eval --provider google evals/grading/cases.jsonl
"""

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from app.grading.grader import GradingError, grade
from app.grading.models import DEFAULT_MODEL, GradeIn, GradeOut
from app.grading.prompt import PROMPT_VERSION

KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "google": "GOOGLE_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
RESULTS = Path(__file__).parent / "results"


def metrics(rows: list[tuple[float, GradeOut]]) -> dict:
    n = len(rows)
    exact = [abs(o.points - e) < 1e-9 for e, o in rows]
    certain = [x for x, (_, o) in zip(exact, rows) if o.certain]
    return {
        "n": n,
        "exact": sum(exact) / n if n else None,
        "in_range": sum(o.points_min <= e <= o.points_max for e, o in rows) / n if n else None,
        "mae": sum(abs(o.points - e) for e, o in rows) / n if n else None,
        "calibration": sum(certain) / len(certain) if certain else None,
    }


def _fmt(v):
    return "-" if v is None else f"{v:.2f}" if isinstance(v, float) else str(v)


def main(argv=None) -> Path:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", type=Path)
    ap.add_argument("--provider", default="anthropic", choices=list(KEY_ENV))
    ap.add_argument("--model")
    args = ap.parse_args(argv)
    key = os.environ.get(KEY_ENV[args.provider])
    if not key:
        sys.exit(f"Set {KEY_ENV[args.provider]} first.")
    model = args.model or DEFAULT_MODEL[args.provider]

    cases = [json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]
    rows: dict[str, list[tuple[float, GradeOut]]] = {}
    failures: Counter[str] = Counter()

    async def run():
        # shortcut: cases run one after another, upgrade to bounded gather when a run takes too long
        for c in cases:
            req = GradeIn.model_validate({**c["request"], "provider": args.provider, "model": model})
            # a case with a solution is graded twice: against it and in own_solution mode
            for r in [req, req.model_copy(update={"solution": None})] if req.solution else [req]:
                try:
                    out = await grade(r, key)
                except GradingError as e:
                    failures[e.code] += 1
                    continue
                rows.setdefault(out.basis, []).append((c["expected"], out))

    asyncio.run(run())

    lines = [
        f"# Grading eval {date.today()}",
        "",
        f"- provider: {args.provider}",
        f"- model: {model}",
        f"- prompt version: {PROMPT_VERSION}",
        f"- cases: {len(cases)}",
        "",
        "| basis | n | exact | in_range | mae | calibration |",
        "|---|---|---|---|---|---|",
    ]
    for basis, r in sorted(rows.items()):
        m = metrics(r)
        lines.append(f"| {basis} | " + " | ".join(_fmt(m[k]) for k in ("n", "exact", "in_range", "mae", "calibration")) + " |")
    lines += ["", "## Failures", ""]
    lines += [f"- {code}: {n}" for code, n in sorted(failures.items())] or ["none"]

    RESULTS.mkdir(exist_ok=True)
    slug = re.sub(r"[^\w.-]+", "-", model)
    path = RESULTS / f"{date.today()}-{args.provider}-{slug}.md"
    path.write_text("\n".join(lines) + "\n")
    print(path)
    return path


if __name__ == "__main__":
    main()
