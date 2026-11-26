"""Exam-level metadata parsed from front-matter text: duration and multiple-choice grading rule.

Regexes tolerate missing spaces between words, since some PDFs lose them.
"""

import re

from .models import McRule

TIME_RANGE_RE = re.compile(r"Uhrzeit\W*(\d{1,2})[:.](\d{2})\s*(?:[–—-]|bis)\s*(\d{1,2})[:.](\d{2})", re.IGNORECASE)
_MIN = r"\D{0,40}?(\d{2,3})\s*(?:Minuten|Min\b|minutes)"
# Specific keywords win over the generic fallback (e.g. "Zeit pro Aufgabe ca. 20 Minuten").
MINUTES_RES = [
    re.compile(r"(?:Arbeitszeit|Bearbeitungszeit|Dauer\s*der\s*(?:Klausur|Prüfung)|working\s*time|duration)" + _MIN, re.IGNORECASE),
    re.compile(r"(?:Zeit|Dauer|time)" + _MIN, re.IGNORECASE),
]
TICK_RE = re.compile(
    r"(-?\d+(?:[.,]\d+)?)\s*Punkte?n?\s*pro\s*richtig\w*\s*(?:\w+\s*)?und\s*([-–−]?\s*\d+(?:[.,]\d+)?)\s*Punkte?n?\s*pro\s*falsch", re.IGNORECASE
)
# "• Richtige Antwort: 1 Punkt • Falsche Antwort: −1 Punkt • Keine Antwort: 0 Punkte" (Eidi)
SCHEME_RE = re.compile(
    r"Richtige\s*Antwort\w*\s*:\s*(\d+(?:[.,]\d+)?)\s*Punkte?n?\W{0,8}Falsche\s*Antwort\w*\s*:\s*([-–−]?\s*\d+(?:[.,]\d+)?)\s*Punkt", re.IGNORECASE
)
FLOOR_RE = re.compile(r"minimale\s*Punktzahl[^.\d-]{0,40}?([-–−]?\s*\d+(?:[.,]\d+)?)\s*Punkt", re.IGNORECASE)
ALL_RE = re.compile(
    r"(?:Multiple\s*Choice|mehrere\s*Antwort\w*)[^.]{0,80}?(?:alle\s*Antworten|alle\s*Kreuze)[^.]{0,60}?(?:korrekt|richtig)", re.IGNORECASE
)
# "Single Answer mit 1 Punkt wenn richtig beantwortet und 0 Punkten sonst" (grnvs);
# "Sie erhalten diesen, wenn alle Antwortmöglichkeiten korrekt gewählt sind" (theo)
ALL_DE_RE = re.compile(
    r"Single\s*Answer\s*mit\s*\d+(?:[.,]\d+)?\s*Punkte?n?\s*wenn\s*richtig\w*(?:\s*beantwortet)?\s*und\s*0\s*Punkte?n?\s*sonst"
    r"|wenn\s*alle\s*Antwort\w*\s*korrekt",
    re.IGNORECASE,
)
# "If the wrong answer or multiple answers are marked, no credit will be given."
ALL_EN_RE = re.compile(r"(?:wrong\s*answer|multiple\s*answers|more\s*than\s*one\s*answer)[^.]{0,80}?no\s*(?:credits?|points?)", re.IGNORECASE)


def _f(s: str) -> float:
    return float(s.replace(" ", "").replace(",", ".").replace("–", "-").replace("−", "-"))


def parse_duration(texts: list[str]) -> int | None:
    blob = "\n".join(texts)
    if m := TIME_RANGE_RE.search(blob):
        a = int(m.group(1)) * 60 + int(m.group(2))
        b = int(m.group(3)) * 60 + int(m.group(4))
        if 0 < b - a <= 600:
            return b - a
    for rx in MINUTES_RES:
        if m := rx.search(blob):
            return int(m.group(1))
    return None


def parse_mc_rule(texts: list[str]) -> McRule | None:
    blob = " ".join(texts)
    if m := TICK_RE.search(blob):
        floor = FLOOR_RE.search(blob)
        # "pro falsch" is always a deduction, even when the PDF lost the minus sign
        return McRule(kind="per_tick", right=_f(m.group(1)), wrong=-abs(_f(m.group(2))), floor=_f(floor.group(1)) if floor else 0)
    if m := SCHEME_RE.search(blob):
        return McRule(kind="per_tick", right=_f(m.group(1)), wrong=-abs(_f(m.group(2))))
    if ALL_RE.search(blob) or ALL_EN_RE.search(blob) or ALL_DE_RE.search(blob):
        return McRule(kind="all_or_nothing")
    return None
