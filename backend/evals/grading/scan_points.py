"""Read the teacher's printed points (left margin) and the cover total from a graded scan's text layer."""

import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

_SCORE = re.compile(r"\d{1,3}[,.]\d")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
MARGIN_X = 70  # the points-overview table on one scan starts at x0=162, so keep this bound


@dataclass
class Score:
    page: int  # 0-based
    top: float
    bottom: float
    x0: float
    x1: float
    points: float


def read_scores(pdf_path: Path) -> list[Score]:
    out: list[Score] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            if i == 0:
                continue
            lines: dict[int, list[dict]] = {}
            for c in page.chars:
                if c["x0"] < MARGIN_X and c["text"] in "0123456789,.":  # watermark letters share baselines
                    lines.setdefault(round(c["bottom"]), []).append(c)
            for chars in lines.values():
                chars.sort(key=lambda c: c["x0"])
                text = "".join(c["text"] for c in chars)
                if _SCORE.fullmatch(text):
                    out.append(
                        Score(
                            i,
                            min(c["top"] for c in chars),
                            max(c["bottom"] for c in chars),
                            chars[0]["x0"],
                            chars[-1]["x1"],
                            float(text.replace(",", ".")),
                        )
                    )
    return sorted(out, key=lambda s: (s.page, s.top))


def parse_cover_total(text: str) -> float | None:
    """First number on the line after the first line containing a sigma."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "Σ" in line:
            m = _NUMBER.search(lines[i + 1]) if i + 1 < len(lines) else None
            return float(m.group().replace(",", ".")) if m else None
    return None


def read_cover_total(pdf_path: Path) -> float | None:
    with pdfplumber.open(pdf_path) as pdf:
        return parse_cover_total(pdf.pages[0].extract_text() or "")
