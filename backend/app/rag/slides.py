"""Search over a Subject's Decks: the best slides, one per printed slide label (overlay builds of a slide share a label).

A slide is scored by BM25-style term weights, with the IDF taken from the Subject's own pages, so words found on nearly every page
("wie", "ist") weigh nothing. Terms count more in the title (4), accent headings (2.5), footer section (1.5) than in the body (1).
The local embedding adds 0.3 x the best cosine of any piece of the slide, which catches paraphrases and breaks ties.
Everything is scoped to one account and one Subject."""

import math
import uuid
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Chunk, DeckPage, Document
from . import embed
from .search import MIN_SIM
from .text import tokens

WEIGHTS = {"title": 4.0, "headings": 2.5, "section": 1.5, "body": 1.0}
K1, B = 1.2, 0.5  # BM25 saturation and length normalisation (0.5: slides repeat one title, so a short build must not beat the full one)
BLEND = 0.3
POOL = 300  # nearest pieces taken per query for the embedding side
AGENDA = {
    "agenda",
    "inhalt",
    "inhaltsverzeichnis",
    "uebersicht",
    "ueberblick",
    "overview",
    "zusammenfassung",
    "summary",
    "outline",
    "contents",
    "gliederung",
    "literatur",
    "literaturangaben",
}
AGENDA_FACTOR = 0.5  # agenda and summary pages list every topic of a chapter; they must not outrank the page that explains one


@dataclass
class SlideHit:
    document_id: uuid.UUID
    deck: str
    label: str | None
    page: int  # the build that shows the whole slide
    title: str
    sim: float  # best embedding cosine of the slide
    weak: bool  # no term in title, headings or section, and the embedding is not close either
    terms: list[str]  # the query words found on the slide (the viewer highlights them)


@dataclass
class _Unit:
    document_id: uuid.UUID
    deck: str
    label: str | None
    page: int
    title: str
    pages: set[int]
    tf: dict[str, Counter]
    agenda: bool

    def length(self, field: str) -> int:
        return sum(self.tf[field].values())


def _unique(items) -> list[str]:
    return list(dict.fromkeys(i for i in items if i))


def _units(db: Session, user_id: uuid.UUID, course: uuid.UUID) -> list[_Unit]:
    rows = db.execute(
        select(DeckPage, Document.title)
        .join(Document, DeckPage.document_id == Document.id)
        .where(Document.user_id == user_id, Document.course_id == course)
        .order_by(Document.position, Document.created_at, DeckPage.page)
    ).all()
    groups: dict[tuple, list[tuple[DeckPage, str]]] = {}
    for p, deck in rows:
        groups.setdefault((p.document_id, p.label or p.page), []).append((p, deck))
    units = []
    for group in groups.values():
        pages = [p for p, _ in group]
        best = max(pages, key=lambda p: len(p.body))  # builds add to a slide, so the fullest one shows all of it
        titles = _unique(p.title for p in pages)
        lines = _unique(ln for p in pages for ln in p.body.splitlines())
        text = {
            "title": " ".join(titles),
            "headings": " ".join(_unique(h for p in pages for h in p.headings if h not in titles)),  # a heading that repeats the title adds nothing
            "section": next((p.section for p in pages if p.section), ""),
            "body": " ".join(lines),
        }
        units.append(
            _Unit(
                best.document_id,
                group[0][1],
                best.label,
                best.page,
                titles[0] if titles else (lines[0][:80] if lines else f"Page {best.page}"),
                {p.page for p in pages},
                {f: Counter(tokens(t)) for f, t in text.items()},
                bool(AGENDA & set(tokens(text["title"]))),
            )
        )
    return units


def _match(q: str, w: str) -> bool:
    """Same word, or one is the other plus an ending of up to 3 letters (domaene / domaenen), or a name with a digit missing one
    letter (ip4 / ipv4). Short words must match exactly."""
    if q == w:
        return True
    if len(q) + 1 == len(w) and q[-1].isdigit() and any(w == q[:i] + c + q[i:] for i in range(1, len(q)) for c in "abcdefghijklmnopqrstuvwxyz"):
        return True
    if len(q) < 4 or len(w) < 4:
        return False
    short, long = sorted((q, w), key=len)
    return long.startswith(short) and len(long) - len(short) <= 3


def _lexical(units: list[_Unit], query: str) -> tuple[list[float], list[bool], list[list[str]]]:
    """(score, found in title/headings/section, query words found) per unit."""
    terms = _unique(t for t in tokens(query) if len(t) > 1)
    vocab = {w for u in units for c in u.tf.values() for w in c}
    avg = {f: (sum(u.length(f) for u in units) / len(units)) or 1 for f in WEIGHTS}
    score, head, found = [0.0] * len(units), [False] * len(units), [[] for _ in units]
    for t in terms:
        words = {w for w in vocab if _match(t, w)}
        tfs = [{f: sum(u.tf[f][w] for w in words) for f in WEIGHTS} for u in units]
        df = sum(1 for tf in tfs if any(tf.values()))
        idf = math.log(1 + (len(units) - df + 0.5) / (df + 0.5))
        for i, (u, tf) in enumerate(zip(units, tfs, strict=True)):
            if any(tf.values()):
                found[i].append(t)
            for f, weight in WEIGHTS.items():
                if tf[f]:
                    norm = 1 - B + B * u.length(f) / avg[f]
                    score[i] += idf * weight * tf[f] * (K1 + 1) / (tf[f] + K1 * norm)
                    head[i] = head[i] or f != "body"
    return [s * AGENDA_FACTOR if u.agenda else s for s, u in zip(score, units, strict=True)], head, found


def _similarity(db: Session, user_id: uuid.UUID, course: uuid.UUID, queries: list[str]) -> dict[tuple[uuid.UUID, int], float]:
    best: dict[tuple[uuid.UUID, int], float] = {}
    for vec in embed.embed(queries):
        dist = Chunk.embedding.cosine_distance(vec)
        q = (
            select(Chunk.document_id, Chunk.page, 1 - dist)
            .join(Document, Chunk.document_id == Document.id)
            .where(Document.user_id == user_id, Document.course_id == course)
            .order_by(dist)
            .limit(POOL)
        )
        for doc, page, sim in db.execute(q):
            best[doc, page] = max(best.get((doc, page), 0.0), float(sim))
    return best


def search_slides(db: Session, user_id: uuid.UUID, course: uuid.UUID, queries: list[str], k: int = 5) -> list[SlideHit]:
    """The `k` best slides of the Subject for these queries, best first. Weak ones are flagged, never hidden."""
    queries = [q.strip() for q in queries if q.strip()]
    # shortcut: pages are read and tokenised on every search, fine for a few thousand pages; cache per Subject if it is slow
    units = _units(db, user_id, course) if queries else []
    if not units:
        return []
    lex, head, found = _lexical(units, " ".join(queries))
    top = max(lex) or 1.0
    sims = _similarity(db, user_id, course, queries)
    scored = []
    for u, s, in_head, terms in zip(units, lex, head, found, strict=True):
        sim = max((sims.get((u.document_id, p), 0.0) for p in u.pages), default=0.0)
        score = s / top + BLEND * sim
        if score > 0:
            scored.append((score, SlideHit(u.document_id, u.deck, u.label, u.page, u.title, sim, not in_head and sim < MIN_SIM, terms)))
    scored.sort(key=lambda x: -x[0])
    return [h for _, h in scored[:k]]
