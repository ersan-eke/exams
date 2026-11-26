from pathlib import Path

from .enrich import enrich as run_enrich
from .extract import extract
from .models import ExamStructure
from .render import render_exam
from .structure import group


def _redact_map(pages) -> dict[int, list[tuple[float, float, float, float]]]:
    return {p.index: [(b.x0, b.top, b.x1, b.bottom) for b in p.redact] for p in pages}


def render_variants(pdf_path: str | Path, exam: ExamStructure, pages, out_dir: str | Path, ink: bool) -> dict[str, Path | None]:
    """Render blank crops (solution ink hidden if exam.is_solution) and optionally crops with ink.
    Returns {"blank": crops_dir, "ink": crops_dir | None}."""
    out_dir = Path(out_dir)
    redact = _redact_map(pages)
    render_exam(pdf_path, exam, out_dir / "blank", strip_solutions=exam.is_solution, debug=False, redact=redact)
    result: dict[str, Path | None] = {"blank": out_dir / "blank" / "crops", "ink": None}
    if ink:
        render_exam(pdf_path, exam, out_dir / "ink", strip_solutions=False, debug=False, redact=redact)
        result["ink"] = out_dir / "ink" / "crops"
    return result


def process(
    pdf_path: str | Path, out_dir: str | Path, strip_solutions: bool | None = None, debug: bool = True, enrich: bool = False
) -> ExamStructure:
    """PDF -> exam structure + crop images (+ debug overlays) in out_dir."""
    out_dir = Path(out_dir)
    pages = extract(pdf_path)
    if enrich:
        run_enrich(pdf_path, pages)
    exam = group(pages, str(pdf_path), pdf_path=pdf_path)
    if exam.tasks:
        strip = exam.is_solution if strip_solutions is None else strip_solutions
        redact = _redact_map(pages)
        render_exam(pdf_path, exam, out_dir, strip_solutions=strip, debug=debug, redact=redact)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "exam.json").write_text(exam.model_dump_json(indent=2))
    return exam
