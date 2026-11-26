"""Optional docling pass: formulas become `$LaTeX$` lines before grouping.

Formulas run on the MLX engine (Apple Silicon, ~2 s each); the CPU engine costs ~60 s per formula and is never
used, so without `mlx_vlm` nothing runs. Tables stay off: docling got 1 of 3 right.
"""

import importlib.util
import logging
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from .extract import Line, Page

log = logging.getLogger(__name__)

MAX_LATEX = 2000
INLINE_COVERAGE = 0.8


@dataclass
class Enriched:
    page: int  # 0-based, like Page.index
    bbox: tuple[float, float, float, float]  # x0, top, x1, bottom in PDF points, top-left origin
    kind: Literal["formula"]
    text: str | None


_converter = None


def available() -> bool:
    return importlib.util.find_spec("mlx_vlm") is not None


def valid_latex(s: str) -> bool:
    """Model output is a hint: reject what looks truncated or runaway."""
    if not s.strip() or len(s) > MAX_LATEX:
        return False
    plain = re.sub(r"\\[\\{}$]", "", s)  # escaped \\ \{ \} \$
    if plain.count("{") != plain.count("}") or "$" in plain:
        return False
    if len(re.findall(r"\\left\b", s)) != len(re.findall(r"\\right\b", s)):
        return False
    tokens = re.findall(r"\\[a-zA-Z]+|\\.|\S", s)
    return not any(len(set(tokens[i : i + 4])) == 1 for i in range(len(tokens) - 3))  # 4+ identical tokens in a row


def find_items(pdf_path: str | Path, pages: set[int] | None = None) -> list[Enriched]:
    """The only place that imports docling."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.vlm_engine_options import MlxVlmEngineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    global _converter
    if _converter is None:  # the model loads once per process
        opts = PdfPipelineOptions(do_ocr=False, do_table_structure=False, do_formula_enrichment=True)
        opts.code_formula_options.engine_options = MlxVlmEngineOptions()
        _converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    conv = _converter
    doc = conv.convert(str(pdf_path)).document
    out: list[Enriched] = []
    for item in doc.texts:
        label = item.label.value
        if label != "formula" or not item.prov:
            continue
        prov = item.prov[0]
        if pages is not None and prov.page_no - 1 not in pages:
            continue
        b = prov.bbox.to_top_left_origin(doc.pages[prov.page_no].size.height)
        out.append(Enriched(prov.page_no - 1, (b.l, b.t, b.r, b.b), "formula", item.text))
    return out


def _digits(hit: list[Line]) -> Counter:
    raw = " ".join(ln.text for ln in hit)
    raw = re.sub(r"\(cid:\d+\)", "", raw)
    raw = re.sub(r"\(\d+(?:\.\d+)*\)\s*$", "", raw.strip())  # trailing equation number
    return Counter(re.findall(r"\d", raw))


def _digits_latex(s: str) -> Counter:
    return Counter(re.findall(r"\d", s))


def _center_in(ln: Line, b: tuple[float, float, float, float]) -> bool:
    return b[0] <= (ln.x0 + ln.x1) / 2 <= b[2] and b[1] <= (ln.top + ln.bottom) / 2 <= b[3]


def enrich_pages(pages: list[Page], items: list[Enriched]) -> None:
    by_index = {p.index: p for p in pages}
    for it in items:
        page = by_index.get(it.page)
        if page is None:
            continue
        x0, top, x1, bottom = it.bbox
        if not it.text or not valid_latex(it.text.strip().strip("$").strip()):
            continue
        hit = [ln for ln in page.lines if not ln.furniture and not ln.converted and _center_in(ln, it.bbox)]
        if not hit:
            continue
        # shortcut: an inline formula inside a text line is left to the script/font heuristics; upgrade by
        # splicing the formula into the line text when docling's inline boxes prove reliable
        if len(hit) == 1 and (hit[0].x1 - hit[0].x0) > 0 and (x1 - x0) < INLINE_COVERAGE * (hit[0].x1 - hit[0].x0):
            continue
        if _digits(hit) - _digits_latex(it.text):  # the model dropped an entry: the text would be wrong
            continue
        first = hit[0]
        new = replace(
            first,
            text=f"${it.text.strip().strip('$').strip()}$",
            x0=x0,
            top=top,
            x1=x1,
            bottom=bottom,
            converted=True,
            scripts=False,
            scripts_uncertain=False,
            raw_len=sum(ln.raw_len for ln in hit),
            fonts=frozenset({first.font}),
        )  # not the math-structure fonts: the text carries it
        ids = {id(ln) for ln in hit}
        i = page.lines.index(first)
        page.lines = [ln for ln in page.lines if id(ln) not in ids]
        page.lines.insert(min(i, len(page.lines)), new)


def enrich(pdf_path: str | Path, pages: list[Page]) -> None:
    """Never raises: enrichment is an optional improvement."""
    if not available():
        log.info("enrich skipped: mlx_vlm not installed")
        return
    try:
        enrich_pages(pages, find_items(pdf_path))
    except Exception as e:
        log.warning("enrich failed: %s", type(e).__name__)
