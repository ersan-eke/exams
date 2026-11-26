"""Step 1: turn a PDF into per-page primitives (styled text lines, graphics, grading boxes).

Everything that is not exam content is classified here so later steps never see it:
StuDocu cover pages and download footers, the "Lösungsvorschlag" watermark, repeated
page headers/footers, and the point-grading boxes in the page margin.
"""

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

WATERMARK_MIN_SIZE = 40  # giant diagonal letters like "Lösungsvorschlag"
CHECKBOX_MIN, CHECKBOX_MAX = 5, 14  # side length of MC checkboxes in pt
CHECKBOX_MSAM = {"(cid:3)", "□", "(cid:2)", "⊠"}  # amssymb square, boxtimes
CHECKBOX_UNICODE = {"☐", "☒", "☑"}
MARGIN = 50  # grading boxes live within this distance of the page edge
FURNITURE_RE = re.compile(
    r"lOMoARcPSD|Studocu|Downloaded by|Heruntergeladen durch|"
    r"^\W*(Seite|Page)\s*\d+\s*(/|von|of)\s*\d+\W*$|^\W*\d+\s*/\s*\d+\W*$|^[–—-]?\s*\d+\s*[–—-]?$",
    re.IGNORECASE,
)
TASK_HEADER_RE = re.compile(r"^\s*(Aufgabe|Problem|Exercise|Task|Question|Frage)\s*\d", re.IGNORECASE)
POINTS_NOTE_RE = re.compile(r"^\W*\d+(?:[.,]\d+)?\s*(?:Punkte?|Pkt\.?|P|points?|credits?|marks?)\W*$", re.IGNORECASE)  # "(4 Punkte)"
STUDOCU_RE = re.compile(r"lOMoARcPSD|Studocu|Downloaded by|Heruntergeladen durch", re.IGNORECASE)
BOLD_RE = re.compile(r"Bold|Bol\b|BX|Semibold|Heavy|Black|Demi", re.IGNORECASE)


@dataclass
class Line:
    page: int
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    font: str
    size: float
    bold: bool
    color: tuple[float, float, float]
    furniture: bool = False
    fonts: frozenset[str] = frozenset()
    scripts: bool = False  # has sub/superscript letters or digits, which plain text loses
    scripts_uncertain: bool = False  # small glyphs that look like scripts but were not folded (stacked, on operators)
    converted: bool = False  # produced by enrichment (table/formula as text): graphics inside it are not a visual
    raw_len: int = 0  # text length before script folding (geometry heuristics must not see the markup)

    @property
    def style(self) -> tuple[str, int]:
        return (self.font, round(self.size))

    @property
    def solution_ink(self) -> bool:
        return is_ink_color(self.color)


@dataclass
class Box:
    x0: float
    top: float
    x1: float
    bottom: float
    kind: str = ""  # rect | line | curve | image


@dataclass
class Word:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    solution_ink: bool = False


@dataclass
class GradingBox(Box):
    max_points: int = 0


@dataclass
class Page:
    index: int
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    graphics: list[Box] = field(default_factory=list)
    grading_boxes: list[GradingBox] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)  # body words, for MC option texts
    checkboxes: list[Box] = field(default_factory=list)  # MC checkbox candidates (kind rect | glyph)
    scanned: bool = False
    skip: str | None = None  # reason this page is not exam content
    redact: list[Box] = field(default_factory=list)  # StuDocu lines with other people's names/emails
    watermark_chars: int = 0

    @property
    def body(self) -> list[Line]:
        return [ln for ln in self.lines if not ln.furniture]


def to_rgb(color) -> tuple[float, float, float]:
    if not color:
        return (0.0, 0.0, 0.0)
    if isinstance(color, (int, float)):
        return (float(color),) * 3
    c = tuple(float(v) for v in color if isinstance(v, (int, float)))
    if len(c) == 1:
        return c * 3
    if len(c) == 3:
        return c  # type: ignore[return-value]
    if len(c) == 4:  # CMYK
        k = c[3]
        return tuple((1 - v) * (1 - k) for v in c[:3])  # type: ignore[return-value]
    return (0.0, 0.0, 0.0)


def base_font(name: str) -> str:
    return name.split("+")[-1]


MAX_SCRIPT = 6  # shortcut: longer small text is a note or solution ink, not a script; upgrade if real scripts get cut


def is_checkbox_size(w: float, h: float) -> bool:
    return CHECKBOX_MIN <= w <= CHECKBOX_MAX and CHECKBOX_MIN <= h <= CHECKBOX_MAX


def is_ink_color(rgb: tuple[float, float, float]) -> bool:
    r, g, b = rgb
    return b - max(r, g) > 0.1 and abs(r - g) < 0.12


def split_words(chars: list[dict], top: float, bottom: float) -> list[Word]:
    """Words of one text line: a gap wider than the line extraction's x tolerance starts a new word."""
    words: list[Word] = []
    prev = None
    for c in chars:
        if c is prev:  # pdfplumber repeats a ligature char once per expanded letter
            continue
        ink = is_ink_color(to_rgb(c.get("non_stroking_color")))
        text = unicodedata.normalize("NFKC", c["text"])
        if prev is not None and c["x0"] - prev["x1"] <= 1.5 and words[-1].solution_ink == ink:
            w = words[-1]
            w.text += text
            w.x1 = max(w.x1, c["x1"])
        else:
            words.append(Word(text, c["x0"], top, c["x1"], bottom, ink))
        prev = c
    return words


def glyph_checkboxes(chars: list[dict], page_height: float) -> tuple[list[Box], set[int]]:
    """Box/circle glyphs (amssymb square/boxtimes, LaTeX circle font, Unicode ballot boxes) used as checkboxes.

    Math uses the same glyphs ("(q,□,N)"), so a glyph only counts when it stands apart from its
    neighbours on the line. Char boxes span the whole font height, so the visible square is placed
    on the baseline with a side of about 2/3 em (amssymb square metrics)."""
    boxes, used = [], set()
    for c in chars:
        font = base_font(c["fontname"])
        glyph = (font.startswith("MSAM") and c["text"] in CHECKBOX_MSAM) or c["text"] in CHECKBOX_UNICODE or font.startswith("LCIRCLE")
        w = c["x1"] - c["x0"]
        # Blue glyphs are solution ink (a tick, or a symbol in a sample answer), never a printed box.
        if not glyph or not is_checkbox_size(w, w) or is_ink_color(to_rgb(c.get("non_stroking_color"))):
            continue
        cy = (c["top"] + c["bottom"]) / 2
        if any(
            d is not c and abs((d["top"] + d["bottom"]) / 2 - cy) < c["size"] / 2 and (-1 < d["x0"] - c["x1"] < 1 or -1 < c["x0"] - d["x1"] < 1)
            for d in chars
        ):
            continue
        side = min(w, 0.67 * c["size"])
        matrix = c.get("matrix")
        baseline = page_height - matrix[5] if matrix else c["bottom"]
        cx = (c["x0"] + c["x1"]) / 2
        boxes.append(Box(cx - side / 2, baseline - side, cx + side / 2, baseline, "glyph"))
        used.add(id(c))
    return boxes, used


def find_grading_boxes(chars: list[dict], width: float) -> tuple[list[GradingBox], set[int]]:
    """Vertical runs of small digits 0,1,...,n in the margin = the points of one subtask."""
    margin_digits = [c for c in chars if c["text"].isdigit() and 6 <= c["size"] <= 9.5 and (c["x1"] < MARGIN or c["x0"] > width - MARGIN)]
    # Merge digits on the same baseline into numbers ("1","0" -> "10").
    tokens: list[tuple[int, float, float, float, float, list[dict]]] = []
    for c in sorted(margin_digits, key=lambda c: (round(c["top"]), c["x0"])):
        if tokens and abs(tokens[-1][2] - c["top"]) < 2 and -1 < c["x0"] - tokens[-1][3] < 3:
            val, x0, top, _, bottom, cs = tokens[-1]
            tokens[-1] = (val * 10 + int(c["text"]), x0, top, c["x1"], bottom, cs + [c])
        else:
            tokens.append((int(c["text"]), c["x0"], c["top"], c["x1"], c["bottom"], [c]))

    columns: dict[int, list] = defaultdict(list)
    for t in tokens:
        columns[round(t[1] / 6)].append(t)

    boxes, used = [], set()
    for col in columns.values():
        col.sort(key=lambda t: t[2])
        run: list = []
        for t in col + [None]:
            if t is not None and run and t[0] == run[-1][0] + 1 and t[2] - run[-1][2] < 30:
                run.append(t)
                continue
            if len(run) >= 2 and run[0][0] == 0:
                boxes.append(
                    GradingBox(
                        x0=min(r[1] for r in run),
                        top=run[0][2],
                        x1=max(r[3] for r in run),
                        bottom=run[-1][4],
                        max_points=run[-1][0],
                    )
                )
                used.update(id(c) for r in run for c in r[5])
            run = [t] if t is not None and t[0] == 0 else []
    return boxes, used


def _baseline(c: dict) -> float:
    """Baseline in y-down page coordinates (the char matrix is exact; bottom is a fallback)."""
    m = c.get("matrix")
    return -m[5] if m else c["bottom"]


def fold_scripts(raw_lines: list[dict]) -> list[dict]:
    """Fold sub/superscript glyphs into the preceding base glyph as `_{..}` / `^{..}`.

    A glyph is a script when it is < 0.8x the size of its base and its baseline is shifted by >= 15 % of
    the base size. Script-only lines vanish; lines that absorbed scripts get `scripts=True` (the visual
    check still wants to know). Lines without scripts are returned untouched."""
    chars = [c for ln in raw_lines for c in ln["chars"]]
    bases = [c for c in chars if not c["text"].isspace()]
    marks = {id(c) for c in bases if c["text"] in "*\u2020\u2021"}  # label stars never carry scripts
    labels: set[int] = set()  # ")" or "." closing a label like "a)", "(b)", "10)", "1.": nothing after it is a script
    for ln in raw_lines:
        g = [c for c in ln["chars"] if not c["text"].isspace()][:5]
        for i, c in enumerate(g):
            pre = [x["text"] for x in g[:i]]
            if pre[:1] == ["("]:
                pre = pre[1:]
            if (c["text"] == ")" and 1 <= len(pre) <= 2 and all(t.isalnum() for t in pre)) or (
                c["text"] == "." and 1 <= len(pre) <= 2 and all(t.isdigit() for t in pre)
            ):
                labels.add(id(c))
                break
    line_of = {id(c): k for k, ln in enumerate(raw_lines) for c in ln["chars"]}
    rows: dict[int, list[dict]] = defaultdict(list)  # baseline bucket -> glyphs, so neighbours are cheap to find
    for c in bases:
        rows[int(_baseline(c) // 12)].append(c)

    def near(c: dict) -> list[dict]:
        return [d for k in (-1, 0, 1) for d in rows[int(_baseline(c) // 12) + k]]

    runs: list[dict] = []  # {"chars", "base" (None = rejected), "kind", "uncertain"}
    for c in sorted(bases, key=lambda c: c["x0"]):
        # chain: a glyph directly right of a script glyph on its baseline extends that run
        run = next(
            (
                r
                for r in runs
                if -0.3 * c["size"] <= c["x0"] - r["chars"][-1]["x1"] < 0.7 * c["size"]
                and abs(_baseline(r["chars"][-1]) - _baseline(c)) < 0.15 * r["chars"][-1]["size"]
            ),
            None,
        )
        if run is not None:
            run["chars"].append(c)
            continue
        best = None
        for d in near(c):
            shift = _baseline(d) - _baseline(c)  # > 0: raised
            if (
                d is not c
                and c.get("non_stroking_color") == d.get("non_stroking_color")
                and c["size"] < 0.8 * d["size"]
                and d["x1"] <= c["x0"] + 0.3 * d["size"]
                and c["x0"] - d["x1"] < 0.7 * d["size"]
                and (0.15 - 0.005) * d["size"] <= abs(shift) <= 0.6 * d["size"]  # epsilon: 0.1499 is 0.15
                and (best is None or d["x1"] > best["x1"])
            ):
                best, best_shift = d, shift
        if best is None:
            continue
        # a full-size glyph on the base's line under/over the script means a margin tag ("TP" by a label)
        covered = any(
            e is not best
            and abs(_baseline(e) - _baseline(best)) < 0.15 * best["size"]
            and e["size"] >= 0.8 * best["size"]
            and min(e["x1"], c["x1"]) - max(e["x0"], c["x0"]) > 0.5 * (c["x1"] - c["x0"])
            for e in near(best)
        )
        # operators, symbols, big-operator fonts (CMEX sum signs come out as "P") only look like bases
        symbol = not (best["text"].isalnum() or best["text"] in ")]}") or re.search(r"CMEX|MathExtension", best.get("fontname", "")) is not None
        label = id(best) in labels
        ok = not (covered or label or id(best) in marks or symbol)
        runs.append(
            {
                "chars": [c],
                "base": best if ok else None,
                "kind": "^" if best_shift > 0 else "_",
                "uncertain": symbol and not (covered or label),
                "src": best,
            }
        )
    per_base = Counter(id(r["src"]) for r in runs)
    uncertain_lines: set[int] = set()
    folded: dict[int, str] = {}  # id(base) -> appended text
    dropped: set[int] = set()
    extent: dict[int, float] = {}
    owner: dict[int, dict] = {}  # id(script glyph) -> its base
    for run in runs:
        text = "".join(g["text"] for g in run["chars"])
        last, src = run["chars"][-1], run["src"]
        # a full-size letter starting inside the run's span: the script sits under a word ("lim"), not after a base
        if id(src) not in labels and any(
            e is not src
            and e["text"].isalpha()
            and e["size"] >= 0.8 * src["size"]
            and abs(_baseline(e) - _baseline(src)) < 0.15 * src["size"]
            and src["x1"] - 0.3 * src["size"] <= e["x0"] < last["x1"] - 0.25 * (last["x1"] - last["x0"])
            for e in near(src)
        ):
            run["base"], run["uncertain"] = None, True
        # a full-size glyph between the run's own glyphs (")" in "(a_n)_n", "(3^9)^5"): the fold would read as a different formula
        ids = {id(g) for g in run["chars"]}
        if (
            run["base"] is not None
            and len(run["chars"]) > 1
            and any(
                e is not src
                and id(e) not in ids
                and e["size"] >= 0.8 * src["size"]
                and abs(_baseline(e) - _baseline(src)) < 0.15 * src["size"]
                and run["chars"][0]["x1"] - 0.1 * src["size"] <= e["x0"] < last["x0"]
                for e in near(src)
            )
        ):
            run["base"], run["uncertain"] = None, True
        if run["base"] is not None and per_base[id(run["src"])] > 1:  # stacked limits/fractions: not plain text
            run["base"], run["uncertain"] = None, True
        if run["uncertain"]:
            uncertain_lines.update(line_of[id(g)] for g in run["chars"] + [run["src"]])
        if run["base"] is None or len(text) > MAX_SCRIPT or text in ("*", "\u2020", "\u2021"):  # footnote marks stay as printed
            continue
        base = run["base"]
        folded[id(base)] = folded.get(id(base), "") + f"{run['kind']}{{{text}}}"
        extent[id(base)] = max(extent.get(id(base), 0), run["chars"][-1]["x1"])
        dropped.update(id(g) for g in run["chars"])
        owner.update((id(g), base) for g in run["chars"])
    if not dropped and not uncertain_lines:
        return raw_lines
    extra: dict[int, int] = defaultdict(int)  # text length of vanished script-only lines, credited to the base's line
    out = []
    for k, ln in enumerate(raw_lines):
        raw_len = ln.get("raw_len", len(ln["text"].strip()))
        uncertain = ln.get("scripts_uncertain", False) or k in uncertain_lines
        if not any(id(c) in dropped or id(c) in folded for c in ln["chars"]):
            out.append((k, {**ln, "scripts_uncertain": uncertain, "raw_len": raw_len}))
            continue
        kept = [
            dict(c, text=c["text"] + folded[id(c)], x1=max(c["x1"], extent[id(c)])) if id(c) in folded else c
            for c in ln["chars"]
            if id(c) not in dropped
        ]
        if not any(not c["text"].isspace() for c in kept):
            first = next(c for c in ln["chars"] if id(c) in owner)
            if not FURNITURE_RE.search(ln["text"].strip()):  # lone digits were furniture, not body text
                extra[line_of[id(owner[id(first)])]] += raw_len
            continue
        text = pdfplumber.utils.extract_text(kept, x_tolerance=1.5, y_tolerance=1e6)
        out.append(
            (
                k,
                {
                    **ln,
                    "chars": kept,
                    "text": text,
                    "scripts": any(id(c) in folded for c in ln["chars"]),
                    "scripts_uncertain": uncertain,
                    "raw_len": raw_len,
                },
            )
        )
    return [{**ln, "raw_len": ln["raw_len"] + extra[k]} if k in extra else ln for k, ln in out]


def extract_page(page, index: int) -> Page:
    out = Page(index=index, width=float(page.width), height=float(page.height))
    chars = page.chars

    watermark = {id(c) for c in chars if c["size"] >= WATERMARK_MIN_SIZE}
    hidden = {id(c) for c in chars if c["size"] <= 1.5}
    hidden |= {id(c) for c in chars if not c.get("upright", True)}  # rotated margin codes, axis labels
    out.watermark_chars = len(watermark)
    out.grading_boxes, grading = find_grading_boxes(chars, out.width)
    drop = watermark | hidden | grading
    out.checkboxes, glyphs = glyph_checkboxes([c for c in chars if id(c) not in drop], out.height)

    kept = page.filter(lambda o: o.get("object_type") != "char" or id(o) not in drop)
    for raw in fold_scripts(kept.extract_text_lines(return_chars=True, x_tolerance=1.5, keep_blank_chars=False)):
        lchars = raw["chars"]
        font = Counter(base_font(c["fontname"]) for c in lchars).most_common(1)[0][0]
        size = Counter(round(c["size"], 1) for c in lchars).most_common(1)[0][0]
        color = Counter(to_rgb(c.get("non_stroking_color")) for c in lchars).most_common(1)[0][0]
        text = raw["text"].strip()
        furniture = bool(FURNITURE_RE.search(text))
        out.lines.append(
            Line(
                page=index,
                text=text,
                x0=raw["x0"],
                top=raw["top"],
                x1=raw["x1"],
                bottom=raw["bottom"],
                font=font,
                size=size,
                bold=bool(BOLD_RE.search(font)),
                color=color,
                furniture=furniture,
                fonts=frozenset(base_font(c["fontname"]) for c in lchars),
                scripts_uncertain=raw.get("scripts_uncertain", False),
                raw_len=raw.get("raw_len", len(text)),
                scripts=raw.get("scripts", False) or any(c["text"].isalnum() and c["size"] < 0.8 * size for c in lchars),
            )
        )
        if not STUDOCU_RE.search(text):  # lone numbers count as furniture but can be option texts
            out.words += split_words([c for c in lchars if id(c) not in glyphs], raw["top"], raw["bottom"])

    # Graphics: drop invisible white fills and the grid next to each grading box.
    def near_grading(b) -> bool:
        return any(
            b["top"] < g.bottom + 6
            and b["bottom"] > g.top - 6
            and b["x0"] < g.x1 + 45
            and b["x1"] > g.x0 - 45
            and (b["x1"] < MARGIN + 40 or b["x0"] > out.width - MARGIN - 40)
            for g in out.grading_boxes
        )

    for kind in ("rects", "lines", "curves"):
        for g in getattr(page, kind):
            if g.get("fill") and not g.get("stroke") and min(to_rgb(g.get("non_stroking_color"))) > 0.97:
                continue
            if near_grading(g):
                continue
            box = Box(g["x0"], g["top"], g["x1"], g["bottom"], kind[:-1])
            out.graphics.append(box)
            w, h = box.x1 - box.x0, box.bottom - box.top
            dark_fill = g.get("fill") and max(to_rgb(g.get("non_stroking_color"))) < 0.3  # scan markers
            # Blue squares are solution ink (fills over a ticked box, "■" in a sample answer).
            ink = (g.get("fill") and is_ink_color(to_rgb(g.get("non_stroking_color")))) or (
                g.get("stroke") and is_ink_color(to_rgb(g.get("stroking_color")))
            )
            if kind == "rects" and is_checkbox_size(w, h) and abs(w - h) <= 1.5 and not dark_fill and not ink:
                out.checkboxes.append(box)

    # Scans and photos (often tiled into several images, with handwriting on top) cover the page.
    page_area = out.width * out.height
    image_area = 0.0
    for img in page.images:
        area = (img["x1"] - img["x0"]) * (img["bottom"] - img["top"])
        image_area += area
        if area <= 0.6 * page_area:
            out.graphics.append(Box(img["x0"], img["top"], img["x1"], img["bottom"], "image"))
    body_chars = sum(len(ln.text) for ln in out.body)
    out.scanned = image_area > 0.6 * page_area and body_chars < 600

    out.redact = [Box(ln.x0, ln.top, ln.x1, ln.bottom) for ln in out.lines if STUDOCU_RE.search(ln.text)]
    if index == 0 and any(re.search(r"studocu", ln.text, re.IGNORECASE) for ln in out.lines):
        out.skip = "studocu-cover"
    return out


def mark_repeated_furniture(pages: list[Page]) -> None:
    """Lines repeated at the same spot on many pages (running headers/footers) are furniture."""
    content = [p for p in pages if not p.skip]
    if len(content) < 3:
        return
    keyed: list[tuple[Line, tuple]] = []
    for p in content:
        for ln in p.lines:
            if ln.top < 0.1 * p.height or ln.bottom > 0.9 * p.height:
                text = re.sub(r"\s+", "", ln.text)
                # Digits vary per page ("…-E0753-05"), but "Aufgabe N" headers must stay content,
                # and so must "(4 Punkte)" printed beside every task header at the top of the page (ds-2020-retake).
                if not TASK_HEADER_RE.match(ln.text) and not POINTS_NOTE_RE.match(ln.text):
                    text = re.sub(r"\d+", "#", text)
                keyed.append((ln, (text, round(ln.top / 8))))
    seen = Counter(key for _, key in keyed)
    threshold = max(3, 0.4 * len(content))
    for ln, key in keyed:
        # Needs real words: repeated labels inside identical figures ("-3") are content.
        if seen[key] >= threshold and len(re.findall(r"[^\W\d_]", ln.text)) >= 3:
            ln.furniture = True


def drop_margin_graphics(pages: list[Page]) -> None:
    """Footer/header graphics (barcodes, the "Seite leer" box, download banners) must not stretch crops.

    Dropped: everything from the footer text down, and small images/boxes near the top or bottom
    edge that repeat at the same spot on many pages (corner barcodes on pages without footer text)."""
    content = [p for p in pages if not p.skip]

    def key(g: Box) -> tuple:
        return g.kind, round(g.x0 / 4), round(g.top / 4)

    def near_edge(g: Box, p: Page) -> bool:
        small = g.kind == "image" or is_checkbox_size(g.x1 - g.x0, g.bottom - g.top)
        return small and (g.bottom < 0.1 * p.height or g.top > 0.9 * p.height)

    seen = Counter(key(g) for p in content for g in p.graphics if near_edge(g, p))
    threshold = max(3, 0.3 * len(content))
    for p in content:
        # Words, not lone numbers: digits of the margin grading boxes count as furniture too.
        feet = [ln.top for ln in p.lines if ln.furniture and ln.top > 0.85 * p.height and len(re.findall(r"[^\W\d_]", ln.text)) >= 3]
        foot = min(feet) - 8 if feet else p.height

        def margin(g: Box) -> bool:
            in_foot = (g.top + g.bottom) / 2 >= foot and g.bottom - g.top < 60  # noqa: B023 - called within this iteration
            return in_foot or (near_edge(g, p) and seen[key(g)] >= threshold)  # noqa: B023

        p.graphics = [g for g in p.graphics if not margin(g)]
        p.checkboxes = [c for c in p.checkboxes if (c.top + c.bottom) / 2 < foot]


def extract(path: str | Path) -> list[Page]:
    with pdfplumber.open(path) as pdf:
        pages = [extract_page(p, i) for i, p in enumerate(pdf.pages)]
    mark_repeated_furniture(pages)
    drop_margin_graphics(pages)
    return pages
