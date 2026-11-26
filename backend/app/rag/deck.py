"""Read a Deck's page structure: printed slide label, page title, footer section, accent-coloured headings and the cleaned body text.

Every signal is optional. A page that has none of them still gets its plain text, so every page of every Deck stays searchable."""

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from pdfminer.pdftypes import resolve1

from .text import clean

log = logging.getLogger(__name__)

FOOTER = 0.93  # the footer is what lies below this fraction of the page height
TITLE_ZONE = 0.15  # the title is a line in the top of the page ...
TITLE_RATIO = 1.1  # ... at least this much bigger than the page's body text
ACCENT_SHARE = 0.7  # a line is a heading when this share of its letters has the Deck's accent colour
ACCENT_PAGES = 0.25  # an accent colour must show up on this share of the pages to count
LABEL_SHARE = 0.3  # a "label" shared by more pages than this is a year or a course code, not a slide number
LABEL_RE = re.compile(r"(\d+-\d+)\s*$")


@dataclass
class PageRead:
    page: int  # 1-based
    label: str | None = None  # printed slide label from the footer, e.g. "3-21"
    title: str = ""
    section: str = ""  # footer text without the label: chapter and section
    headings: list[str] = field(default_factory=list)
    body: str = ""
    mark: tuple[int, str] | None = None  # (level, title) of the page's first PDF bookmark


def _accent(color) -> tuple[float, float, float] | None:
    """An RGB key for a saturated colour; None for black, white, greys and anything unreadable."""
    try:
        v = tuple(float(x) for x in ((color,) if isinstance(color, (int, float)) else color))
    except (TypeError, ValueError):
        return None
    if len(v) == 4:  # CMYK
        c, m, y, k = v
        v = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    if len(v) != 3 or max(v) - min(v) < 0.2:
        return None
    return tuple(round(x, 2) for x in v)


def _bookmarks(pdf) -> dict[int, tuple[int, str]]:
    """First bookmark (level, title) per 0-based page index."""
    index = {p.page_obj.pageid: i for i, p in enumerate(pdf.pages)}
    out: dict[int, tuple[int, str]] = {}
    try:
        for level, title, dest, action, _se in pdf.doc.get_outlines():
            try:
                d = resolve1(dest) if dest else resolve1(resolve1(action).get("D"))
                if not isinstance(d, list):
                    d = resolve1(pdf.doc.get_dest(d))
                    d = d.get("D") if isinstance(d, dict) else d
                out.setdefault(index[d[0].objid], (level, clean(title).strip()))
            except Exception as e:  # one odd bookmark must not cost the others
                log.debug("bookmark skipped: %s", type(e).__name__)
    except Exception as e:  # no outline at all (PDFNoOutlines) or a broken one
        log.debug("no bookmarks: %s", type(e).__name__)
    return {i: m for i, m in out.items() if m[1]}


def _read_page(page) -> tuple[PageRead, list[tuple[str, tuple | None]], str | None]:
    """One page: its structure without accent headings, its lines as (text, accent colour), and its title line."""
    w, h = float(page.width), float(page.height)
    shown = page.filter(lambda o: o.get("object_type") != "char" or (o["size"] >= 2 and o.get("upright", True)))  # hidden and rotated text
    body = shown.crop((0, 0, w, h * FOOTER)).extract_text_lines(return_chars=True, x_tolerance=1.5)
    footer = clean(shown.crop((0, h * FOOTER, w, h)).extract_text(x_tolerance=0.8) or "").strip().split("\n")[-1]  # above it can be footnotes
    label = (m := LABEL_RE.search(footer)) and m.group(1)
    section = footer[: m.start()] if m else footer
    section = re.sub(r"^[\W_]+|[\W_]+$", "", section) if not section.strip().isdigit() else ""

    sizes = Counter()
    for ln in body:
        sizes.update(round(c["size"], 1) for c in ln["chars"] if c["text"].strip())
    base = sizes.most_common(1)[0][0] if sizes else 0
    lines, title = [], None
    for ln in body:
        text = clean(ln["text"]).strip()
        if not text:
            continue
        chars = [c for c in ln["chars"] if c["text"].strip()]
        size = Counter(round(c["size"], 1) for c in chars).most_common(1)[0][0]
        colors = Counter(_accent(c["non_stroking_color"]) for c in chars)
        color, n = colors.most_common(1)[0]
        lines.append((text, color if n / len(chars) >= ACCENT_SHARE else None))
        if title is None and ln["top"] < h * TITLE_ZONE and size >= base * TITLE_RATIO:
            title = text
    return PageRead(0, label, "", section, [], "\n".join(t for t, _ in lines)), lines, title


def read_deck(path: Path) -> list[PageRead]:
    """Every page of the PDF in order (pages without text come back empty, so the Deck counts as read)."""
    with pdfplumber.open(path) as pdf:
        marks = _bookmarks(pdf)
        read = [_read_page(p) for p in pdf.pages]
    colors = Counter(c for _, lines, _ in read for c in {c for _, c in lines if c})  # pages per colour
    accent = next((c for c, n in colors.most_common(1) if n >= max(2, ACCENT_PAGES * len(read))), None)
    labels = Counter(p.label for p, _, _ in read if p.label)
    drop_labels = len(read) >= 10 and labels and labels.most_common(1)[0][1] > LABEL_SHARE * len(read)
    out = []
    for i, (p, lines, title) in enumerate(read):
        p.page = i + 1
        p.mark = marks.get(i)
        p.title = (p.mark and p.mark[1]) or title or ""
        p.headings = [t for t, c in lines if accent and c == accent and len(t) > 2 and t != title]
        if drop_labels:
            p.label = None
        out.append(p)
    return out
