"""Typing help for the Chat input: completions and a "Did you mean" drawn only from a Subject's slide titles, accent headings and footer sections."""

import difflib
import re
import unicodedata
import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import DeckPage, Document
from .slides import _match
from .text import tokens

COMPLETIONS = 6
MIN_PREFIX = 2
MIN_TYPO = 4  # shorter words are too often right: no suggestion
CUTOFF = 0.8  # difflib ratio; "kollisionsdomaene" vs a one-letter slip is ~0.95, a different word is well below


WORD = re.compile(r"[^\W_]+(?:-[^\W_]+)*")  # a hyphenated word is one word; Unicode letters and digits. Mirrors `W` in ChatPane.vue: change both


class Vocab(Counter):
    """Normalized word -> number of pages; `spelling` keeps how each was written on the slides ("groesse" -> "Größe")."""

    def __init__(self):
        super().__init__()
        self.spelling: dict[str, Counter] = {}

    def written(self, token: str) -> str:
        seen = self.spelling[token]
        return max(seen, key=seen.__getitem__)  # most frequent; a tie goes to the first seen (Counter keeps insertion order)


def _spellings(text: str):
    """(normalized word, spelling) for each word of `text` and for the parts of its hyphenated words."""
    for word in WORD.findall(unicodedata.normalize("NFC", text)):
        for piece in [word, *word.split("-")] if "-" in word else [word]:
            if t := next(iter(tokens(piece)), ""):
                yield t, piece


def vocabulary(db: Session, user_id: uuid.UUID, course: uuid.UUID) -> Vocab:
    """The words of the Subject's titles, headings and sections, counted per page (so common terms come first)."""
    # shortcut: the vocabulary is rebuilt on every request, fine for a few thousand pages; cache per Subject when typing lags
    rows = db.execute(
        select(DeckPage.title, DeckPage.headings, DeckPage.section)
        .join(Document, DeckPage.document_id == Document.id)
        .where(Document.user_id == user_id, Document.course_id == course)
    )
    vocab = Vocab()
    for title, headings, section in rows:
        pairs = [(t, w) for t, w in _spellings(" ".join([title, section or "", *headings])) if len(t) >= MIN_PREFIX and not t.isdigit()]
        vocab.update({t for t, _ in pairs})
        for t, w in pairs:
            vocab.spelling.setdefault(t, Counter())[w] += 1
    return vocab


def hints(vocab: Vocab, text: str) -> dict:
    """Completions for the word being typed (none after a space) and at most one correction for a finished word."""
    text = unicodedata.normalize("NFC", text)
    typed = WORD.findall(text)
    typing = bool(typed) and text.endswith(typed[-1])  # not after a space or a dangling hyphen
    prefix = tokens(typed.pop())[:1] if typing else []
    completions = []
    if prefix and len(prefix[0]) >= MIN_PREFIX:
        found = [w for w in vocab if w.startswith(prefix[0]) and w != prefix[0]]
        completions = [vocab.written(w) for w in sorted(found, key=lambda w: (-vocab[w], w))[:COMPLETIONS]]
    for raw in typed:
        word = next(iter(tokens(raw)), "")
        if (
            len(word) >= MIN_TYPO
            and not any(_match(word, w) for w in vocab)
            and (close := difflib.get_close_matches(word, vocab, n=1, cutoff=CUTOFF))
        ):
            return {"completions": completions, "suggestion": {"word": raw, "to": vocab.written(close[0])}}
    return {"completions": completions, "suggestion": None}
