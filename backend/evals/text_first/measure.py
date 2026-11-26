"""Before/after numbers for the text-first phase: missing points, visual share, tokens per grading request, seconds.

Run from backend/: uv run python -m evals.text_first.measure ../samples [--enrich] [--limit N] [--only a,b]
Sequential on purpose (seconds per exam). Tokens: text chars/4, each sent image ceil(w*h/750) at the renderer's scale.
Works on older checkouts too (Region.visual None counts as visual; enrichment only when asked).
"""

import json
import math
import sys
import time
from pathlib import Path

from app.pipeline.extract import extract
from app.pipeline.render import SCALE
from app.pipeline.structure import group


def _tokens(regions, text: str) -> float:
    img = sum(math.ceil((r.bbox.x1 - r.bbox.x0) * (r.bbox.y1 - r.bbox.y0) * SCALE**2 / 750) for r in regions if r.visual is not False)
    return len(text) / 4 + img


def measure(root: Path, enrich: bool, pdfs: list[Path] | None = None) -> dict:
    pdfs = pdfs or sorted(root.rglob("*.pdf"))
    miss = {"mc": 0, "other": 0}
    vis = {"subtask": [0, 0], "context": [0, 0]}
    tok: list[float] = []
    secs: list[float] = []
    for pdf in pdfs:
        t0 = time.time()
        pages = extract(pdf)
        if enrich:
            from app.pipeline.enrich import enrich as run_enrich

            run_enrich(pdf, pages)
        exam = group(pages, str(pdf), pdf_path=pdf)
        secs.append(time.time() - t0)
        for t in exam.tasks:
            for s in t.subtasks:
                if s.points is None:
                    miss["mc" if s.mc_options else "other"] += 1
                vis["subtask"][0] += sum(r.visual is not False for r in s.regions)
                vis["subtask"][1] += len(s.regions)
                ctx = [c for c in t.context if c.applies_from in (None, s.id)]
                regs = [r for c in ctx for r in c.regions] + s.regions
                tok.append(_tokens(regs, "".join(c.text for c in ctx) + s.text))
            for c in t.context:
                vis["context"][0] += sum(r.visual is not False for r in c.regions)
                vis["context"][1] += len(c.regions)
    return {
        "exams": len(pdfs),
        "missing_points": miss,
        "visual_share": {k: round(a / b, 3) if b else 0 for k, (a, b) in vis.items()},
        "regions": {k: v[1] for k, v in vis.items()},
        "tokens_per_request": round(sum(tok) / max(len(tok), 1)),
        "requests": len(tok),
        "seconds_per_exam": round(sum(secs) / max(len(secs), 1), 2),
    }


if __name__ == "__main__":
    a = sys.argv[1:]
    root = Path(a[0])
    pdfs = sorted(root.rglob("*.pdf"))
    if "--only" in a:
        keys = a[a.index("--only") + 1].split(",")
        pdfs = [p for k in keys for p in pdfs if k in p.name]
    if "--limit" in a:
        pdfs = pdfs[: int(a[a.index("--limit") + 1])]
    print(json.dumps(measure(root, "--enrich" in a, pdfs)))
