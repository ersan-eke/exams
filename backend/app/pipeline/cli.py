"""Run the pipeline on PDFs or folders and write a review report.

python -m app.pipeline.cli ../samples/grnvs/grnvs_endterm_2019.pdf
python -m app.pipeline.cli ../samples --out ../debug/pipeline --limit 3
"""

import argparse
import html
import time
import traceback
from collections import defaultdict
from pathlib import Path

from . import process


def collect(paths: list[str], limit: int | None) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            by_dir: dict[Path, list[Path]] = defaultdict(list)
            for f in sorted(p.rglob("*.pdf")):
                by_dir[f.parent].append(f)
            for group in by_dir.values():
                files += group[:limit] if limit else group
        else:
            files.append(p)
    return files


def write_report(rows: list[dict], out: Path) -> Path:
    def row_html(r: dict) -> str:
        link = f'<a href="{html.escape(r["dir"])}/debug/">debug</a>' if r.get("dir") else ""
        issues = "<br>".join(html.escape(i) for i in r["issues"])
        return (
            f'<tr class="{r["status"]}"><td>{html.escape(r["course"])}</td><td>{html.escape(r["file"])}</td>'
            f"<td>{r['status']}</td><td>{r['tasks']}</td><td>{r['subtasks']}</td><td>{r['points']}</td>"
            f"<td>{'yes' if r.get('solution') else ''}</td><td>{link}</td><td>{issues}</td></tr>"
        )

    page = f"""<!doctype html><meta charset="utf-8"><title>Pipeline report</title>
<style>body{{font:13px system-ui;margin:16px}} table{{border-collapse:collapse}} td,th{{border:1px solid #ccc;padding:3px 6px;vertical-align:top}}
tr.ok td:nth-child(3){{background:#c8f7c5}} tr.warn td:nth-child(3){{background:#ffe9a8}} tr.error td:nth-child(3){{background:#f7c5c5}}</style>
<table><tr><th>course</th><th>file</th><th>status</th><th>tasks</th><th>subtasks</th><th>points</th><th>solution</th><th></th><th>issues</th></tr>
{"".join(row_html(r) for r in rows)}</table>"""
    path = out / "report.html"
    path.write_text(page)
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", default="../debug/pipeline")
    ap.add_argument("--limit", type=int, help="max PDFs per folder")
    ap.add_argument("--no-debug", action="store_true")
    ap.add_argument("--enrich", action="store_true", help="docling formulas as LaTeX (Apple Silicon, needs mlx-vlm)")
    args = ap.parse_args()

    out = Path(args.out)
    rows = []
    for f in collect(args.paths, args.limit):
        course = f.parent.name
        rel = Path(course) / f.stem
        t0 = time.time()
        try:
            exam = process(f, out / rel, debug=not args.no_debug, enrich=args.enrich)
            total = sum(t.points or 0 for t in exam.tasks)
            row = dict(
                course=course,
                file=f.name,
                status=exam.status,
                tasks=len(exam.tasks),
                subtasks=sum(len(t.subtasks) for t in exam.tasks),
                points=f"{total:g}" + (f" / {exam.total_points_stated:g}" if exam.total_points_stated else ""),
                solution=exam.is_solution,
                dir=str(rel),
                issues=[i.message for i in exam.issues],
            )
        except Exception as e:
            row = dict(
                course=course, file=f.name, status="error", tasks=0, subtasks=0, points="", issues=[f"crash: {e!r}", traceback.format_exc(limit=-2)]
            )
        rows.append(row)
        print(
            f"{row['status']:5} {time.time() - t0:5.1f}s {course}/{f.name}: {row['tasks']} tasks, "
            f"{row['subtasks']} subtasks, {row['points']}  {'; '.join(row['issues'])[:150]}"
        )

    counts = defaultdict(lambda: defaultdict(int))
    for r in rows:
        counts[r["course"]][r["status"]] += 1
    print("\ncourse     ok  warn error")
    for c, n in sorted(counts.items()):
        print(f"{c:9} {n['ok']:3} {n['warn']:5} {n['error']:5}")
    out.mkdir(parents=True, exist_ok=True)
    print(f"\nreport: {write_report(rows, out).resolve()}")


if __name__ == "__main__":
    main()
