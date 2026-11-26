"""Step 3: render cleaned pages, cut region crops, and draw debug overlays.

Cleaning works on PDF objects (not pixels) so nothing underneath gets erased:
the watermark is hidden, and for solution PDFs also the solution ink (blue-tinted
text, strokes and fills). Objects are made transparent rather than removed, which
also works for objects nested inside form XObjects (diagrams).
"""

import ctypes
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image, ImageDraw

from .models import ExamStructure, Region

SCALE = 2.0  # 144 dpi


def _color(obj, stroke: bool = False) -> tuple[int, int, int]:
    v = [ctypes.c_uint() for _ in range(4)]
    getter = pdfium_c.FPDFPageObj_GetStrokeColor if stroke else pdfium_c.FPDFPageObj_GetFillColor
    getter(obj.raw, *(ctypes.byref(x) for x in v))
    return (v[0].value, v[1].value, v[2].value)


def _is_watermark(obj) -> bool:
    if obj.type != pdfium_c.FPDF_PAGEOBJ_TEXT:
        return False
    _, bottom, _, top = obj.get_pos()
    r, g, b = _color(obj)
    tinted = min(r, g, b) > 150 and max(r, g, b) - min(r, g, b) > 20
    return top - bottom > 40 and tinted


def _bluish(rgb: tuple[int, int, int]) -> bool:
    """Solution ink in TUM templates: pure blue text/lines and light-blue fills."""
    r, g, b = rgb
    return b - max(r, g) > 20 and abs(r - g) < 30


def _is_solution_ink(obj) -> bool:
    if obj.type == pdfium_c.FPDF_PAGEOBJ_TEXT:
        return _bluish(_color(obj))
    if obj.type == pdfium_c.FPDF_PAGEOBJ_PATH:
        return _bluish(_color(obj)) or _bluish(_color(obj, stroke=True))
    return False


def _hide(obj) -> None:
    for setter, stroke in ((pdfium_c.FPDFPageObj_SetFillColor, False), (pdfium_c.FPDFPageObj_SetStrokeColor, True)):
        setter(obj.raw, *_color(obj, stroke), 0)


def _in_any(obj, boxes: list[tuple[float, float, float, float]], page_height: float) -> bool:
    left, bottom, right, top = obj.get_pos()
    cx, cy = (left + right) / 2, page_height - (bottom + top) / 2
    return any(x0 - 1 <= cx <= x1 + 1 and y0 - 1 <= cy <= y1 + 1 for x0, y0, x1, y1 in boxes)


def render_clean_page(
    pdf: pdfium.PdfDocument, index: int, strip_solutions: bool, redact: list[tuple[float, float, float, float]] = ()
) -> Image.Image:
    page = pdf[index]
    height = page.get_height()
    for obj in page.get_objects(max_depth=5):
        if (
            _is_watermark(obj)
            or (strip_solutions and _is_solution_ink(obj))
            or redact
            and obj.level == 0
            and obj.type == pdfium_c.FPDF_PAGEOBJ_TEXT
            and _in_any(obj, redact, height)
        ):
            _hide(obj)
    return page.render(scale=SCALE).to_pil().convert("RGB")


def crop(img: Image.Image, region: Region) -> Image.Image:
    b = region.bbox
    return img.crop(tuple(int(v * SCALE) for v in (b.x0, b.y0, b.x1, b.y1)))


COLORS = ["#1f77b4", "#2ca02c", "#9467bd", "#17becf", "#bcbd22", "#8c564b"]


def render_exam(
    pdf_path: str | Path,
    exam: ExamStructure,
    out_dir: Path,
    strip_solutions: bool,
    debug: bool = True,
    redact: dict[int, list[tuple[float, float, float, float]]] | None = None,
) -> None:
    crops_dir = out_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(pdf_path))
    used_pages = sorted({r.page for t in exam.tasks for block in t.context + t.subtasks for r in block.regions})
    redact = redact or {}
    pages = {i: render_clean_page(pdf, i, strip_solutions, redact.get(i, [])) for i in used_pages}

    overlays: dict[int, list[tuple[Region, str, str]]] = {i: [] for i in pages}
    for t in exam.tasks:
        for c in t.context:
            for k, r in enumerate(c.regions):
                r.image = f"{c.id}_{k}.png"
                crop(pages[r.page], r).save(crops_dir / r.image)
                scope = f" (from {c.applies_from})" if c.applies_from else ""
                overlays[r.page].append((r, "#ff7f0e", f"{c.id}{scope}"))
        for j, s in enumerate(t.subtasks):
            for k, r in enumerate(s.regions):
                r.image = f"{s.id}_{k}.png"
                crop(pages[r.page], r).save(crops_dir / r.image)
                pts = f" [{s.points:g}P]" if s.points is not None else ""
                overlays[r.page].append((r, COLORS[j % len(COLORS)], f"{s.id} {s.label}{pts}"))

    if not debug:
        return
    dbg = out_dir / "debug"
    dbg.mkdir(exist_ok=True)
    for i, img in pages.items():
        img = img.copy()
        draw = ImageDraw.Draw(img, "RGBA")
        for r, color, label in overlays[i]:
            b = [int(v * SCALE) for v in (r.bbox.x0, r.bbox.y0, r.bbox.x1, r.bbox.y1)]
            draw.rectangle(b, outline=color, width=4)
            tw = draw.textlength(label) + 8
            draw.rectangle([b[0], b[1], b[0] + tw, b[1] + 14], fill=color)
            draw.text((b[0] + 4, b[1] + 1), label, fill="white")
        img.save(dbg / f"page_{i + 1:02d}.png")
