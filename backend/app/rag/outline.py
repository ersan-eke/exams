"""A Deck's automatic Outline: two levels, built from the best structure the Deck has, no key needed.

Source order: PDF bookmarks; else the footer chapter/section when it repeats across pages (section = level 1, page titles = level 2);
else title-size headings (equal consecutive titles merged) in blocks of pages; else "Page N" in blocks of pages.
An entry is {"title", "page", "children": [{"title", "page"}]}."""

from collections import Counter

from pydantic import BaseModel

from ..grading.prompt import Text
from .deck import PageRead

BLOCK = 10  # shortcut: decks without sections are cut into fixed blocks of pages; use the printed chapter numbers if they show up in the titles


def _leaf(title: str, page: int) -> dict:
    return {"title": title, "page": page}


def _titles(pages: list[PageRead], *, fallback: bool) -> list[dict]:
    """Page titles in order. Equal consecutive titles merge and untitled pages belong to the title before them; with `fallback` a
    leading untitled page is named "Page N" (so a block never comes out empty)."""
    out: list[dict] = []
    for p in pages:
        if p.title and not (out and out[-1]["title"] == p.title):
            out.append(_leaf(p.title, p.page))
        elif not p.title and not out and fallback:
            out.append(_leaf(f"Page {p.page}", p.page))
    return out


def _bookmarks(pages: list[PageRead]) -> list[dict]:
    marked = [p for p in pages if p.mark]
    if not marked:
        return []
    top = min(p.mark[0] for p in marked)
    out: list[dict] = []
    for p in marked:
        level, title = p.mark
        if level == top or not out:  # a deeper entry before any top one stands on its own
            out.append({**_leaf(title, p.page), "children": []})
        else:
            out[-1]["children"].append(_leaf(title, p.page))  # shortcut: levels below 2 are flattened into level 2
    return out


def _footer(pages: list[PageRead]) -> list[dict]:
    sections = [p.section for p in pages]
    common = Counter(s for s in sections if s).most_common(1)
    if not common or common[0][1] < 2 or 2 * sum(map(bool, sections)) < len(pages):
        return []
    first = next(s for s in sections if s)
    filled, last = [], first  # pages without a footer belong to the section before them
    for s in sections:
        last = s or last
        filled.append(last)
    out: list[dict] = []
    for p, s in zip(pages, filled, strict=True):
        if not out or out[-1]["title"] != s:
            out.append({**_leaf(s, p.page), "children": []})
        out[-1]["children"].append(p)
    for e in out:
        e["children"] = _titles(e["children"], fallback=False)
    return out


def _blocks(pages: list[PageRead]) -> list[dict]:
    titled = any(p.title for p in pages)
    out = []
    for i in range(0, len(pages), BLOCK):
        chunk = pages[i : i + BLOCK]
        a, b = chunk[0].page, chunk[-1].page
        kids = _titles(chunk, fallback=True) if titled else [_leaf(f"Page {p.page}", p.page) for p in chunk]
        out.append({**_leaf(f"Page {a}" if a == b else f"Pages {a}–{b}", a), "children": kids})
    return out


def build_outline(pages: list[PageRead]) -> list[dict]:
    return _bookmarks(pages) or _footer(pages) or _blocks(pages)


# --- AI Outline: the student's LLM names the structure from page titles and openings only ---

MAX_TITLE = 100
MAX_ENTRIES = 200  # per level
SNIPPET = 200  # characters of each page's text that go to the LLM

SYSTEM = """You structure a lecture Deck for a student. You get every page as "page number | title | opening of the text". Reply with a \
two-level table of contents: sections (level 1) each with sub-entries (level 2). Every entry has a short title and the page number it \
starts on, taken from the list; pages ascend. Titles in the language of the pages. Reply with the JSON object only."""


class AiEntry(BaseModel):
    title: str
    page: int


class AiSection(AiEntry):
    children: list[AiEntry]


class AiOutline(BaseModel):
    sections: list[AiSection]


def items(rows: list[tuple[int, str, str]]) -> list[Text]:
    """(page, automatic title, body) per page; only the title and the opening of the body are sent."""
    return [Text("\n".join(f"{page} | {title} | {' '.join(body.split())[:SNIPPET]}" for page, title, body in rows))]


def from_ai(out: AiOutline, page_count: int) -> list[dict]:
    """The model's Outline as stored: entries with a blank title or a page that does not exist are dropped, pages made ascending."""

    def keep(entries: list) -> list:  # one entry per page, ascending: the page keys the fold state in the UI
        ok = sorted((e for e in entries if e.title.strip() and 1 <= e.page <= page_count), key=lambda e: e.page)
        return list({e.page: e for e in reversed(ok)}.values())[::-1][:MAX_ENTRIES]

    def leaf(e: AiEntry) -> dict:
        return _leaf(e.title.strip()[:MAX_TITLE], e.page)

    return [{**leaf(s), "children": [leaf(c) for c in keep(s.children)]} for s in keep(out.sections)]
