"""Turn graded exam scans plus their solution PDFs into grading-eval cases (cases.jsonl, coverage.md, contact-sheet.png)."""

import base64
import io
import json
import random
import re
import sys
from pathlib import Path

import pypdfium2
from PIL import Image

from app.grading.models import GradeIn, Part, Solution
from app.pipeline import render_variants
from app.pipeline.extract import extract
from app.pipeline.models import ExamStructure
from app.pipeline.structure import group
from evals.grading.scan_crop import clean_crop
from evals.grading.scan_points import Score, read_cover_total, read_scores

DPI = 150
DROP = {"sol", "solution"}


def _tokens(path: Path) -> set[str]:
    toks = {"gdb" if t == "gbd" else t for t in re.split(r"[-_]", path.stem.lower()) if t}
    return toks - DROP


def find_pairs(folder: Path) -> list[tuple[str, Path, Path | None]]:
    """(alias, scan, solution or None when the best match is a tie or has no overlap)."""
    pdfs = sorted((p for p in folder.glob("*.pdf")), key=lambda p: p.name.lower())
    is_sol = lambda p: bool(DROP & set(re.split(r"[-_]", p.stem.lower())))
    scans = [p for p in pdfs if not is_sol(p)]
    sols = [p for p in pdfs if is_sol(p)]
    out = []
    for i, scan in enumerate(scans, 1):
        a = _tokens(scan)
        ranked = sorted(((len(a & _tokens(s)) / len(a | _tokens(s)), s) for s in sols), key=lambda x: -x[0])
        best = ranked[0] if ranked and ranked[0][0] > 0 else None
        tie = best and len(ranked) > 1 and ranked[1][0] == best[0]
        out.append((f"exam-{i:02d}", scan, None if tie or not best else best[1]))
    return out


def _subtasks(exam: ExamStructure):
    return [s for t in exam.tasks for s in t.subtasks]


def match(scores: list[Score], exam: ExamStructure) -> dict[str, float]:
    found: dict[str, list[float]] = {}
    for sc in scores:
        y = (sc.top + sc.bottom) / 2
        for s in _subtasks(exam):
            if any(r.page == sc.page - 1 and r.bbox.y0 - 6 <= y <= r.bbox.y1 for r in s.regions):
                found.setdefault(s.id, []).append(sc.points)
                break
    return {k: v[0] for k, v in found.items() if len(v) == 1}


def mapping_ok(scores: list[Score], exam: ExamStructure, cover_total: float | None, n_scan_pages: int) -> bool:
    if n_scan_pages < exam.page_count + 1 or cover_total is None:
        return False
    return abs(sum(match(scores, exam).values()) - cover_total) < 1e-6


def render_page(scan: Path, index: int) -> Image.Image:
    if index <= 0:
        raise ValueError("scan page 0 is the cover")
    return pypdfium2.PdfDocument(str(scan))[index].render(scale=DPI / 72).to_pil()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _file_b64(d: Path, name: str | None) -> list[str]:
    return [_b64((d / name).read_bytes())] if name else []


def build_cases(alias, scan, exam, pages, scores, points, blank_dir, ink_dir) -> list[dict]:
    imgs: dict[int, Image.Image] = {}
    cases = []
    for s in _subtasks(exam):
        if s.mc_key is not None or s.id not in points or not s.points:
            continue
        if points[s.id] > s.points:  # pipeline read the max wrong
            continue
        # shortcut: a question-line-only region has no answer area; upgrade when the pipeline links answer areas outside the subtask region
        if sum(r.bbox.y1 - r.bbox.y0 for r in s.regions) < 45:
            continue
        answers = []
        for r in s.regions:
            if r.page + 1 <= 0:
                raise ValueError("never use the cover page")
            if r.page + 1 not in imgs:
                imgs[r.page + 1] = render_page(scan, r.page + 1)
            img = imgs[r.page + 1]
            whiten = [(b.x0 - 8, b.top, b.x1 + 8, b.bottom) for b in pages[r.page].grading_boxes]
            whiten += [(c.x0 - 2, c.top - 2, c.x1 + 2, c.bottom + 2) for c in scores if c.page == r.page + 1]
            size = (img.width * 72 / DPI, img.height * 72 / DPI)
            answers.append(_b64(clean_crop(img, (r.bbox.x0, r.bbox.y0, r.bbox.x1, r.bbox.y1), size, whiten)))
        question = [i for r in s.regions if r.visual is not False for i in _file_b64(blank_dir, r.image)]
        solution = [i for r in s.regions for i in _file_b64(ink_dir, r.image)]
        request = GradeIn(
            points=s.points,
            question=Part(text=s.text, images=question),
            solution=Solution(text=s.solution_text, images=solution),
            answer=Part(images=answers),
        )
        cases.append({"id": f"{alias}/{s.id}", "expected": float(points[s.id]), "request": request.model_dump(mode="json", exclude_none=True)})
    return cases


def _contact_sheet(cases: list[dict], path: Path, cols=4, cell=(300, 200)) -> None:
    crops = [c["request"]["answer"]["images"][0] for c in cases if c["request"]["answer"]["images"]]
    picked = random.Random(0).sample(crops, min(24, len(crops)))
    sheet = Image.new("RGB", (cols * cell[0], max(1, -(-len(picked) // cols)) * cell[1]), "white")
    for i, b in enumerate(picked):
        im = Image.open(io.BytesIO(base64.b64decode(b))).convert("RGB")
        im.thumbnail(cell)
        sheet.paste(im, ((i % cols) * cell[0], (i // cols) * cell[1]))
    sheet.save(path)


def _import_one(alias, scan, sol, folder) -> tuple[str, list[dict], int, int]:
    """status, cases, skipped MC, unmatched."""
    pages = extract(sol)
    exam = group(pages, sol.name, pdf_path=sol)
    scores, cover = read_scores(scan), read_cover_total(scan)
    n = len(pypdfium2.PdfDocument(str(scan)))
    pts = match(scores, exam)
    if n < exam.page_count + 1:
        return "excluded: too few pages", [], 0, 0
    if not mapping_ok(scores, exam, cover, n):
        return f"excluded: sum mismatch (parsed {sum(pts.values()):g} vs cover {cover})", [], 0, 0
    work = folder / "work" / alias
    dirs = render_variants(sol, exam, pages, work, ink=True)
    cases = build_cases(alias, scan, exam, pages, scores, pts, dirs["blank"], dirs["ink"])
    subs = _subtasks(exam)
    mc = sum(s.mc_key is not None for s in subs)
    return "ok", cases, mc, sum(s.mc_key is None for s in subs) - len(cases)


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    folder = Path(argv[0] if argv else "evals/grading/private")
    if not folder.is_dir():
        sys.exit(f"folder not found: {folder}")
    pairs = find_pairs(folder)
    if not pairs:
        sys.exit(f"no scans (*.pdf without a sol/solution token) in {folder}")
    all_cases, rows = [], ["| alias | scan | solution | status | cases | skipped MC | unmatched |", "|---|---|---|---|---|---|---|"]
    for alias, scan, sol in pairs:
        status, cases, mc, un = ("unpaired", [], 0, 0) if sol is None else _import_one(alias, scan, sol, folder)
        all_cases += cases
        rows.append(f"| {alias} | {scan.name} | {sol.name if sol else '-'} | {status} | {len(cases)} | {mc} | {un} |")
        print(f"{alias}: {status}, {len(cases)} cases")
    (folder / "cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in all_cases))
    (folder / "coverage.md").write_text("\n".join(rows) + "\n")
    _contact_sheet(all_cases, folder / "contact-sheet.png")


if __name__ == "__main__":
    main()
