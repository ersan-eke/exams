"""Multiple-choice options (checkboxes inside a subtask's regions) and, for solution PDFs, the answer key.

Checkbox candidates come from extraction (`Page.checkboxes`: small square rects and box/circle glyphs).
Here they are cleaned up (grids of touching cells dropped, double-stroked boxes merged, pre-filled
legend boxes like "Kreuze können durch vollständiges Ausfüllen gestrichen werden ■" dropped),
put into reading order and labelled with the text printed right of them.
"""

import re
from pathlib import Path

import pypdfium2 as pdfium

from .extract import Box, Page, Word
from .models import BBox, McOption, Region
from .render import _is_solution_ink

TICK_OVERLAP = 0.3  # share of a box that solution ink must cover to count as ticked
TICK_MAX_SCALE = 3  # ink objects bigger than this many box sides are fills/frames, not ticks
CID_RE = re.compile(r"\(cid:\d+\)")  # unmapped glyphs (circle pieces of figures etc.)
LETTERS_RE = re.compile(r"[^\W\d_]")
TOUCH = 1.5  # cells closer than this belong to a grid (timetables, Gantt charts), not to MC options


def _bbox(b: Box) -> BBox:
    return BBox(x0=b.x0, y0=b.top, x1=b.x1, y1=b.bottom)


def _center(b: BBox) -> tuple[float, float]:
    return (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2


def _intersection(a: BBox, b: BBox) -> float:
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return w * h if w > 0 and h > 0 else 0.0


def _area(b: BBox) -> float:
    return max(0.0, b.x1 - b.x0) * max(0.0, b.y1 - b.y0)


def reading_order(boxes: list[BBox]) -> list[BBox]:
    """Rows first (top to bottom), then x. Boxes whose vertical centers differ by at most half a box
    height share a row, so slightly misaligned columns still read left to right."""
    rows: list[list[BBox]] = []
    for b in sorted(boxes, key=lambda b: _center(b)[1]):
        if rows and _center(b)[1] - _center(rows[-1][0])[1] <= max(3.0, 0.5 * b.height):
            rows[-1].append(b)
        else:
            rows.append([b])
    return [b for row in rows for b in sorted(row, key=lambda b: b.x0)]


def _touches(a: BBox, b: BBox) -> bool:
    v_overlap = min(a.y1, b.y1) - max(a.y0, b.y0) > 0
    h_overlap = min(a.x1, b.x1) - max(a.x0, b.x0) > 0
    side = abs(a.x1 - b.x0) < TOUCH or abs(b.x1 - a.x0) < TOUCH
    stacked = abs(a.y1 - b.y0) < TOUCH or abs(b.y1 - a.y0) < TOUCH
    return (side and v_overlap) or (stacked and h_overlap)


def candidates(page: Page) -> list[BBox]:
    """Checkbox candidates of a page without grid cells; nested boxes (frame + inner box) merged."""
    boxes = [_bbox(b) for b in page.checkboxes]
    boxes = [b for b in boxes if not any(o is not b and _touches(b, o) for o in boxes)]
    kept: list[BBox] = []
    for b in sorted(boxes, key=_area, reverse=True):
        cx, cy = _center(b)
        if not any(k.x0 - 1 <= cx <= k.x1 + 1 and k.y0 - 1 <= cy <= k.y1 + 1 for k in kept):
            kept.append(b)
    return kept


def _in_row(w: Word, b: BBox) -> bool:
    cy = (w.top + w.bottom) / 2
    return b.y0 - 2 <= cy <= b.y1 + 2


def _option_text(words: list[Word], b: BBox, boxes: list[BBox], limit: float) -> str:
    """Words on the box's line, right of it, up to the next box column (options are laid out in a
    grid, so a box in another row still bounds the column) or the region edge."""
    right = min([o.x0 for o in boxes if o.x0 >= b.x1 - 1 and o is not b] + [limit])
    return " ".join(w.text for w in words if _in_row(w, b) and w.x0 >= b.x1 - 1 and w.x1 <= right + 1 and not CID_RE.search(w.text))


def _prefilled(words: list[Word], b: BBox) -> bool:
    """A printed (non-ink) mark inside the box: an example in the ticking legend, not an option."""
    area = _area(b)
    return any(_intersection(b, BBox(x0=w.x0, y0=w.top, x1=w.x1, y1=w.bottom)) >= TICK_OVERLAP * area for w in words)


def find_options(page: Page, region: Region, region_index: int) -> list[McOption]:
    """Checkboxes inside the region in reading order, bbox relative 0..1 to the region bbox."""
    r = region.bbox
    width, height = r.x1 - r.x0, r.y1 - r.y0
    if width <= 0 or height <= 0:
        return []
    boxes = [b for b in candidates(page) if r.x0 <= _center(b)[0] <= r.x1 and r.y0 <= _center(b)[1] <= r.y1]
    words = [w for w in page.words if not w.solution_ink]
    # Page headers/footers ("Seite leer [ ]" markers next to "– Seite 2 / 16 –") are not options.
    furniture = [ln for ln in page.lines if ln.furniture and len(LETTERS_RE.findall(ln.text)) >= 3]
    options = []
    for b in reading_order(boxes):
        if _prefilled(words, b) or any(ln.top < b.y1 and ln.bottom > b.y0 for ln in furniture):
            continue
        rel = BBox(
            x0=max(0.0, (b.x0 - r.x0) / width),
            y0=max(0.0, (b.y0 - r.y0) / height),
            x1=min(1.0, (b.x1 - r.x0) / width),
            y1=min(1.0, (b.y1 - r.y0) / height),
        )
        options.append(McOption(region=region_index, bbox=rel, text=_option_text(words, b, boxes, r.x1)))
    return options


def ink_boxes(pdf_path: str | Path, page_index: int) -> list[BBox]:
    """Boxes (PDF points, top-left origin) of the solution-ink objects of one page.

    Only top-level page objects are checked: objects nested in form XObjects report positions in
    form space. TUM templates draw the ticks at top level."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[page_index]
        height = page.get_height()
        inks = []
        for obj in page.get_objects(max_depth=1):
            if obj.level == 0 and _is_solution_ink(obj):
                left, bottom, right, top = obj.get_pos()
                inks.append(BBox(x0=left, y0=height - top, x1=right, y1=height - bottom))
    finally:
        pdf.close()
    return inks


def ticked(inks: list[BBox], options_abs: list[BBox]) -> list[int]:
    """Indices of the boxes covered >= 30 % by ink marks (ink much bigger than a box is ignored)."""
    out = []
    for i, b in enumerate(options_abs):
        area = _area(b)
        marks = [ink for ink in inks if ink.x1 - ink.x0 <= TICK_MAX_SCALE * (b.x1 - b.x0) and ink.height <= TICK_MAX_SCALE * b.height]
        if area > 0 and min(area, sum(_intersection(b, m) for m in marks)) >= TICK_OVERLAP * area:
            out.append(i)
    return out


def answer_key(pdf_path: str | Path, page_index: int, options_abs: list[BBox]) -> list[int]:
    """Indices of the boxes (absolute PDF points, top-left origin) covered >= 30 % by solution ink."""
    return ticked(ink_boxes(pdf_path, page_index), options_abs)
