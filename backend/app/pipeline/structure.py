"""Step 2: find task headers and subtask labels, then cut the exam into regions.

Regex only proposes candidates. They are confirmed by layout evidence:
- headers must share one dominant style (font + size) and sit at the left text edge,
- subtask labels must follow the sequence a, b, c, ... (or N.1, N.2, ...) at a consistent indent,
- the resulting points are cross-checked (subtasks vs. task header vs. total on the cover page).
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .extract import Line, Page, is_checkbox_size
from .mc import find_options, ink_boxes, ticked
from .meta import parse_duration, parse_mc_rule
from .models import AnswerBox, BBox, Context, ExamStructure, Issue, McRule, Region, Subtask, Task

HEADER_RE = re.compile(r"^(Aufgabe|Problem|Exercise|Task|Question|Frage)\s*(\d+(?:\.\d+)?)\s*[.:]?\s*(.*)$", re.IGNORECASE)
NUMBERED_HEADER_RE = re.compile(r"^(\d{1,2})\.\s+(\D.*)$")  # "8. Anfangswertproblem (ca. 8 Pkt.)"
TABLE_RE = re.compile(r"^\d+(\s+\d+)+\b")  # "Aufgabe 1 2 3 4 Ges." overview tables on cover pages
POINTS_RE = re.compile(
    r"[(\[]?\s*(?:ca\.?\s*)?(\d+(?:[.,]\d+)?)\s*(?:Punkte|Punkt|Pkt\.?|P\b|points?|pts\.?|credits?|marks?)\s*[)\]]?",
    re.IGNORECASE,
)
NUM = r"\d+(?:[.,]\d+)?"
# "2P+2P+2P+3P=9P", "(14 = 2 + 2 + 2 + 2 + 4 + 2 Punkte)", "(2+1,5+1,5 Punkte)": subtask points in order
SUM_RE = re.compile(rf"(?:({NUM})\s*=\s*)?({NUM}\s*(?:P\b)?\s*(?:\+\s*{NUM}\s*(?:P\b)?\s*)+)(?:=\s*({NUM})\s*(?:P\b)?)?")
# "je 1P = 4P", "(je 2 Punkte)", "2 points each"
EACH_RE = re.compile(rf"\bje\s*({NUM})\s*(?:Punkte?|Pkt\.?|P)\b(?:\s*=\s*({NUM}))?|({NUM})\s*(?:points?|marks?|credits?)\s*each", re.IGNORECASE)
SLASH_RE = re.compile(rf"(?:^|\s)/\s*({NUM})\s*$")  # "Kurz und Knapp /21"
BRACKET_RE = re.compile(rf"(?:^|\s)[(\[]\s*({NUM})\s*[)\]]\s*$")  # "– Grundlagen [29]", "(12)"; not "O(1)"
SLOT_RE = re.compile(rf"\[\s*/\s*({NUM})\s*\]")  # "1.2: (Un-)Gleichheit [ /3.5]"
# "(2 Punkt(e))", "(bitte ankreuzen, nur eine Antwort ist korrekt; 1 Punkt)", "(2 Punkte, Teilpunkte möglich)"
PAREN_POINTS_RE = re.compile(rf"\((?:[^()]*[;,]\s*)?({NUM})\s*(?:Punkt\(e\)|Punkte?|Pkt\.?|P\.?|points?|marks?)\s*(?:[;,][^()]*)?\)", re.IGNORECASE)
INTRO_EACH_RE = re.compile(  # theo "Pro Teilaufgabe kann 1 Punkt erreicht werden", grnvs "Single Answer mit 1 Punkt wenn richtig"
    rf"Pro\s*Teilaufgabe\s*kann\s*({NUM})\s*Punkte?n?\s*erreicht|Single\s*Answer\s*mit\s*({NUM})\s*Punkte?n?\s*wenn\s*richtig", re.IGNORECASE
)
# grnvs: "Teilaufgaben mit nur einer richtigen Antwort werden mit 1 Punkt bewertet" next to a per-tick rule
SINGLE_RE = re.compile(rf"nur\s*einer\s*richtigen\s*Antwort\s*werden\s*mit\s*({NUM})\s*Punkte?n?\s*bewertet", re.IGNORECASE)
EXCEPT_RE = re.compile(rf"Ausnahme\s*Teilaufgaben?\s*((?:[a-z]\)\s*(?:,|und)?\s*)+)mit\s*({NUM})\s*Punkte?n?\s*pro\s*Kreuz", re.IGNORECASE)
STATED_RE = re.compile(rf"({NUM})\s*(?:Punkte?n?|Pkt\.?|points?)\b", re.IGNORECASE)
LETTER_RE = re.compile(r"^(?:\(([a-z])\)|([a-z])\))\s*(\*)?\s*(?:\[\s*(\d+(?:[.,]\d+)?)\s*(?:P|Punkte|Pkt)?\.?\s*\])?")
NUMBERED_RE = re.compile(r"^(\d+)\.(\d+)\b\s*(\*)?")
END_RE = re.compile(r"^(Zusätzlicher Platz|Additional space|Platz für (Lösungen|Notizen)|Konzeptpapier|Ende der (Klausur|Prüfung))", re.IGNORECASE)
TOTAL_RE = re.compile(r"(?:Gesamtpunktzahl|insgesamt|total|maximal)\D{0,60}?(\d+(?:[.,]\d+)?)\s*(?:Punkte|points|credits)", re.IGNORECASE)
SOLUTION_NAME_RE = re.compile(r"sol|lösung|losung|lsg|loesung", re.IGNORECASE)

LABEL_INDENT = 50  # labels sit at most this far right of the page's text edge
PAD = 4
# formula, symbol and code fonts: their text comes out garbled or loses its layout
MATH_STRUCT_FONT_RE = re.compile(r"CMEX|Extension", re.IGNORECASE)  # large operators, radicals, brackets: two-dimensional math
BIG_OPERATORS = "\u2211\u220f\u222b\u221a"  # ∑ ∏ ∫ √
CHECKBOX_GLYPHS = {"(cid:3)", "(cid:2)"}  # amssymb boxes are MC checkboxes, not formulas
CODE_RE = re.compile(r"[{};]\s*$|==|\+\+|!=|->|\w\s*\[\s*\w*\s*\]")


SCRIPT_RE = re.compile(r"[_^]\{([^}]*)\}")  # markup from extract.fold_scripts; it must not count as text length


@dataclass(frozen=True)
class Pos:
    page: int
    y: float


@dataclass
class Label:
    line: Line
    label: str
    key: str  # "a" or "3" (numbered style)
    star: bool
    points: float | None


# "e)* 2 Punkte: ...", "k) 2 Punkte. ..."; the label may follow a stray line ("t\ni)* 1.5 Punkte:")
INLINE_POINTS_RE = re.compile(r"^[a-z0-9]{1,3}\)\*?\s*(\d+(?:[.,]\d+)?)\s*Punkte?\s*[:.]", re.IGNORECASE | re.MULTILINE)


def _half_step(v: float) -> bool:
    return v > 0 and abs(v * 2 - round(v * 2)) < 1e-9


def split_mc_points(task: Task) -> str | None:
    """MC tasks often print points only in the task header ("Multiple Choice (15 Punkte)") and
    note exceptions in the question ("e)* 2 Punkte: ..."). Read those notes, then share the rest
    of the header points equally among the MC subtasks still without points, if that gives 0.5 steps.
    Returns what was assumed (for the exam's issues), or None when nothing was changed."""
    subs = task.subtasks
    if task.points is None or not subs or any(not s.mc_options for s in subs):
        return None
    noted: dict[str, float] = {}
    for s in subs:
        if s.points is None and (m := INLINE_POINTS_RE.search(s.text)):
            noted[s.id] = float(m.group(1).replace(",", "."))
    if any(not _half_step(v) for v in noted.values()):
        return None
    open_ = [s for s in subs if s.points is None and s.id not in noted]
    if not open_ and not noted:
        return None
    rest = task.points - sum(s.points or 0 for s in subs) - sum(noted.values())
    share = rest / len(open_) if open_ else 0.0
    if open_ and not _half_step(share):
        return None
    if not open_ and abs(rest) > 1e-9:
        return None
    parts = []
    if noted:
        labels = {s.id: s.label for s in subs}
        parts.append(", ".join(f"{v:g} P for {labels[k]}" for k, v in noted.items()) + " from notes in the question")
    if open_:
        others = " for the others" if noted else ""
        parts.append(f"assumed {share:g} P each{others} (from {task.points:g} P task total)")
    for s in subs:
        if s.id in noted:
            s.points = noted[s.id]
        elif s.points is None:
            s.points = share
    return "; ".join(parts)


def num(s: str | None) -> float | None:
    return float(s.replace(",", ".")) if s else None


@dataclass
class HeaderPoints:
    """What a task header line says about points."""

    points: float | None = None
    title: str = ""
    parts: list[float] | None = None  # subtask points in order ("2P+2P+3P=7P")
    each: float | None = None  # every subtask ("je 1P = 4P")
    bracket: float | None = None  # "Grundlagen [29]": points only if the exam's other headers use it too
    issue: str | None = None


def header_points(rest: str) -> HeaderPoints:
    """Points and title from the text after "Aufgabe N" on the header line."""
    hp = HeaderPoints()
    if bare := re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*", rest):  # "Aufgabe 1.1   8"
        hp.points = num(bare.group(1))
        return hp
    title = rest
    m = SUM_RE.search(rest)
    # a sum only counts with a points unit ("2P+3P", "3 + 2 Punkte"): "Teil 1 + 2" is not 3 points
    if m and ("P" in m.group(0) or re.match(r"\s*(?:Punkte?|Pkt|points?)", rest[m.end() :], re.IGNORECASE)):
        parts = [float(x.replace(",", ".")) for x in re.findall(NUM, m.group(2))]
        stated = num(m.group(1) or m.group(3))
        hp.points = stated if stated is not None else sum(parts)
        if stated is not None and abs(stated - sum(parts)) > 1e-9:
            hp.issue = f"header parts {m.group(2).strip()} sum to {sum(parts):g}, header says {stated:g}"
        else:
            hp.parts = parts
        title = rest[: m.start()] + rest[m.end() :]
    if m := EACH_RE.search(rest):
        hp.each = num(m.group(1) or m.group(3))
        hp.points = hp.points if hp.points is not None else num(m.group(2))
        title = title.replace(m.group(0), "")
    if hp.points is None and (m := POINTS_RE.search(title)):
        hp.points = num(m.group(1))
    if hp.points is None and (m := SLASH_RE.search(title)):
        hp.points = num(m.group(1))
        title = title[: m.start()]
    elif hp.points is None and (m := BRACKET_RE.search(title)):
        hp.bracket = num(m.group(1))
        title = title[: m.start()]
    title = POINTS_RE.sub("", title)
    hp.title = re.sub(r"[(\[]\s*(?:Punkte?|P)?\s*[)\]]", "", title).strip(" -–:.()[]")
    return hp


def apply_header_points(task: Task, hp: HeaderPoints) -> list[str]:
    """Header parts or a per-subtask value for the subtasks in order. Printed subtask points win;
    a disagreement is returned as an issue, as is a part count that doesn't match the subtasks."""
    subs, msgs = task.subtasks, []
    if hp.issue:
        msgs.append(f"{task.id}: {hp.issue}")
    values = hp.parts
    if values is None and hp.each is not None:
        if task.points is not None and abs(hp.each * len(subs) - task.points) > 1e-9:
            return msgs + [f"{task.id}: {hp.each:g} P each for {len(subs)} subtasks is not the header's {task.points:g} P"]
        values = [hp.each] * len(subs)
    if values is None:
        return msgs
    if len(values) != len(subs):
        return msgs + [f"{task.id}: header lists {len(values)} parts for {len(subs)} subtasks"]
    for s, v in zip(subs, values):
        if s.points is None:
            s.points = v
        elif abs(s.points - v) > 1e-9:
            msgs.append(f"{s.id}: printed {s.points:g} P, header says {v:g} P")
    return msgs


def inline_points(text: str) -> float | None:
    """A point value stated in the question itself ("... nicht korrekt? (2 Punkt(e))", "[ /3.5]")."""
    head = " ".join(text.splitlines()[:3])
    m = SLOT_RE.search(head) or PAREN_POINTS_RE.search(head)
    return num(m.group(1)) if m else None


def two_value_split(task: Task, values: list[float]) -> str | None:
    """The user's rule: total T over N questions with exactly two stated values p1 < p2 gives a unique
    split n2 = (T - N p1) / (p2 - p1); the first N - n2 questions get p1, the last n2 get p2."""
    # shortcut: assumes the cheap questions come first (the user's rule); read per-question hints if an exam orders them otherwise
    subs = task.subtasks
    vals = sorted(set(values))
    if task.points is None or len(vals) != 2 or any(s.points is not None for s in subs):
        return None
    p1, p2 = vals
    n2 = (task.points - len(subs) * p1) / (p2 - p1)
    if abs(n2 - round(n2)) > 1e-9 or not 0 < round(n2) < len(subs):  # all one value: the even split's job
        return None
    for i, s in enumerate(subs):
        s.points = p2 if i >= len(subs) - round(n2) else p1
    return f"{p1:g} P for the first {len(subs) - round(n2)}, {p2:g} P for the last {round(n2)} (from {task.points:g} P task total)"


def per_tick_points(task: Task, rule: McRule, single: float | None, intro: str) -> list[str]:
    """Per-tick scoring: a question is worth its number of correct boxes x points per right tick
    (a single-answer question what the exam states for it). Needs the answer key; never an even split."""
    open_ = [s for s in task.subtasks if s.mc_options and s.points is None]
    if not open_:
        return []
    # grnvs_endterm_2020: "(Ausnahme Teilaufgaben c) und d) mit 0,5 Punkten pro Kreuz)"
    other: dict[str, float] = {}
    if m := EXCEPT_RE.search(intro):
        other = {k: float(m.group(2).replace(",", ".")) for k in re.findall(r"([a-z])\)", m.group(1))}
    elif re.search(r"Ausnahme", intro):
        return [f"{task.id}: per-tick rule with exceptions; MC points not derived"]
    nokey = []
    for s in open_:
        right = other.get(s.label[:1], rule.right)
        if s.mc_key:
            s.points = single if len(s.mc_key) == 1 and single is not None else len(s.mc_key) * right
        else:
            nokey.append(s.label or s.id)
    if nokey:
        return [f"{task.id}: MC points of {', '.join(nokey)} depend on the answer key (per-tick rule)"]
    return []


def derive_mc(task: Task, cover_rule: McRule | None, cover_text: str) -> list[str]:
    """MC points of one task: the rule stated in its intro (else the cover's), per-question values from
    the intro, per-tick maxima, the two-value split, then the even split of the header total."""
    first = task.subtasks[0] if task.subtasks else None
    intro = " ".join([task.title] + [c.text for c in task.context] + ([first.text] if first and not first.label else []))
    task.mc_rule = parse_mc_rule([intro])
    subs = task.subtasks
    if not any(s.mc_options for s in subs):
        return []
    rule = task.mc_rule or cover_rule
    if m := INTRO_EACH_RE.search(intro):
        each = num(m.group(1) or m.group(2))
        for s in subs:
            if s.mc_options and s.points is None:
                s.points = each
    if rule and rule.kind == "per_tick":
        m = SINGLE_RE.search(intro) or SINGLE_RE.search(cover_text)
        single = num(m.group(1)) if m else None
        if single is not None:  # the frontend needs it for solution-only keys
            rule.single = single
        return per_tick_points(task, rule, single, intro)
    stated = [v for v in (float(x.replace(",", ".")) for x in STATED_RE.findall(intro)) if v and v != task.points]
    if all(s.mc_options for s in subs) and (how := two_value_split(task, stated)):
        return [f"{task.id}: subtask points not printed; {how}"]
    if how := split_mc_points(task):
        return [f"{task.id}: subtask points not printed; {how}"]
    open_ = [s for s in subs if s.points is None]
    if task.points is not None and open_ and all(s.mc_options for s in subs):
        return [f"{task.id}: {task.points:g} P over {len(open_)} MC questions without points; not split"]
    return []


def fill_remainder(task: Task, rule: McRule | None) -> None:
    """The one labelled subtask without points gets what the task header leaves."""
    open_ = [s for s in task.subtasks if s.points is None]
    if task.points is None or len(open_) != 1 or not open_[0].label:
        return
    if open_[0].mc_options and rule and rule.kind == "per_tick":
        return
    rest = task.points - sum(s.points or 0 for s in task.subtasks)
    if _half_step(rest):
        open_[0].points = rest


class Grouper:
    def __init__(self, pages: list[Page], source: str, pdf_path: str | Path | None = None):
        self.pages = pages
        self.source = source  # display name (file name); also hints solution PDFs
        self.pdf_path = pdf_path  # the real file, read for MC answer keys; None = no keys
        self._inks: dict[int, list[BBox]] = {}  # solution-ink boxes per page index
        self.issues: list[Issue] = []
        self.usable = [p for p in pages if not p.skip and not p.scanned]
        self.lines = sorted((ln for p in self.usable for ln in p.body), key=lambda ln: (ln.page, ln.top, ln.x0))
        self.left: dict[int, float] = {}
        self.right: dict[int, float] = {}
        self.is_solution = self.detect_solution()
        for p in self.usable:
            long = [ln for ln in p.body if (ln.raw_len or len(ln.text)) >= 15 and ln.size >= 7 and not self.is_ink(ln)] or p.body
            if long:
                # 10th percentile, not min: one stray line (e.g. an unrecognized grading box merged
                # into a table row) must not move the text edge.
                xs = sorted(ln.x0 for ln in long)
                self.left[p.index] = xs[len(xs) // 10]
                self.right[p.index] = max(ln.x1 for ln in long)
        self.label_columns = self.find_label_columns()
        self.implicit_task = False
        self.points_from_grading: set[str] = set()

    def warn(self, msg: str, level: str = "warn") -> None:
        self.issues.append(Issue(level=level, message=msg))  # type: ignore[arg-type]

    # ---------- anchors ----------

    @staticmethod
    def parse_header(ln: Line) -> tuple[str, str] | None:
        """(number, rest of line) for "Aufgabe 3 Title" or, as fallback style, "3. Title"."""
        if m := HEADER_RE.match(ln.text):
            return None if TABLE_RE.match(m.group(3)) else (m.group(2), m.group(3))
        if m := NUMBERED_HEADER_RE.match(ln.text):
            return m.group(1), m.group(2)
        return None

    def find_headers(self) -> list[tuple[Line, str, str]]:
        by_style: dict[tuple, list[tuple[Line, str, str]]] = defaultdict(list)
        numbered_style: dict[tuple, list[tuple[Line, str, str]]] = defaultdict(list)
        for ln in self.lines:
            parsed = self.parse_header(ln)
            if not parsed or ln.x0 > self.left.get(ln.page, 0) + 40:
                continue
            if HEADER_RE.match(ln.text):
                by_style[ln.style].append((ln, *parsed))
            elif ln.bold:  # "3. Title" only counts when set apart in bold
                numbered_style[ln.style].append((ln, *parsed))
        if not by_style:
            # Numbered headers must count 1, 2, 3, ... to rule out ordinary numbered lists.
            def counts_up(hs: list) -> bool:
                nums = list(dict.fromkeys(int(h[1]) for h in hs))  # drop "(Fortsetzung)" repeats
                return len(nums) >= 2 and nums == list(range(1, len(nums) + 1))

            by_style = {k: v for k, v in numbered_style.items() if counts_up(v)}
        if not by_style:
            return []
        # Prefer the style used most often; ties go to bold, then bigger text.
        style = max(by_style, key=lambda s: (len(by_style[s]), by_style[s][0][0].bold, s[1]))
        headers, seen = [], set()
        for h in by_style[style]:
            if h[1] in seen:  # "Aufgabe 2 (Fortsetzung)" on the next page
                continue
            seen.add(h[1])
            headers.append(h)
        return headers

    def header_band(self, header: Line) -> list[Line]:
        """The header line plus lines beside it (titles set in a different font)."""
        return sorted(
            (ln for ln in self.lines if ln.page == header.page and ln.top < header.bottom and ln.bottom > header.top and ln.x0 >= header.x0),
            key=lambda ln: ln.x0,
        )

    def find_labels(self, task_lines: list[Line], task_number: str) -> list[Label]:
        labels: list[Label] = []
        for ln in task_lines:
            if ln.x0 - self.left.get(ln.page, 0) > LABEL_INDENT:
                continue
            column = self.label_columns.get(ln.page % 2)
            if column is not None and abs(ln.x0 - column) > 8:
                continue
            expected_idx = len(labels)
            m = LETTER_RE.match(ln.text)
            if m and (not labels or labels[0].key.isalpha()):
                letter = m.group(1) or m.group(2)
                if letter != chr(ord("a") + expected_idx):
                    continue
                labels.append(Label(ln, m.group(0).split("[")[0].strip(), letter, bool(m.group(3)), num(m.group(4))))
            else:
                m = NUMBERED_RE.match(ln.text)
                if not m or (labels and labels[0].key.isalpha()):
                    continue
                if m.group(1) != task_number.split(".")[0] or int(m.group(2)) != expected_idx + 1:
                    continue
                labels.append(Label(ln, m.group(0).strip(), m.group(2), bool(m.group(3)), None))
        return labels

    def find_label_columns(self) -> dict[int, float]:
        """x position of subtask labels per page parity (TUM templates alternate margins between
        odd and even pages). Taken document-wide, so "f)" printed inside a table can't win. Lines
        before the first task header are skipped: a task overview listing "(b) [3 Punkte]" can't either."""
        headers = self.find_headers()
        first = (headers[0][0].page, headers[0][0].top) if headers else (-1, 0)
        cands: dict[int, Counter] = defaultdict(Counter)
        for ln in self.lines:
            if (
                (ln.page, ln.top) >= first
                and (LETTER_RE.match(ln.text) or NUMBERED_RE.match(ln.text))
                and ln.x0 - self.left.get(ln.page, 0) <= LABEL_INDENT
            ):
                cands[ln.page % 2][round(ln.x0 / 4) * 4] += 1
        columns = {parity: float(c.most_common(1)[0][0]) for parity, c in cands.items()}
        if len(columns) == 1:  # only one parity has labels: use it for both
            columns[1 - next(iter(columns))] = next(iter(columns.values()))
        return columns

    def label_points(self, label: Label, subtask_id: str) -> float | None:
        if label.points is not None:
            return label.points
        page = self.pages[label.line.page]
        for g in page.grading_boxes:
            if label.line.top - 12 <= g.top <= label.line.top + 40:
                self.points_from_grading.add(subtask_id)
                return float(g.max_points)
        text = label.line.text
        # the last points note ending near the line's end; "f) (0.5 Punkte): Character" is 0.5, not "5 Punkte"
        m = next((m for m in reversed(list(POINTS_RE.finditer(text))) if m.end() > len(text) - 20), None)
        return num(m.group(1)) if m else None

    # ---------- regions ----------

    def items(self, page: Page):
        frame_w, frame_h = 0.9 * page.width, 0.9 * page.height
        for ln in page.body:
            yield ln.x0, ln.top, ln.x1, ln.bottom
        for g in page.graphics:
            if g.x1 - g.x0 < frame_w and g.bottom - g.top < frame_h:
                yield g.x0, g.top, g.x1, g.bottom

    def regions_between(self, start: Pos, end: Pos) -> list[Region]:
        regions = []
        for page in self.usable:
            if not start.page <= page.index <= end.page:
                continue
            y0 = start.y if page.index == start.page else float("-inf")
            y1 = end.y if page.index == end.page else float("inf")
            inside = [it for it in self.items(page) if y0 <= (it[1] + it[3]) / 2 < y1]
            if not inside:
                continue
            left = self.left.get(page.index, min(it[0] for it in inside))
            right = self.right.get(page.index, max(it[2] for it in inside))
            bbox = BBox(
                x0=max(0, min(left, min(it[0] for it in inside)) - PAD),
                y0=max(y0, min(it[1] for it in inside) - PAD, 0),
                x1=min(page.width, max(right, max(it[2] for it in inside)) + PAD),
                y1=min(y1, max(it[3] for it in inside) + PAD, page.height),
            )
            if bbox.height > 2:
                regions.append(Region(page=page.index, bbox=bbox, visual=self.visual(page, bbox)))
        return regions

    def visual(self, page: Page, bbox: BBox) -> bool:
        """Whether the text cannot carry the crop (figure, drawn table, garbled glyphs, unfolded
        scripts). Fonts, code and folded scripts are text. Errs towards True: a missing figure costs a grade, an extra crop only tokens."""

        def inside(x0, top, x1, bottom):
            return bbox.x0 <= (x0 + x1) / 2 <= bbox.x1 and bbox.y0 <= (top + bottom) / 2 <= bbox.y1

        lines = [ln for ln in page.body if inside(ln.x0, ln.top, ln.x1, ln.bottom)]
        # a refused script fold or garbled glyphs: the text is wrong, the crop is right
        for ln in lines:
            if ln.converted:  # text by construction
                continue
            text = ln.text
            for g in CHECKBOX_GLYPHS:
                text = text.replace(g, "")
            if (
                ln.scripts_uncertain
                or "(cid:" in text
                or re.search("[\x00-\x08\x0b-\x1f\ue000-\uf8ff\ufffd]", text)
                or any(c in BIG_OPERATORS for c in text)
                or any(MATH_STRUCT_FONT_RE.search(f) for f in ln.fonts)
            ):
                return True
        converted = [ln for ln in lines if ln.converted]
        checkboxes = {id(c) for c in page.checkboxes}
        small = 0
        for g in page.graphics:
            if not inside(g.x0, g.top, g.x1, g.bottom) or id(g) in checkboxes:
                continue
            if any(c.x0 <= (g.x0 + g.x1) / 2 <= c.x1 and c.top <= (g.top + g.bottom) / 2 <= c.bottom for c in converted):
                continue
            if g.kind in ("image", "curve"):
                return True
            w, h = g.x1 - g.x0, g.bottom - g.top
            if (
                h < 2
                and w < 0.5 * (bbox.x1 - bbox.x0)
                and any(  # fraction bar: text right above and below it
                    ln.x0 < g.x1 and ln.x1 > g.x0 and -0.5 * ln.size <= g.top - ln.bottom < 1.5 * ln.size for ln in lines
                )
                and any(ln.x0 < g.x1 and ln.x1 > g.x0 and -0.5 * ln.size <= ln.top - g.bottom < 1.5 * ln.size for ln in lines)
            ):
                return True  # line boxes reach above the bar, hence the negative bound
            if (
                h < 2
                and w < 0.5 * (bbox.x1 - bbox.x0)
                and any(  # overline (conjugate, closure): short bar over the top half of a text line, nothing above it
                    ln.x0 - 1 <= g.x0 and g.x1 <= ln.x1 + 1 and w < 8 * ln.size and ln.top - 0.6 * ln.size <= g.bottom <= (ln.top + ln.bottom) / 2
                    for ln in lines
                )
                and not any(ln.x0 < g.x1 and ln.x1 > g.x0 and 0 < g.top - (ln.top + ln.bottom) / 2 < 1.5 * ln.size for ln in lines)
            ):
                return True
            if (
                w < 2
                and sum(
                    ln.top < g.bottom and ln.bottom > g.top and ln.x0 - 4 <= g.x0 <= ln.x1 + 4  # matrix bracket, column rule
                    for ln in lines
                )
                >= 2
            ):
                return True
            answer_box = w > 0.5 * (bbox.x1 - bbox.x0) and h > 25
            rule = h < 2 and w > 0.5 * (bbox.x1 - bbox.x0)  # separators and ruled answer lines
            if not (answer_box or rule):
                small += 1
        return small >= 6  # tables and diagrams drawn from lines

    def is_ink(self, ln: Line) -> bool:
        return self.is_solution and ln.solution_ink

    def text_in(self, regions: list[Region], solution: bool = False) -> str:
        out = []
        for r in regions:
            got = []
            for ln in self.pages[r.page].body:
                if r.bbox.y0 <= (ln.top + ln.bottom) / 2 <= r.bbox.y1 and self.is_ink(ln) == solution:
                    got.append(ln)
            idx = [i for i, ln in enumerate(got) if CODE_RE.search(SCRIPT_RE.sub(r"\1", ln.text))]
            # from the first to the last code line everything is code ("else", "for (...)" have no terminator)
            code = set(range(idx[0], idx[-1] + 1)) if len(idx) >= 2 else set(idx)
            left = min((got[i].x0 for i in idx), default=0)
            for i, ln in enumerate(got):  # code keeps its indentation, relative to the region's leftmost code line
                out.append(" " * max(round((ln.x0 - left) / (0.5 * ln.size)), 0) * (i in code) + ln.text)
        return "\n".join(out)

    def is_lead_in(self, start: Pos, end: Pos) -> bool:
        """Text between an answer area and the next label that introduces the following subtasks:
        it must start with prose at the left text edge (not axis labels of a plot) and contain
        no checkboxes (those are answer options of the current subtask)."""
        inside = [ln for ln in self.lines if (start.page, start.y) <= (ln.page, (ln.top + ln.bottom) / 2) < (end.page, end.y) and not self.is_ink(ln)]
        if not inside:
            return False
        first = inside[0]
        if first.x0 - self.left.get(first.page, 0) > 15 or (first.raw_len or len(first.text)) < 25:
            return False
        for page in self.usable:
            if not start.page <= page.index <= end.page:
                continue
            y0 = start.y if page.index == start.page else float("-inf")
            y1 = end.y if page.index == end.page else float("inf")
            if any(g.kind == "rect" and is_checkbox_size(g.x1 - g.x0, g.bottom - g.top) and y0 <= g.top < y1 for g in page.graphics):
                return False
        return True

    def answer_boxes(self, start: Pos, end: Pos) -> list[tuple[int, BBox]]:
        """Big, (nearly) empty frames or grids in a segment = answer areas, in reading order.

        Answer areas are drawn either as one rectangle or as many full-width lines (squared paper),
        so wide rects/lines are clustered vertically first.
        """
        found: list[tuple[int, BBox]] = []
        for page in self.usable:
            if not start.page <= page.index <= end.page:
                continue
            y0 = start.y if page.index == start.page else float("-inf")
            y1 = end.y if page.index == end.page else float("inf")
            width = self.right.get(page.index, page.width) - self.left.get(page.index, 0)
            wide = sorted(
                (g for g in page.graphics if g.kind in ("rect", "line") and g.top >= y0 and g.bottom <= y1 and g.x1 - g.x0 >= 0.6 * width),
                key=lambda g: g.top,
            )
            # Vertical strokes join a box drawn as separate top/bottom/side lines.
            # Page-high margin rules are not box sides.
            verticals = [g for g in page.graphics if g.kind in ("rect", "line") and g.x1 - g.x0 < 3 and 20 <= g.bottom - g.top < 0.9 * page.height]
            clusters: list[BBox] = []
            for g in wide:
                last = clusters[-1] if clusters else None
                joined = last and any(v.top <= last.y1 + 3 and v.bottom >= g.top - 3 for v in verticals)
                if last and (g.top <= last.y1 + 20 or joined):
                    clusters[-1] = BBox(x0=min(last.x0, g.x0), y0=last.y0, x1=max(last.x1, g.x1), y1=max(last.y1, g.bottom))
                else:
                    clusters.append(BBox(x0=g.x0, y0=g.top, x1=g.x1, y1=g.bottom))
            for c in clusters:
                if c.height < 25:
                    continue
                inner = sum((ln.raw_len or len(ln.text)) for ln in page.body if not self.is_ink(ln) and c.y0 <= ln.top and ln.bottom <= c.y1)
                if inner > 80:  # a framed table or figure, not an answer area
                    continue
                found.append((page.index, c))
        return found

    def last_answer_box(self, start: Pos, end: Pos) -> Pos | None:
        """Bottom of the subtask's answer area."""
        boxes = self.answer_boxes(start, end)
        if not boxes:
            return None
        page, box = boxes[-1]
        return Pos(page, box.y1 + PAD)

    def attach_answer_boxes(self, subtask: Subtask, start: Pos, end: Pos) -> None:
        """Answer areas relative to the region they lie in, the largest per region (an area split
        over two pages gives two). The frontend puts a text field on each."""
        if subtask.mc_options:
            return
        best: dict[int, tuple[float, AnswerBox]] = {}
        for page, box in self.answer_boxes(start, end):
            cy = (box.y0 + box.y1) / 2
            for k, r in enumerate(subtask.regions):
                b = r.bbox
                if r.page != page or not b.y0 <= cy <= b.y1:
                    continue
                w, h = b.x1 - b.x0, b.y1 - b.y0
                rel = lambda v, lo, size: min(1.0, max(0.0, (v - lo) / size))
                area = (box.x1 - box.x0) * box.height
                if k not in best or area > best[k][0]:
                    best[k] = (
                        area,
                        AnswerBox(
                            region=k, bbox=BBox(x0=rel(box.x0, b.x0, w), y0=rel(box.y0, b.y0, h), x1=rel(box.x1, b.x0, w), y1=rel(box.y1, b.y0, h))
                        ),
                    )
                break
        subtask.answer_boxes = [ab for _, (_, ab) in sorted(best.items())]

    def attach_mc(self, subtask: Subtask) -> None:
        """Checkbox options inside the regions (MC = at least 2), and for solution PDFs the ticked ones."""
        options = [o for k, r in enumerate(subtask.regions) for o in find_options(self.pages[r.page], r, k)]
        if len(options) < 2:
            return
        subtask.mc_options = options
        if not self.is_solution or self.pdf_path is None:
            return
        by_page: dict[int, list[tuple[int, BBox]]] = defaultdict(list)
        for i, o in enumerate(options):
            r = subtask.regions[o.region]
            w, h = r.bbox.x1 - r.bbox.x0, r.bbox.y1 - r.bbox.y0
            by_page[r.page].append(
                (i, BBox(x0=r.bbox.x0 + o.bbox.x0 * w, y0=r.bbox.y0 + o.bbox.y0 * h, x1=r.bbox.x0 + o.bbox.x1 * w, y1=r.bbox.y0 + o.bbox.y1 * h))
            )
        key: list[int] = []
        for page, boxes in by_page.items():
            if page not in self._inks:
                self._inks[page] = ink_boxes(self.pdf_path, page)
            key += [boxes[j][0] for j in ticked(self._inks[page], [b for _, b in boxes])]
        subtask.mc_key = sorted(key) or None  # no ink found: key unknown rather than "nothing is correct"

    # ---------- main ----------

    def run(self) -> ExamStructure:
        scanned = [p.index + 1 for p in self.pages if p.scanned and not p.skip]
        content_pages = [p for p in self.pages if not p.skip]
        kind = "digital" if not scanned else ("scanned" if len(scanned) == len(content_pages) else "mixed")
        if scanned:
            self.warn(f"{len(scanned)} scanned page(s) need OCR (not supported yet): {scanned[:10]}", "error")

        headers = self.find_headers()
        if not headers:
            # Quizzes are one long series of a), b), c), ... without task headers.
            labels = self.find_labels(self.lines, "1")
            if len(labels) >= 2:
                headers = [(labels[0].line, "1", "")]
                self.implicit_task = True
                self.warn("no task headers found; treating the exam as a single task")
            else:
                self.warn("no task headers found", "error")

        first = Pos(headers[0][0].page, headers[0][0].top) if headers else Pos(len(self.pages), 0)
        front = [ln for ln in self.lines if (ln.page, ln.top) < (first.page, first.y)]
        total = None
        for ln in front:
            if m := TOTAL_RE.search(ln.text):
                total = num(m.group(1))
                break
        meta_texts = [ln.text for ln in front]

        end = Pos(len(self.pages), 0)
        if headers:
            last = headers[-1][0]
            for ln in self.lines:
                if (ln.page, ln.top) > (last.page, last.top) and END_RE.match(ln.text):
                    end = Pos(ln.page, ln.top - PAD)
                    break

        tasks: list[Task] = []
        brackets: dict[str, float] = {}
        for i, (h, number, rest) in enumerate(headers):
            nxt = headers[i + 1][0] if i + 1 < len(headers) else None
            start = Pos(h.page, h.top - PAD)
            stop = Pos(nxt.page, nxt.top - PAD) if nxt else end
            band = [] if self.implicit_task else self.header_band(h)
            rest = " ".join([rest] + [ln.text for ln in band if ln is not h]).strip()
            hp = header_points(rest)
            points, title = hp.points, hp.title

            band_ids = {id(ln) for ln in band}
            body = [ln for ln in self.lines if (start.page, start.y) <= (ln.page, ln.top) < (stop.page, stop.y) and id(ln) not in band_ids]
            labels = self.find_labels(body, number)
            tid = f"A{number}"

            contexts: list[Context] = []
            subtasks: list[Subtask] = []
            spans: list[tuple[Pos, Pos]] = []  # (start, end) per subtask
            if labels:
                stem = self.regions_between(start, Pos(labels[0].line.page, labels[0].line.top - PAD))
                if stem:
                    contexts.append(Context(id=f"{tid}_ctx0", regions=stem, text=self.text_in(stem)))
                bounds = [Pos(lb.line.page, lb.line.top - PAD) for lb in labels] + [stop]
                for j, lb in enumerate(labels):
                    seg_start, seg_end = bounds[j], bounds[j + 1]
                    if j + 1 < len(labels):
                        # Text after this subtask's answer box introduces the following subtasks.
                        box_end = self.last_answer_box(seg_start, seg_end)
                        if box_end and self.is_lead_in(box_end, seg_end):
                            lead = self.regions_between(box_end, seg_end)
                            if lead:
                                contexts.append(
                                    Context(
                                        id=f"{tid}_ctx{len(contexts)}",
                                        applies_from=f"{tid}{labels[j + 1].key}",
                                        regions=lead,
                                        text=self.text_in(lead),
                                    )
                                )
                                seg_end = box_end
                    regions = self.regions_between(seg_start, seg_end)
                    sid = f"{tid}{lb.key}"
                    subtasks.append(
                        Subtask(
                            id=sid,
                            label=lb.label,
                            points=self.label_points(lb, sid),
                            independent=lb.star,
                            regions=regions,
                            text=self.text_in(regions),
                            solution_text=self.text_in(regions, True),
                        )
                    )
                    spans.append((seg_start, seg_end))
            else:
                regions = self.regions_between(start, stop)
                subtasks.append(
                    Subtask(
                        id=f"{tid}_", label="", points=points, regions=regions, text=self.text_in(regions), solution_text=self.text_in(regions, True)
                    )
                )
                spans.append((start, stop))
            for st, (a, b) in zip(subtasks, spans):
                self.attach_mc(st)
                self.attach_answer_boxes(st, a, b)
                if st.points is None and labels:
                    st.points = inline_points(st.text)

            task = Task(id=tid, number=number, title=title, points=points, context=contexts, subtasks=subtasks)
            if labels:
                for msg in apply_header_points(task, hp):
                    self.warn(msg)
            tasks.append(task)
            if hp.bracket is not None:
                brackets[tid] = hp.bracket

        # "[29]" / "(12)" after the title are points only as the exam's notation, not one "Array [10]"
        if len(brackets) >= 2:
            for task in tasks:
                if task.id in brackets:
                    task.points = brackets[task.id]
                    if len(task.subtasks) == 1 and not task.subtasks[0].label and task.subtasks[0].points is None:
                        task.subtasks[0].points = task.points
        cover_rule = parse_mc_rule(meta_texts)  # before the first task: applies to every task
        for task in tasks:
            for msg in derive_mc(task, cover_rule, " ".join(meta_texts)):
                self.warn(msg)
        if tasks:  # MC instructions are often printed under "Aufgabe 1 Multiple Choice"
            meta_texts += [tasks[0].title] + [c.text for c in tasks[0].context]
        self.points_from_total(tasks, total)
        for task in tasks:
            fill_remainder(task, task.mc_rule or cover_rule)
            self.check_task(task, bool(task.subtasks and task.subtasks[0].label))
        self.check_exam(tasks, total)
        return ExamStructure(
            source=Path(self.source).name,
            page_count=len(self.pages),
            page_sizes=[(p.width, p.height) for p in self.pages],
            kind=kind,  # type: ignore[arg-type]
            is_solution=self.is_solution,
            total_points_stated=total,
            duration_minutes=parse_duration(meta_texts),
            mc_rule=parse_mc_rule(meta_texts),
            tasks=tasks,
            issues=self.issues,
        )

    @staticmethod
    def points_from_total(tasks: list[Task], total: float | None) -> None:
        """The one task without points gets what the cover's total leaves ("(8" + "Punkte)" split over two lines)."""

        def known(t: Task) -> float | None:
            if t.points is not None:
                return t.points
            return sum(s.points for s in t.subtasks) if all(s.points is not None for s in t.subtasks) else None  # type: ignore[misc]

        open_ = [t for t in tasks if known(t) is None]
        if total is None or len(open_) != 1:
            return
        rest = total - sum(known(t) for t in tasks if t is not open_[0])  # type: ignore[misc]
        if _half_step(rest):
            open_[0].points = rest
            if len(open_[0].subtasks) == 1 and not open_[0].subtasks[0].label:
                open_[0].subtasks[0].points = rest

    # ---------- checks ----------

    def check_task(self, task: Task, has_labels: bool) -> None:
        sub_points = [s.points for s in task.subtasks]
        if has_labels and task.points is not None and all(p is not None for p in sub_points):
            s = sum(sub_points)  # type: ignore[arg-type]
            # Grading boxes only show whole points (half points are a second column of boxes),
            # so they can undercount the header by up to 0.5 per subtask.
            graded = sum(1 for st in task.subtasks if st.id in self.points_from_grading)
            slack = 0.5 * graded
            if not -0.01 <= task.points - s <= slack + 0.01:
                self.warn(f"{task.id}: subtask points sum to {s:g}, header says {task.points:g}")
        for s in task.subtasks:
            if not s.regions:
                self.warn(f"{s.id}: empty region")

    def check_exam(self, tasks: list[Task], total: float | None) -> None:
        numbers = [t.number for t in tasks]
        ints = [int(n.split(".")[0]) for n in numbers]
        if ints and ints != sorted(ints):
            self.warn(f"task numbers out of order: {numbers}")
        task_points = [
            t.points if t.points is not None else (sum(s.points for s in t.subtasks) if all(s.points is not None for s in t.subtasks) else None)
            for t in tasks
        ]
        if total is not None and tasks and all(p is not None for p in task_points):
            s = sum(task_points)  # type: ignore[arg-type]
            if abs(s - total) > 0.01:
                self.warn(f"tasks sum to {s:g} points, cover page says {total:g}")

    def detect_solution(self) -> bool:
        if SOLUTION_NAME_RE.search(Path(self.source).stem):
            return True
        if any(p.watermark_chars for p in self.pages):
            return True
        blue = sum(1 for ln in self.lines if ln.solution_ink)
        return bool(self.lines) and blue / len(self.lines) > 0.03


def group(pages: list[Page], source: str, pdf_path: str | Path | None = None) -> ExamStructure:
    """`source` is the display name; `pdf_path` the file to read MC answer keys from (None: no keys)."""
    return Grouper(pages, source, pdf_path).run()
