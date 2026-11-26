"""Text hygiene for search: `clean` repairs what PDF extraction damages, `tokens` is how both slides and questions are compared."""

import re
import unicodedata

CID_RE = re.compile(r"\(cid:\d+\)")
PRIVATE_RE = re.compile("[\ue000-\uf8ff]")
UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
WORD_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def clean(text: str) -> str:
    """Drop `(cid:N)` and private-use glyphs, and fold a stray diaeresis ("U¨bersetzen", "¨Ubung") into its letter."""
    text = PRIVATE_RE.sub("", CID_RE.sub("", text))
    text = re.sub(r"(\w)\u00a8", "\\1\u0308", text)
    text = re.sub(r"\u00a8(\w)", "\\1\u0308", text)  # shortcut: a diaeresis between two letters binds to the left one
    return unicodedata.normalize("NFC", text)


def tokens(text: str) -> list[str]:
    """Lower-case words with umlauts spelled out (ä = ae), accents and dashes dropped. A hyphenated word also gives its parts and
    its joined form, so "Count-to-Infinity", "count to infinity" and "CountToInfinity" meet."""
    text = unicodedata.normalize("NFKD", unicodedata.normalize("NFC", text).lower().translate(UMLAUTS))
    text = "".join(c for c in text if not unicodedata.combining(c)).replace("–", "-").replace("—", " ")
    out = []
    for word in WORD_RE.findall(text):
        out.append(word.replace("-", ""))
        if "-" in word:
            out.extend(word.split("-"))
    return out
